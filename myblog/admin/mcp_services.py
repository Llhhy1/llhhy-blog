# -*- coding: utf-8 -*-
"""MCP 服务管理面板（v3.13.0）。

后台统一的 MCP 服务管理入口（超管专属）：
1. **内置服务启停**：只读诊断 /mcp、写能力 /mcp-write 的运行时总开关
   （Setting 键 `mcp_diag_disabled` / `mcp_write_disabled`，停 → 端点对外 404，
   不暴露端点存在；get_setting 无缓存即时生效，无需重启）。
2. **外部服务登记**：登记第三方 MCP 服务（名称/URL/Header/Token），
   存 Setting 表 JSON（`mcp_external_services`），**不建新表**；Token 用
   backup_settings.encrypt_secret（Fernet，密钥源自 SECRET_KEY）加密单独存键
   （`mcp_service_token_<id>`），库里不落明文，页面只回显掩码。
3. **AI 接入指令生成**：每个服务可生成「脱敏版 / 完整版」接入指令——
   脱敏版给 AI 拿到步骤后引导用户填 token；完整版含真实 token，AI 拿到即可
   直接写 mcp.json / 执行安装。查看完整版写入审计日志（token 查看留痕）。

安全红线：
- 全部路由 super_required（超管专属，普通管理员 403）；
- 全部写操作 log_audit；
- Token 永不明文落库 / 明文回显（仅完整指令页显式查看，且记审计）；
- 外部服务 URL 强校验 http(s)，杜绝 javascript: 等注入面。
"""
import datetime
import json
import secrets
from urllib.parse import urlsplit

from flask import render_template, request, redirect, url_for, flash, jsonify, current_app

from models import db, Setting
from ._helpers import admin_bp, super_required, log_audit
from utils import get_setting, setting_bool
from backup_settings import encrypt_secret, decrypt_secret

# ---------------------------------------------------------------------------
# Setting 键与外部服务 JSON 的读写
# ---------------------------------------------------------------------------

KEY_DIAG_DISABLED = "mcp_diag_disabled"
KEY_WRITE_DISABLED = "mcp_write_disabled"
KEY_EXT_SERVICES = "mcp_external_services"
KEY_BASE_URL = "mcp_base_url"      # 生成指令用的对外域名（空 = 用当前访问域名）
KEY_TOKEN_FMT = "mcp_service_token_%s"

MAX_EXT_SERVICES = 20              # 外部服务登记数量上限（防滥用）


def _load_ext_services():
    """读外部服务列表（JSON 解析失败视为空列表，绝不抛异常）。"""
    raw = get_setting(KEY_EXT_SERVICES) or "[]"
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_ext_services(rows):
    _upsert_setting(KEY_EXT_SERVICES, json.dumps(rows, ensure_ascii=False))


def _upsert_setting(key, value):
    """Setting 表 upsert（主键是自增 id，不能用 merge 空对象——会撞 key 唯一约束）。"""
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))
    db.session.commit()


def _mask_token(tok):
    """token 掩码：前 4 + … + 后 4；过短全打码。"""
    tok = (tok or "").strip()
    if not tok:
        return ""
    if len(tok) <= 12:
        return "****"
    return tok[:4] + "…" + tok[-4:]


def _get_ext_token(sid):
    """解密某外部服务的 token；无/解密失败返回空串。"""
    return decrypt_secret(get_setting(KEY_TOKEN_FMT % sid) or "")


def _base_url():
    """指令里的对外域名：面板显式配置优先，否则用当前访问域名。"""
    configured = (get_setting(KEY_BASE_URL) or "").strip().rstrip("/")
    if configured:
        return configured
    return request.host_url.rstrip("/")


# ---------------------------------------------------------------------------
# 指令生成（脱敏版 / 完整版）
# ---------------------------------------------------------------------------

def _builtin_instruction(kind, full=False):
    """生成内置端点（diag / write）的接入指令文本。

    返回 (mcp_json 片段, 步骤文本)。full=True 时嵌入真实 token（调用方负责审计）。
    """
    base = _base_url()
    cfg_token_name = "MCP_AUTH_TOKEN" if kind == "diag" else "MCP_WRITE_TOKEN"
    real_token = current_app.config.get(cfg_token_name) or ""
    if kind == "diag":
        url = base + "/mcp"
        server_key = "llhhy-blog-diag"
        title = "只读诊断 MCP（%s）接入指令" % url
        purpose = "让 AI 助手远程查询博客健康状态：全站体检、数据库状态、日志（自动脱敏）、版本一致性等。"
    else:
        url = base + "/mcp-write"
        server_key = "llhhy-blog-write"
        title = "写能力 MCP（%s）接入指令" % url
        purpose = "让 AI 助手在授权下远程创建文章（默认落草稿，后台审核后发布）。"

    placeholder = "<%s>" % cfg_token_name
    shown = real_token if full else placeholder

    mcp_json = json.dumps({
        "mcpServers": {
            server_key: {
                "type": "http",
                "url": url,
                "headers": {"Authorization": "Bearer " + shown},
            }
        }
    }, ensure_ascii=False, indent=2)

    curl_probe = (
        "curl -i -X POST %s -H 'Content-Type: application/json' "
        "-d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'"
        % url)
    curl_ok = (
        "curl -s -X POST %s -H 'Content-Type: application/json' "
        "-H 'Accept: application/json, text/event-stream' "
        "-H \"Authorization: Bearer %s\" "
        "-d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'"
        % (url, shown))

    steps = [
        "目标：%s" % title,
        "用途：%s" % purpose,
        "",
        "1. 端点探活（不带 token 应 401/404，说明端点在线且受保护）：",
        "   %s" % curl_probe,
        "2. 带对 token 应返回工具列表 JSON（验证配置正确）：",
        "   %s" % curl_ok,
        "3. 把下面片段合并进 AI 客户端的 mcp.json（如 ~/.workbuddy/mcp.json）：",
        mcp_json,
        "4. token 说明：%s 存于服务器宝塔「环境变量」；脱敏版请向博主索取，" % cfg_token_name,
        "   或在本页点「显示完整指令」获取真实值（查看会留审计日志）。",
        "5. 保存后在 AI 客户端连接器管理页对 %s 点一次「信任」。" % server_key,
        "6. 验证：%s" % (
            "对 AI 说「博客现在健康吗」即走只读端点。"
            if kind == "diag" else
            "对 AI 说「帮我建一篇草稿，标题是…正文是…」，文章落在后台草稿箱即成功。"),
    ]
    if not real_token:
        hint = ("⚠️ 服务器尚未配置 %s，该端点当前对外关闭（fail-closed）。" % cfg_token_name)
        fix = ("   先在宝塔环境变量配置该值（python3 -c \"import secrets;print(secrets.token_hex(32))\" 生成），"
               "站点「停止 → 启动」后再生成完整指令。")
        steps[0:0] = [hint, fix, ""]

    return mcp_json, "\n".join(steps)


def _ext_instruction(row, full=False):
    """生成外部服务的接入指令文本。full=True 时嵌入解密后的 token。"""
    token = _get_ext_token(row["id"])
    shown = token if full else "<TOKEN>"
    header_name = row.get("header") or "Authorization"
    if header_name.lower() == "authorization":
        header_val = "Bearer " + shown
        header_note = "（Authorization 头，值带 Bearer 前缀）"
    else:
        header_val = shown
        header_note = "（自定义头，值就是 token 本身）"

    mcp_json = json.dumps({
        "mcpServers": {
            row["name"]: {
                "type": "http",
                "url": row["url"],
                "headers": {header_name: header_val},
            }
        }
    }, ensure_ascii=False, indent=2)

    steps = [
        "目标：接入外部 MCP 服务「%s」（%s）" % (row["name"], row["url"]),
        "用途：%s" % (row.get("desc") or "（登记时未填用途说明）"),
        "",
        "1. 把下面片段合并进 AI 客户端的 mcp.json（如 ~/.workbuddy/mcp.json）：",
        mcp_json,
        "2. 认证头：%s %s" % (header_name, header_note),
        "   token 来源：%s。" % (
            "本面板登记值，本页点「显示完整指令」可查看" if token
            else "登记时未填，请到面板补填"),
        "3. 保存后在 AI 客户端连接器管理页对「%s」点一次「信任」。" % row["name"],
        "4. 验证：让 AI 调用该服务的任一工具，返回正常即接入成功。",
    ]
    if not row.get("enabled", True):
        steps.insert(0, "⚠️ 该服务当前在面板里是「已停用」状态：先到面板开启再接入。")
    return mcp_json, "\n".join(steps)


# ---------------------------------------------------------------------------
# 面板页
# ---------------------------------------------------------------------------

@admin_bp.route("/mcp-services")
@super_required
def mcp_services():
    ext_rows = []
    for row in _load_ext_services():
        r = dict(row)
        r["token_masked"] = _mask_token(_get_ext_token(r.get("id", "")))
        ext_rows.append(r)
    return render_template(
        "admin/mcp_services.html",
        diag_enabled=not setting_bool(KEY_DIAG_DISABLED),
        write_enabled=not setting_bool(KEY_WRITE_DISABLED),
        diag_token_masked=_mask_token(current_app.config.get("MCP_AUTH_TOKEN") or ""),
        write_token_masked=_mask_token(current_app.config.get("MCP_WRITE_TOKEN") or ""),
        diag_token_ok=bool(current_app.config.get("MCP_AUTH_TOKEN")),
        write_token_ok=bool(current_app.config.get("MCP_WRITE_TOKEN")),
        ext_rows=ext_rows,
        base_url_setting=(get_setting(KEY_BASE_URL) or "").strip(),
    )


@admin_bp.route("/mcp-services/base", methods=["POST"])
@super_required
def mcp_services_base():
    """配置生成指令用的对外域名（空 = 用当前访问域名）。"""
    val = (request.form.get("base_url") or "").strip().rstrip("/")
    if val and not val.lower().startswith(("http://", "https://")):
        flash("❌ 对外域名必须以 http(s):// 开头")
        return redirect(url_for("admin.mcp_services"))
    _upsert_setting(KEY_BASE_URL, val)
    log_audit("mcp_base", "mcp_service", detail="指令对外域名=%s" % (val or "（用当前访问域名）"))
    flash("✅ 指令域名已保存")
    return redirect(url_for("admin.mcp_services"))


@admin_bp.route("/mcp-services/toggle/<which>", methods=["POST"])
@super_required
def mcp_services_toggle(which):
    """内置端点启停：停止 → 端点对外 404（不暴露存在），即时生效无需重启。"""
    if which not in ("diag", "write"):
        return jsonify({"error": "not found"}), 404
    key = KEY_DIAG_DISABLED if which == "diag" else KEY_WRITE_DISABLED
    enable = request.form.get("enable") == "1"
    _upsert_setting(key, "" if enable else "true")
    label = "只读诊断 /mcp" if which == "diag" else "写能力 /mcp-write"
    log_audit("mcp_toggle", "mcp_service", detail="%s → %s" % (label, "开启" if enable else "停止"))
    flash("✅ %s 已%s（%s）" % (label, "开启" if enable else "停止",
                                "端点恢复服务" if enable else "端点对外 404，即时生效"))
    return redirect(url_for("admin.mcp_services"))


# ---------------------------------------------------------------------------
# 外部服务 CRUD
# ---------------------------------------------------------------------------

def _validate_ext_form():
    """校验外部服务表单。返回 (err, 字段 dict)；err 非空即失败。"""
    name = (request.form.get("name") or "").strip()
    url = (request.form.get("url") or "").strip()
    header = (request.form.get("header") or "Authorization").strip() or "Authorization"
    token = (request.form.get("token") or "").strip()
    desc = (request.form.get("desc") or "").strip()

    if not name or len(name) > 40:
        return "名称必填且 ≤ 40 字", None
    if any(c.isspace() for c in name) or any(c in name for c in '"\'\\{}'):
        return "名称不能含空白或引号/反斜杠/花括号（要作为 mcp.json 的键）", None
    try:
        parts = urlsplit(url)
    except Exception:
        return "URL 格式不合法", None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return "URL 必须是 http(s):// 完整地址", None
    if len(url) > 300:
        return "URL ≤ 300 字符", None
    if len(header) > 60 or any(c.isspace() for c in header) or ":" in header:
        return "Header 名 ≤ 60 字符、不含空白与冒号", None
    if len(token) > 200:
        return "Token ≤ 200 字符", None
    if len(desc) > 120:
        return "用途说明 ≤ 120 字", None
    return "", {"name": name, "url": url, "header": header, "token": token, "desc": desc}


@admin_bp.route("/mcp-services/add", methods=["POST"])
@super_required
def mcp_services_add():
    err, f = _validate_ext_form()
    if err:
        flash("❌ " + err)
        return redirect(url_for("admin.mcp_services"))
    rows = _load_ext_services()
    if len(rows) >= MAX_EXT_SERVICES:
        flash("❌ 外部服务最多登记 %d 个，请先清理不再使用的条目" % MAX_EXT_SERVICES)
        return redirect(url_for("admin.mcp_services"))
    if any(r.get("name") == f["name"] for r in rows):
        flash("❌ 已存在同名服务「%s」" % f["name"])
        return redirect(url_for("admin.mcp_services"))

    sid = secrets.token_hex(4)
    rows.append({"id": sid, "name": f["name"], "url": f["url"], "header": f["header"],
                 "desc": f["desc"], "enabled": True,
                 "created_at": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%d %H:%M")})
    if f["token"]:
        _upsert_setting(KEY_TOKEN_FMT % sid, encrypt_secret(f["token"]))
    _save_ext_services(rows)
    log_audit("mcp_add", "mcp_service", detail="外部服务「%s」 %s" % (f["name"], f["url"]))
    flash("✅ 已登记外部服务「%s」，可在其指令页生成 AI 接入指令" % f["name"])
    return redirect(url_for("admin.mcp_services"))


@admin_bp.route("/mcp-services/update/<sid>", methods=["POST"])
@super_required
def mcp_services_update(sid):
    rows = _load_ext_services()
    row = next((r for r in rows if r.get("id") == sid), None)
    if not row:
        return jsonify({"error": "not found"}), 404

    # 仅启停（表单无 name 字段时按开关处理，避免整表校验误伤）
    if "name" not in request.form:
        enable = request.form.get("enable") == "1"
        row["enabled"] = enable
        _save_ext_services(rows)
        log_audit("mcp_toggle", "mcp_service",
                  detail="外部服务「%s」→ %s" % (row["name"], "开启" if enable else "停止"))
        flash("✅ 外部服务「%s」已%s" % (row["name"], "开启" if enable else "停止"))
        return redirect(url_for("admin.mcp_services"))

    err, f = _validate_ext_form()
    if err:
        flash("❌ " + err)
        return redirect(url_for("admin.mcp_services"))
    if any(r.get("id") != sid and r.get("name") == f["name"] for r in rows):
        flash("❌ 已存在同名服务「%s」" % f["name"])
        return redirect(url_for("admin.mcp_services"))

    row.update({"name": f["name"], "url": f["url"], "header": f["header"], "desc": f["desc"]})
    if f["token"]:  # 留空 = 不改 token
        _upsert_setting(KEY_TOKEN_FMT % sid, encrypt_secret(f["token"]))
    _save_ext_services(rows)
    log_audit("mcp_update", "mcp_service", detail="外部服务「%s」 %s" % (f["name"], f["url"]))
    flash("✅ 外部服务「%s」已更新" % f["name"])
    return redirect(url_for("admin.mcp_services"))


@admin_bp.route("/mcp-services/delete/<sid>", methods=["POST"])
@super_required
def mcp_services_delete(sid):
    rows = _load_ext_services()
    row = next((r for r in rows if r.get("id") == sid), None)
    if not row:
        return jsonify({"error": "not found"}), 404
    rows = [r for r in rows if r.get("id") != sid]
    _save_ext_services(rows)
    tk = Setting.query.filter_by(key=KEY_TOKEN_FMT % sid).first()
    if tk:
        db.session.delete(tk)
        db.session.commit()
    log_audit("mcp_delete", "mcp_service", detail="外部服务「%s」已删除（含密文 token）" % row["name"])
    flash("✅ 外部服务「%s」已删除" % row["name"])
    return redirect(url_for("admin.mcp_services"))


# ---------------------------------------------------------------------------
# AI 接入指令页
# ---------------------------------------------------------------------------

@admin_bp.route("/mcp-services/instruction/<kind>")
@super_required
def mcp_instruction(kind):
    """生成某服务的 AI 接入指令。?full=1 = 完整版（含真实 token，记审计）。"""
    full = request.args.get("full") == "1"
    if kind in ("diag", "write"):
        mcp_json, text = _builtin_instruction(kind, full=full)
        label = "只读诊断 /mcp" if kind == "diag" else "写能力 /mcp-write"
    else:
        row = next((r for r in _load_ext_services() if r.get("id") == kind), None)
        if not row:
            return jsonify({"error": "not found"}), 404
        mcp_json, text = _ext_instruction(row, full=full)
        label = "外部服务「%s」" % row["name"]

    if full:
        # 查看完整指令（含真实 token）留审计——token 属敏感信息，查看必须可回溯
        log_audit("mcp_full", "mcp_service", detail="查看完整接入指令：%s" % label)

    return render_template(
        "admin/mcp_instruction.html",
        kind=kind, label=label, mcp_json=mcp_json, text=text, full=full,
    )
