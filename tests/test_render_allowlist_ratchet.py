"""把「改了 HTML 白名单必须 bump `_RENDER_VERSION`」这条纪律变成**机器门禁**。

背景（v3.26.0 审计 R115，低危 latent 风险）：
`utils/render.py` 的正文渲染结果会缓存进 `post.content_html`，失效判断靠
`content_digest()`——它把 `_RENDER_VERSION` 混进指纹。所以一旦**收紧或放宽
`_ALLOWED_TAGS` / `_ALLOWED_ATTRS` 却忘了 bump `_RENDER_VERSION`**，历史文章的
旧缓存 HTML **不会重渲染**，新白名单对存量内容形同虚设。

这条纪律原先只写在 `render.py` 的注释和 `README.md` 里 —— 靠人记住。
本文件把它钉死：**白名单一改，测试立刻变红**，逼作者同时更新
`_RENDER_VERSION` 与本文件里的 `ALLOWLIST_SHA256`（两者一起改才是完整动作）。
"""
import ast
import hashlib
import io
import os

RENDER_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "myblog", "utils", "render.py")

# v3.25.x 基线：白名单 = 常用排版标签 + 表格系，属性集**不含 style、不含任何 on\***。
EXPECTED_ALLOWLIST_SHA256 = \
    "8c47e46f63649a7ef41f0b2ac110866fce3cbd0f6867aeb30e6f8c02afa06db5"
EXPECTED_RENDER_VERSION = "3"


def _load():
    """用 AST 取字面量——不 import 整个包（避免 app 上下文依赖）。"""
    with io.open(RENDER_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = node.targets[0].id
            if name in ("_ALLOWED_TAGS", "_ALLOWED_ATTRS", "_RENDER_VERSION"):
                out[name] = ast.literal_eval(node.value)
    return out


def test_allowlist_matches_recorded_hash():
    """白名单改了 → 变红。修复动作：bump `_RENDER_VERSION` + 更新本常量。"""
    d = _load()
    basis = repr(sorted(d["_ALLOWED_TAGS"])) + "|" + repr(sorted(d["_ALLOWED_ATTRS"].items()))
    got = hashlib.sha256(basis.encode()).hexdigest()
    assert got == EXPECTED_ALLOWLIST_SHA256, (
        "HTML 白名单已变更（sha256=%s，记录值=%s）。\n"
        "**必须同时 bump `utils/render.py` 的 `_RENDER_VERSION` 并更新本文件常量**，"
        "否则历史文章的 `content_html` 缓存不会重渲染，新白名单对存量内容无效。"
        % (got, EXPECTED_ALLOWLIST_SHA256))


def test_render_version_unchanged_since_hash_update():
    d = _load()
    assert d["_RENDER_VERSION"] == EXPECTED_RENDER_VERSION, (
        "_RENDER_VERSION 被改成 %r，但白名单哈希常量没变——"
        "两者必须一起更新（否则下次改白名单不会被门禁发现）。"
        % d["_RENDER_VERSION"])


def test_allowlist_has_no_dangerous_tags_or_attrs():
    """白名单的**语义**底线：不得放进 script/iframe/style/svg/form 与 on* 事件属性。"""
    d = _load()
    tags = set(d["_ALLOWED_TAGS"])
    dangerous = {"script", "iframe", "style", "svg", "form", "object", "embed", "link"}
    assert not (tags & dangerous), "白名单混入了危险标签：%s" % sorted(tags & dangerous)
    for owner, attrs in d["_ALLOWED_ATTRS"].items():
        names = set(attrs)
        assert "style" not in names, "%s 放行了 style 属性（可做 CSS 注入）" % owner
        for a in names:
            assert not a.startswith("on"), "%s 放行了事件属性 %s" % (owner, a)
