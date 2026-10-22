"""把 WordPress WXR / Typecho SQL 备份解析成统一的文章条目。

这里**只解析、不碰数据库**：解析器可以单独测试，落库逻辑在 importer.py。
两种输入格式的共同目标是一份 `PostItem` 列表：

- WordPress：管理后台「工具 → 导出」得到的 WXR（XML）。这是 WordPress 官方格式，
  大多数「Typecho → WordPress」中转工具最终也会产出 WXR。
- Typecho：phpMyAdmin / 面板导出的 SQL 备份。Typecho 没有官方导出 XML，
  但它的表结构稳定（contents / metas / relationships），解析 SQL 备份最直接。

安全边界：
- 拒绝带 `DOCTYPE` / `ENTITY` 的 XML —— 防实体膨胀（billion laughs）；
- 只读取需要的表，不执行任何 SQL（纯文本解析）；
- 不做任何网络请求（图片下载在 importer 里，走统一的 SSRF 安全出站层）。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET

MAX_ITEMS = 5000


class ParseError(ValueError):
    """输入格式无法识别或内容损坏。"""


@dataclass
class PostItem:
    title: str
    slug: str = ""
    content: str = ""
    summary: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    published: bool = True
    kind: str = "post"
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    cover: str = ""
    source_id: str = ""
    note: str = ""


@dataclass
class ParseResult:
    format: str
    items: list[PostItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)

    def summary(self):
        """给前台预览用的摘要（不含正文，避免把整站内容回显到大响应里）。"""
        published = sum(1 for i in self.items if i.published)
        return {
            "format": self.format,
            "total": len(self.items),
            "published": published,
            "draft": len(self.items) - published,
            "skipped": dict(self.skipped),
            "warnings": self.warnings[:20],
            "samples": [{"title": i.title[:120], "slug": i.slug, "published": i.published}
                        for i in self.items[:10]],
        }


def parse_any(raw, filename=""):
    """按内容嗅探格式并解析。`raw` 为 bytes。"""
    if not raw:
        raise ParseError("文件是空的")
    head = raw[:4096].decode("utf-8", "ignore").lstrip("\ufeff \t\r\n")
    if head.startswith("<?xml") or head.startswith("<rss") or "<channel" in head:
        return parse_wxr(raw)
    if "INSERT INTO" in head.upper() or "CREATE TABLE" in head.upper():
        return parse_typecho_sql(raw)
    raise ParseError("无法识别格式%s：请上传 WordPress 的 WXR(.xml) 或 Typecho 的 SQL 备份(.sql)"
                        % ("（%s）" % filename[:60] if filename else ""))


# ---------------------------------------------------------------- WordPress WXR


def _local(tag):
    """去掉 XML 命名空间，只留本地名（WXR 1.0/1.1/1.2 的命名空间并不统一）。"""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el, name):
    c = _child(el, name)
    return (c.text or "") if c is not None and c.text else ""


def _ns_text(el, ns_fragment, name):
    """按命名空间片段取文本（content:encoded 与 excerpt:encoded 本地名相同）。"""
    for c in el:
        if _local(c.tag) == name and ns_fragment in (c.tag or ""):
            return c.text or ""
    return ""


def _parse_wp_date(value):
    s = (value or "").strip()
    if not s or s.startswith("0000") or s.startswith("1970-01-01 00:00:00"):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)   # 项目约定：naive UTC
        except ValueError:
            continue
    return None


def _clean_html_content(text):
    text = text or ""
    # Gutenberg 区块注释与「更多」标记：留着只会变成正文里的噪声
    text = re.sub(r"<!--\s*/?wp:[^>]*-->", "", text)
    text = re.sub(r"<!--\s*more\s*-->", "", text, flags=re.I)
    return text.strip()


def _strip_tags(text):
    plain = re.sub(r"<[^>]+>", " ", text or "")
    plain = html.unescape(plain)
    return re.sub(r"\s+", " ", plain).strip()


def parse_wxr(raw):
    """解析 WordPress WXR。返回 `ParseResult`。"""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    low = raw.lower()
    if b"<!doctype" in low or b"<!entity" in low:
        raise ParseError("XML 里包含 DOCTYPE/ENTITY 声明，已拒绝解析（防实体膨胀攻击）")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise ParseError("XML 解析失败：%s" % e) from e

    result = ParseResult(format="wordpress")
    items = [el for el in root.iter() if _local(el.tag) == "item"]
    if not items:
        raise ParseError("没有找到 <item>：这不像 WordPress 的 WXR 导出文件")

    # 附件 id → URL：特色图（_thumbnail_id）指向的是附件 item，可能排在其后
    attachments = {}
    for el in items:
        if _text(el, "post_type") == "attachment":
            attachments[_text(el, "post_id")] = _text(el, "attachment_url")

    for el in items:
        post_type = _text(el, "post_type") or "post"
        if post_type == "attachment":
            continue
        if post_type != "post":
            result.skipped[post_type] = result.skipped.get(post_type, 0) + 1
            continue
        title = html.unescape(_text(el, "title")).strip()
        if not title:
            result.skipped["empty_title"] = result.skipped.get("empty_title", 0) + 1
            continue
        status = (_text(el, "status") or "publish").strip().lower()
        categories, tags = [], []
        for c in el:
            if _local(c.tag) != "category":
                continue
            domain = (c.get("domain") or "").strip().lower()
            name = html.unescape((c.text or "").strip())
            if not name:
                continue
            if domain == "category":
                categories.append(name)
            elif domain in ("post_tag", "tag"):
                tags.append(name)
        thumb_id = ""
        for meta in el:
            if _local(meta.tag) == "postmeta" and _text(meta, "meta_key") == "_thumbnail_id":
                thumb_id = _text(meta, "meta_value").strip()
        content = _clean_html_content(_ns_text(el, "content", "encoded"))
        excerpt = _strip_tags(_ns_text(el, "excerpt", "encoded"))
        created = _parse_wp_date(_text(el, "post_date_gmt")) or _parse_wp_date(_text(el, "post_date"))
        updated = _parse_wp_date(_text(el, "post_modified_gmt")) or created
        item = PostItem(
            title=title[:200],
            slug=urllib.parse.unquote(_text(el, "post_name")).strip()[:200],
            content=content,
            summary=excerpt[:400],
            created_at=created,
            updated_at=updated,
            published=(status == "publish"),
            kind="post",
            categories=categories[:1],     # 本项目一篇文章只有一个分类，多余的进警告
            tags=tags[:50],
            cover=attachments.get(thumb_id, ""),
            source_id=_text(el, "post_id"),
        )
        if len(categories) > 1:
            item.note = "原站有 %d 个分类，只保留第一个「%s」" % (len(categories), categories[0])
            result.warnings.append("《%s》：%s" % (title[:40], item.note))
        if not content:
            result.warnings.append("《%s》：正文为空，仍会导入（可在后台补写）" % title[:40])
        result.items.append(item)
        if len(result.items) >= MAX_ITEMS:
            result.warnings.append("条目超过 %d 条，只导入前 %d 条" % (MAX_ITEMS, MAX_ITEMS))
            break
    if not result.items:
        raise ParseError("WXR 里没有可导入的文章（可能只有页面/附件）")
    return result


# ---------------------------------------------------------------- Typecho SQL

# Typecho 的字段顺序（`INSERT INTO ... VALUES` 不带列名时用；按 1.2 官方结构）
_TYPECHO_CONTENTS_COLS = [
    "cid", "title", "slug", "created", "modified", "text", "order", "authorId",
    "template", "type", "status", "password", "commentsNum", "allowComment",
    "allowPing", "allowFeed", "parent",
]
_TYPECHO_METAS_COLS = ["mid", "name", "slug", "type", "count", "order", "parent", "description"]
_TYPECHO_REL_COLS = ["cid", "mid"]

_MYSQL_ESCAPES = {
    "0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t",
    "Z": "\x1a", "\\": "\\", "'": "'", '"': '"',
}


def _mysql_unescape(s):
    return re.sub(r"\\(.)", lambda m: _MYSQL_ESCAPES.get(m.group(1), m.group(1)), s)


def _value(raw, quoted):
    if quoted:
        v = raw
        if v.startswith("_binary "):
            v = v[len("_binary "):]
        return _mysql_unescape(v)
    s = raw.strip()
    if not s or s.upper() == "NULL":
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _scan_row(sql, i):
    """从 `(` 开始扫描一行 VALUES，返回 (值列表, 下一个位置)。"""
    n = len(sql)
    if i >= n or sql[i] != "(":
        raise ParseError("SQL 解析失败：VALUES 后不是 '('")
    i += 1
    vals, cur = [], []
    quoted = False
    q = None
    while i < n:
        ch = sql[i]
        if q:
            if ch == "\\" and i + 1 < n:
                cur.append(ch)
                cur.append(sql[i + 1])
                i += 2
                continue
            if ch == q:
                if i + 1 < n and sql[i + 1] == q:      # 双写引号转义
                    cur.append(q)
                    i += 2
                    continue
                q = None
                i += 1
                continue
            cur.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            if not quoted and not "".join(cur).strip():
                cur = []                             # `_binary '...'` 前缀先丢掉
            q = ch
            quoted = True
            i += 1
            continue
        if ch == ",":
            vals.append(_value("".join(cur), quoted))
            cur, quoted = [], False
            i += 1
            continue
        if ch == ")":
            vals.append(_value("".join(cur), quoted))
            return vals, i + 1
        cur.append(ch)
        i += 1
    raise ParseError("SQL 解析失败：VALUES 行没有闭合括号")


def _iter_insert_rows(sql, table):
    """遍历某个表的全部 INSERT 行，返回 dict 列表（列名取自 INSERT 或内置顺序）。"""
    pattern = re.compile(
        r"INSERT\s+(?:IGNORE\s+)?INTO\s+`?%s`?\s*(?:\(([^)]*)\))?\s*VALUES\s*" % re.escape(table),
        re.I,
    )
    fallback = {
        "contents": _TYPECHO_CONTENTS_COLS,
        "metas": _TYPECHO_METAS_COLS,
        "relationships": _TYPECHO_REL_COLS,
    }.get(table.split("_")[-1], [])
    for m in pattern.finditer(sql):
        cols = None
        if m.group(1):
            cols = [c.strip().strip("`") for c in m.group(1).split(",") if c.strip()]
        if not cols:
            cols = fallback
        i = m.end()
        while True:
            while i < len(sql) and sql[i] in " \t\r\n,":
                i += 1
            if i >= len(sql) or sql[i] != "(":
                break
            vals, i = _scan_row(sql, i)
            if len(vals) != len(cols):
                # 列数对不上通常是解析到了别的表；跳过该行比整包失败更稳
                continue
            yield dict(zip(cols, vals, strict=False))


def _ts(value):
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _typecho_prefix(sql):
    m = re.search(r"(?:INSERT\s+(?:IGNORE\s+)?INTO|CREATE\s+TABLE)\s+`?([A-Za-z0-9_]+?)_contents`?", sql, re.I)
    return m.group(1) if m else ""


def parse_typecho_sql(raw):
    """解析 Typecho 的 SQL 备份（phpMyAdmin / 面板导出均可）。"""
    if isinstance(raw, bytes):
        # phpMyAdmin 导出的字符集不一定是 UTF-8；GB18030 覆盖 GBK/GB2312 老备份
        for enc in ("utf-8", "gb18030"):
            try:
                raw = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raw = raw.decode("utf-8", "replace")
    prefix = _typecho_prefix(raw)
    if not prefix:
        raise ParseError("没有找到 *_contents 表：这不像 Typecho 的 SQL 备份")
    t_contents = prefix + "_contents"
    t_metas = prefix + "_metas"
    t_rel = prefix + "_relationships"
    result = ParseResult(format="typecho")

    # 分类/标签：mid → (type, name)，cid → [mid]
    meta = {}
    for row in _iter_insert_rows(raw, t_metas):
        mtype = (row.get("type") or "").strip().lower()
        name = html.unescape(str(row.get("name") or "").strip())
        if name and mtype in ("category", "tag"):
            meta[row.get("mid")] = (mtype, name)
    rel = {}
    for row in _iter_insert_rows(raw, t_rel):
        cid, mid = row.get("cid"), row.get("mid")
        if cid is not None and mid in meta:
            rel.setdefault(cid, []).append(meta[mid])

    for row in _iter_insert_rows(raw, t_contents):
        ctype = (row.get("type") or "post").strip().lower()
        if ctype in ("page", "page_draft", "attachment", "revision"):
            result.skipped[ctype] = result.skipped.get(ctype, 0) + 1
            continue
        if ctype not in ("post", "post_draft"):
            continue
        title = html.unescape(str(row.get("title") or "").strip())
        if not title:
            result.skipped["empty_title"] = result.skipped.get("empty_title", 0) + 1
            continue
        text = str(row.get("text") or "")
        if text.startswith("<!--markdown-->"):
            # Typecho 用这个标记表示正文是 Markdown；标记本身不能进正文
            text = text[len("<!--markdown-->"):]
        text = re.sub(r"<!--\s*more\s*-->", "", text, flags=re.I).strip()
        status = (row.get("status") or "publish").strip().lower()
        cats, tags = [], []
        for mtype, name in rel.get(row.get("cid"), []):
            (cats if mtype == "category" else tags).append(name)
        password = str(row.get("password") or "").strip()
        item = PostItem(
            title=title[:200],
            slug=urllib.parse.unquote(str(row.get("slug") or "").strip())[:200],
            content=text,
            created_at=_ts(row.get("created")),
            updated_at=_ts(row.get("modified")) or _ts(row.get("created")),
            published=(status == "publish" and not password and ctype == "post"),
            kind="post",
            categories=cats[:1],
            tags=tags[:50],
            source_id=str(row.get("cid") or ""),
        )
        if password:
            item.note = "原站是密码保护文章，已导入为草稿（导入器不支持密码）"
            result.warnings.append("《%s》：%s" % (title[:40], item.note))
        if len(cats) > 1:
            result.warnings.append("《%s》：原站有 %d 个分类，只保留第一个「%s」"
                                   % (title[:40], len(cats), cats[0]))
        if not text:
            result.warnings.append("《%s》：正文为空，仍会导入（可在后台补写）" % title[:40])
        result.items.append(item)
        if len(result.items) >= MAX_ITEMS:
            result.warnings.append("条目超过 %d 条，只导入前 %d 条" % (MAX_ITEMS, MAX_ITEMS))
            break
    if not result.items:
        raise ParseError("SQL 里没有可导入的文章（可能只有页面/附件）")
    return result
