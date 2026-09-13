# -*- coding: utf-8 -*-
"""page_translate —— 全站翻译插件（整页翻译，含文章正文）。

设计（v3.18.0）：
- 前端形态：**远程预构建组件**（`myblog/static/plugins/page_translate/widget.js`），
  纯前端插件，`slots: []`，不占核心槽位；由 `remote_components` 声明、前端
  `window.__pluginRegister` 注册后挂载，**无需前端重新构建**（与旧 article_toc 同款机制）。
- 翻译引擎（前端优先本地、后端兜底）：
  1. 浏览器内置 Translator API（新版 Chrome/Edge，免费离线）→ 前端直译，不经过本端点；
  2. 不支持时 → POST 本插件 `/translate`，复用站点「游戏收录 / AI 摘要」的 OpenAI 兼容配置
     （`api.ai._llm_chat`），无需新增密钥。
- 安全（见 SECURITY_AUDIT.md R81）：
  - POST 走全局 `_csrf_protect`（要求 `X-CSRF-Token`）；
  - 按 IP 限流 + 全局总量限流（防单点刷 / 分布式刷导致 LLM 成本失控）；
  - 目标语言白名单 + 条数/字符双重上限（防超长 payload）；
  - 纯转发、**不落库**；译文由前端以 `textContent` 写入（不经 innerHTML，无 XSS 面）。
- 只装自写/审计过的插件（第三方插件 = 任意代码执行），沿用插件框架红线。
"""
import json
import re

from flask import Blueprint, jsonify, request

from utils import get_setting, rate_limit

bp = Blueprint(
    "plugin_page_translate",
    __name__,
    url_prefix="/api/plugin/page_translate",
)

# 目标语言白名单（源语言由站点 site_lang 推断，仅允许翻译到这些目标）
_LANG_NAMES = {
    "zh": "简体中文",
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    "en": "English（英文）",
    "ja": "日本語（日文）",
    "ko": "한국어（韩文）",
    "fr": "Français（法文）",
    "de": "Deutsch（德文）",
    "es": "Español（西班牙文）",
    "ru": "Русский（俄文）",
}
# 单次请求上限（防超长 payload / 成本失控）
_MAX_ITEMS = 40
_MAX_TOTAL_CHARS = 4000


def _client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def _detect_langs():
    """源语言 = 后台「站点语言」设置（默认中文）；目标语言 = 源语言之外的另一端。"""
    src = (get_setting("site_lang", "zh") or "zh").strip()
    if src.startswith("zh"):
        return src, "en"
    return src, "zh"


def _llm_ready():
    """站点 LLM 是否已配置可用（与游戏审计 / AI 摘要共用配置）。"""
    if get_setting("games_llm_on", "0") != "1":
        return False
    base = (get_setting("games_llm_base", "") or "").strip()
    enc = (get_setting("games_llm_key_enc", "") or "").strip()
    model = (get_setting("games_llm_model", "") or "").strip()
    return bool(base and enc and model)


def _build_prompt(texts, target):
    lang_name = _LANG_NAMES.get(target, target)
    system = (
        "你是专业翻译引擎。把用户给出的 JSON 字符串数组逐条翻译成 %s。"
        "硬性要求：① 严格保持数组元素个数与顺序；② 保留原文中的代码、URL、邮箱、"
        "数字、Markdown/模板符号与专有名词；③ 不要合并或拆分条目；④ 只返回一个 JSON "
        "字符串数组，不要任何解释、不要代码块围栏。" % lang_name
    )
    user = json.dumps(texts, ensure_ascii=False)
    return system, user


def _parse_json_array(text):
    """从模型输出里鲁棒地抠出第一个 JSON 数组并解析（容忍代码块围栏/前后废话）。"""
    if not text:
        return None
    s = text.strip()
    # 去掉 ```json ... ``` 围栏
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    start, end = s.find("["), s.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        arr = json.loads(s[start:end + 1])
    except Exception:
        return None
    if not isinstance(arr, list):
        return None
    return [("" if x is None else str(x)) for x in arr]


@bp.get("/config")
def config():
    """公开只读：告诉前端站点主语言、默认目标语言、以及 LLM 兜底是否可用。"""
    src, target = _detect_langs()
    return jsonify({
        "source": src,
        "target": target,
        "llm_on": _llm_ready(),
        "engine": "browser-first, llm-fallback",
    })


@bp.post("/translate")
def translate():
    """LLM 兜底翻译端点。入参 {target, texts:[...]} → {translations:[...]}。"""
    ip = _client_ip()
    # 双层限流：单 IP 40 次/分，全局 240 次/分（防分布式刷爆 LLM 账单）
    if not rate_limit("ptr_ip_%s" % ip, limit=40, window=60):
        return jsonify({"error": "翻译过于频繁，请稍后再试"}), 429
    if not rate_limit("ptr_global", limit=240, window=60):
        return jsonify({"error": "站点翻译繁忙，请稍后再试"}), 429

    data = request.get_json(silent=True) or {}
    target = (data.get("target") or "").strip()
    texts = data.get("texts")
    if target not in _LANG_NAMES:
        return jsonify({"error": "不支持的目标语言"}), 400
    if not isinstance(texts, list) or not texts:
        return jsonify({"error": "texts 必须为非空数组"}), 400
    texts = [("" if t is None else str(t)) for t in texts[:_MAX_ITEMS]]
    if sum(len(t) for t in texts) > _MAX_TOTAL_CHARS:
        return jsonify({"error": "单次翻译内容过长，请分批"}), 400

    if not _llm_ready():
        return jsonify({"error": "翻译服务未配置（后台「游戏收录 → ⚙️ LLM 审计配置」开启并填好 Base/Key/Model）"}), 503

    # 懒导入，避免插件加载期与 api 包形成循环依赖
    from api.ai import _llm_chat
    system, user = _build_prompt(texts, target)
    out, err = _llm_chat(system, user, timeout=60)
    if out is None:
        return jsonify({"error": err or "翻译失败"}), 502

    arr = _parse_json_array(out)
    if arr is None or len(arr) != len(texts):
        return jsonify({"error": "模型返回格式异常，请重试"}), 502
    return jsonify({"translations": arr})


def register(app, cfg):
    """插件入口：注册端点 + 声明远程前端组件。"""
    app.register_blueprint(bp)
    return {
        "name": "全站翻译",
        "version": "1.0.0",
        "author": "llhhy",
        "description": "浮层一键整页翻译（含文章正文）：优先浏览器内置翻译，回退站点大模型。",
        "slots": [],
        "remote_components": [
            {"name": "page_translate_widget", "url": "/static/plugins/page_translate/widget.js"},
        ],
    }
