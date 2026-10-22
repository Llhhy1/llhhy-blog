"""把解析结果落库：分类/标签、文章、可选的图片本地化。

两条关键纪律：

1. **导入时不触发“发布通知”**。`create_post_core(published=True)` 会发站内通知、
   SEO 推送、订阅邮件 —— 迁移 200 篇文章等于给订阅者发 200 封信。这里统一先以
   草稿落库，最后直接改 `published` 字段（不经过发布回调），再补一次 FTS 同步。
2. **图片下载必须走 `outbound.open_url()`**。旧站内容里的图片地址来自不可信输入，
   直接 `requests.get` 就是给服务器开一个 SSRF 口子。下载有数量/单张上限，
   失败只保留原 URL 并记一条警告，不阻断整篇导入。
"""
import hashlib
import html
import os
import re
import urllib.parse

from flask import current_app

from models import db, Post, Category
from utils import make_slug

MAX_IMAGES_PER_IMPORT = 200
MAX_IMAGE_BYTES = 5 * 1024 * 1024
_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc\s*=\s*)(["\'])(.*?)\2', re.I | re.S)
_EXT_BY_TYPE = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/avif": ".avif",
}
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}


def _plain_text(text, limit):
    """HTML/Markdown 混排 → 单行纯文本摘要。"""
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"[#>*_`~\[\]()!-]+", " ", t)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()[:limit]


def _unique_slug(base):
    base = (make_slug(base) or "post")[:200]
    candidate = base
    i = 2
    while Post.query.filter_by(slug=candidate).first():
        candidate = "%s-%d" % (base, i)
        i += 1
        if i > 999:
            candidate = "%s-%s" % (base, os.urandom(3).hex())
            break
    return candidate


def _category_id(name):
    name = (name or "").strip()[:80]
    if not name:
        return None
    cat = Category.query.filter_by(name=name).first()
    if cat:
        return cat.id
    from admin._helpers import unique_model_slug
    cat = Category(name=name, slug=unique_model_slug(Category, name, max_len=90))
    db.session.add(cat)
    db.session.flush()
    return cat.id


def _first_image(content):
    m = _IMG_SRC_RE.search(content or "")
    return m.group(3).strip() if m else ""


def _download_image(src, base_url, budget):
    """下载一张图片到 uploads/，返回站内 URL；失败返回空串。"""
    if budget.get("left", 0) <= 0:
        return ""
    if src.startswith("data:"):
        return ""
    src = html.unescape(src)          # 正文里的 &amp; 要先还原，否则请求的是错地址
    url = urllib.parse.urljoin(base_url, src) if base_url else src
    if not url.lower().startswith(("http://", "https://")):
        return ""
    from outbound import open_url, read_limited
    req_headers = {"User-Agent": "llhhy-blog-content-migrate/1.0", "Accept": "image/*"}
    try:
        with open_url(url, timeout=15, headers=req_headers) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if not ctype.startswith("image/"):
                return ""
            data, truncated = read_limited(resp, MAX_IMAGE_BYTES)
    except Exception as e:  # noqa: BLE001 —— 单张图失败不该中断整篇导入
        budget.setdefault("errors", []).append("%s: %s" % (url[:80], type(e).__name__))
        return ""
    if truncated or not data:
        budget.setdefault("errors", []).append("%s: 超过单张上限或空响应" % url[:80])
        return ""
    ext = _EXT_BY_TYPE.get(ctype, "")
    if not ext:
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in _ALLOWED_EXT:       # svg 等一律不收（XSS 面）
        return ""
    name = "mig-%s%s" % (hashlib.sha256(data).hexdigest()[:16], ext)
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        with open(path, "wb") as fh:
            fh.write(data)
    budget["left"] = budget.get("left", 0) - 1
    budget["used"] = budget.get("used", 0) + 1
    return "/static/uploads/" + name


def _localize_images(content, base_url, budget):
    if not content:
        return content, 0
    before = budget.get("used", 0)

    def repl(m):
        local = _download_image(m.group(3).strip(), base_url, budget)
        return (m.group(1) + m.group(2) + local + m.group(2)) if local else m.group(0)

    return _IMG_SRC_RE.sub(repl, content), budget.get("used", 0) - before


def import_items(result, *, publish=None, preserve_slug=True, download_images=False,
                 source_base="", author_id=None):
    """把 `ParseResult` 落库。返回统计 dict；单篇失败不中断整体。

    `publish`：None=沿用原站状态；True=全部发布；False=全部存草稿。
    `preserve_slug`：尽量保留原站 slug（推荐，链接不会断；重复导入也能靠它去重）。
    """
    from admin._helpers import create_post_core

    created, skipped, failed = 0, 0, 0
    warnings = list(result.warnings)
    imported_posts = []
    budget = {"left": MAX_IMAGES_PER_IMPORT, "used": 0, "errors": []}

    for item in result.items:
        try:
            wanted = ""
            if preserve_slug:
                wanted = (make_slug(item.slug or item.title) or "post")[:200]
                existing = Post.query.filter_by(slug=wanted).first()
                if existing:
                    if existing.title.strip() == item.title.strip():
                        skipped += 1
                        continue
                    wanted = _unique_slug(wanted)
            else:
                # 不保留 slug 时，用「标题 + 原创建时间」兜底去重，避免重复导入翻倍
                same = Post.query.filter_by(title=item.title).first()
                if same and (item.created_at is None or same.created_at == item.created_at):
                    skipped += 1
                    continue

            content = item.content or ""
            cover = item.cover or ""
            if download_images:
                if not cover:
                    cover = _first_image(content)
                content, n_img = _localize_images(content, source_base, budget)
                if cover:
                    local_cover = _download_image(cover, source_base, budget)
                    cover = local_cover or cover
                if n_img:
                    warnings.append("《%s》：本地化 %d 张图片" % (item.title[:40], n_img))

            summary = (item.summary or "").strip() or _plain_text(content, 200)
            tags = ",".join(str(t).replace(",", " ").replace("，", " ").strip()
                            for t in item.tags if str(t).strip())[:2000]
            post = create_post_core(
                title=item.title, content=content, summary=summary[:400],
                cover=cover[:500] if cover else "",
                category_id=_category_id(item.categories[0] if item.categories else ""),
                tags=tags, published=False, author_id=author_id,
            )
            if preserve_slug and wanted:
                post.slug = wanted
            if item.created_at:
                post.created_at = item.created_at
            if item.updated_at:
                post.updated_at = item.updated_at
            post.published = item.published if publish is None else bool(publish)
            db.session.commit()
            imported_posts.append(post)
            created += 1
            if item.note:
                warnings.append("《%s》：%s" % (item.title[:40], item.note))
        except Exception as e:  # noqa: BLE001 —— 单篇失败继续下一篇，最后汇总
            db.session.rollback()
            failed += 1
            warnings.append("《%s》导入失败：%s: %s" % (item.title[:40], type(e).__name__, str(e)[:120]))

    # 草稿期写入的 FTS 记录要按最终发布状态同步一次
    import contextlib
    with contextlib.suppress(Exception):
        import fts
        for post in imported_posts:
            fts.sync_post(post)
    with contextlib.suppress(Exception):
        from admin._helpers import cleanup_orphan_tags
        cleanup_orphan_tags()

    if budget.get("errors"):
        warnings.append("有 %d 张图片未能本地化（保留原地址）：%s"
                        % (len(budget["errors"]), "；".join(budget["errors"][:5])))
    return {
        "format": result.format,
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "images": budget.get("used", 0),
        "warnings": warnings[:50],
        "warning_count": len(warnings),
    }
