# -*- coding: utf-8 -*-
"""slug 生成、标签归一化与 slug 模板。（utils 子模块，v3.18.1 由 utils.py 拆出）。"""
import re
from .settings import get_setting



def make_slug(text):
    """把标题转成网址短名（slug）。
    保留中英文、数字和下划线，其它字符替换为减号。
    例如：'我的第一篇文章！' -> '我的第一篇文章'
    """
    s = re.sub(r"[^\w一-鿿]+", "-", (text or "").strip()).strip("-")
    return s or "post"


def normalize_tag_key(name):
    """标签归一化键（v3.15.0 标签治理）：去首尾/内部空白 + 统一小写。

    'AI'/'ai'/' AI ' 都归一到 'ai'；中文标签不受 casefold 影响。
    用于「同名不同写法」的标签去重比较，避免标签越积越多。
    """
    return "".join((name or "").casefold().split())


def split_tag_input(raw):
    """把标签输入拆成去重后的标签名列表（v3.15.0 标签治理）。

    分隔符兼容 ASCII/中文逗号、顿号、分号与换行；
    每个名字去除首尾空白/井号；单篇内重复（含大小写/空白变体）只保留一个。
    """
    seen, out = set(), []
    for part in re.split(r"[,，、;；\n]+", raw or ""):
        name = (part or "").strip().strip(" \t#")
        if not name:
            continue
        key = normalize_tag_key(name)
        if key and key not in seen:
            seen.add(key)
            out.append(name)
    return out
# v3.5.2：链接后缀全局模板支持的占位符与其取值来源。
# 仅这些键可作为 {xxx} 占位符；其余字面量原样保留（经 make_slug 清洗）。
SLUG_TEMPLATE_TOKENS = ("slug", "id", "date", "category")
# 预制模板（key -> 模板串）。key 同时作为 Setting.slug_mode 的取值。
# 顺序即下拉展示顺序；"title" 为默认（与旧行为一致）。
SLUG_PRESETS = {
    "title": "{slug}",          # 仅标题短名（旧默认行为）
    "slug-date": "{slug}-{date}",
    "id": "post-{id}",
    "date-slug": "{date}-{slug}",
    "category-slug": "{category}-{slug}",
}


def render_slug_template(template, *, slug, post_id=None, date=None, category=None):
    """把模板串里的 {slug}/{id}/{date}/{category} 替换成对应值，再整体清洗为合法 slug。

    - 各占位符单独经 make_slug 清洗（中英文/数字/下划线，其它转连字符）；
      空缺（如未选分类、date 为 None）则用空串，避免生成 'None' 这种脏串。
    - 字面量（模板里的固定文字）也随整体 make_slug 处理，保证最终仅含合法 slug 字符。
    - 返回清洗后的串；若清洗后为空则返回 None（调用方回退）。
    """
    def piece(token):
        val = {
            "slug": slug,
            "id": str(post_id) if post_id is not None else "",
            "date": (date or ""),
            "category": (category or ""),
        }.get(token, "")
        return make_slug(val) if val else ""

    rendered = template
    # 依次替换已知占位符（顺序无关，因互不嵌套）
    for tok in SLUG_TEMPLATE_TOKENS:
        rendered = rendered.replace("{" + tok + "}", piece(tok))
    # 去掉未识别的 {xxx}
    rendered = re.sub(r"\{[^}]*\}", "", rendered)
    return make_slug(rendered) or None


def apply_slug_template(post, title):
    """按全局 Setting 的 slug_mode / slug_template 生成 base slug。

    调用时机：新建或编辑文章、且用户未手动填单篇 slug 覆盖时。
    - mode='title'（默认）：等价于旧行为 unique_slug(title)。
    - 其它预制/自定义：用 render_slug_template 拼装后，用 unique_slug 做唯一化
      （冲突追加 -2/-3，绝不写出重复 slug 触发路由冲突）。
    返回最终 slug 字符串。
    """
    mode = (get_setting("slug_mode", "title") or "title").strip()
    if mode == "title":
        return _unique_slug_local(title, post.id)
    if mode == "custom":
        template = get_setting("slug_template", "") or ""
    else:
        template = SLUG_PRESETS.get(mode, SLUG_PRESETS["title"])
    if not template:
        return _unique_slug_local(title, post.id)
    # 取分类短名（有分类则取 category.slug，否则取空）
    category_slug = ""
    if getattr(post, "category", None) is not None:
        category_slug = post.category.slug or ""
    date_str = ""
    ca = getattr(post, "created_at", None)
    if ca is not None:
        date_str = ca.strftime("%Y%m%d")
    base = render_slug_template(
        template,
        slug=make_slug(title),
        post_id=post.id,
        date=date_str,
        category=category_slug,
    )
    if not base:
        return _unique_slug_local(title, post.id)
    return _unique_slug_local(base, post.id)


def _unique_slug_local(base, post_id=None):
    """本地唯一化 slug（避免 utils 顶层反向导入 admin 造成循环）。

    与 admin.unique_slug 逻辑一致：base 冲突（排除自身）时追加 -2/-3。
    """
    from models import Post  # 延迟导入，规避循环依赖

    slug = make_slug(base) or "post"
    i = 2
    while True:
        q = Post.query.filter_by(slug=slug)
        if post_id:
            q = q.filter(Post.id != post_id)
        if not q.first():
            break
        slug = f"{make_slug(base)}-{i}"
        i += 1
    return slug
