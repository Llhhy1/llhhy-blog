# -*- coding: utf-8 -*-
"""模块级 import 图**零循环依赖**守卫（v3.25.0）。

背景：v3.25.0 之前，模块级 import 图里有一个 **21 模块的强连通分量** —— `admin` 包与
`api` 包被拉进同一个环。两条边各拖一个包：

    api.common  →  admin            （为了 log_login_attempt）
    admin.ai_summary → api.ai       （为了 _llm_chat / prompt 模板）

环一旦形成，导入顺序就成为隐式契约：谁先被 import 决定了另一个包能否拿到自己的名字，
而这个约束**任何静态检查都看不见**，表现为「本地能跑、gunicorn 换个 worker 就 ImportError」。
`api/theme.py` 与 `seo_push.py` 里那两处 `# 只能延迟导入` 的注释就是这个环的直接产物。

拆法（见 `audit.py` 的模块 docstring）：审计写入是横切关注点，从 `admin/_helpers.py`
搬到顶层 `audit.py`，`api → admin` 这条边随之消失；顺带把 17 处 `from . import admin_bp`
改成 `from ._helpers import admin_bp`（同一个对象，来源更直接），`admin` 包内自环也断开。
现状：**零 SCC**。

建图口径（这五条任一错都会让环凭空消失或凭空出现，改本文件时务必照抄）：

1. 包内 `from . import x`（level=1）**必须**建边 —— `admin/__init__.py` 有 22 条
   副作用注册边，整类丢掉会让 admin 包在图里孤立。
2. `__init__.py` 的 parent_pkg 是**它自己**，不是父包。
3. `from . import X`（module=None）必须**优先展开 names** —— 否则 22 条注册边
   全塌成 `admin → admin` 自环，而**自环不算强连通分量**。
4. `from . import X` 里若 `X` 不是子模块（典型：`from . import admin_bp`），Python 会
   **回退取包属性**（`__init__.py` 里 `from ._helpers import admin_bp` 暴露的）。这是一条
   真实的「子模块 → 包」边，丢掉会把 22 个子模块与 admin 包之间的强连通抹平。
5. **只对本地模块建边**。stdlib / 第三方是纯 sink，建进去只把边数灌到 500+，
   不改变 SCC 结论但让数字失去对照意义。

成环判据：**该边两端是否落在同一个强连通分量**。⛔ 不可用「删掉这条边还成不成环」——
已存在大环时那个判据恒为真，会把几十条无辜边（如 `admin/_helpers → utils`）全判成环内边。
"""
import ast
import pathlib

import admin

MYBLOG = pathlib.Path(admin.__file__).resolve().parent.parent

# 局部模块名 -> 相对 myblog/ 的路径
REL = {p.stem: p.relative_to(MYBLOG).as_posix() for p in MYBLOG.glob("*.py")}
REL.update({p.parent.name + "." + p.stem: p.relative_to(MYBLOG).as_posix()
            for p in MYBLOG.glob("*/*.py")})
PKG = {p.parent.name for p in MYBLOG.glob("*/__init__.py")}
MODS = set(REL) | PKG


def _norm(name):
    """归一到图里的本地模块名；非本地依赖（stdlib / 第三方）返回 None。"""
    if not name:
        return None
    if name in MODS:          # 包内子模块（api.ai）原样保留，**不能 split**
        return name
    top = name.split(".")[0]  # 其余按顶层模块名归一（import fts / import utils.settings）
    return top if top in MODS else None


def _parent_pkg(mod):
    """铁律 2：__init__.py 的「父包」是它自己。"""
    if mod in PKG:
        return mod
    return mod.rsplit(".", 1)[0] if "." in mod else ""


def _resolve_relative(cur, level, module):
    base = _parent_pkg(cur)
    for _ in range(level - 1):
        base = _parent_pkg(base)
    if not module:
        return base or None
    cand = f"{base}.{module}" if base else module
    return cand if cand in MODS else _norm(module)


def _build_graph():
    """模块级 import 图（只看顶层 import，函数内 import 不进图 —— 它们不是包级依赖）。"""
    edges = {}
    for name in sorted(MODS):
        if name in PKG:
            path = MYBLOG / (name + "/__init__.py")     # 铁律 1 + 4
        else:
            path = MYBLOG / REL[name]
        if not path.exists():
            continue
        out = edges.setdefault(name, set())
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Import):
                for a in node.names:
                    d = _norm(a.name)
                    if d:
                        out.add(d)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = _resolve_relative(name, node.level, node.module)
                    if node.module is None:
                        for a in node.names:
                            d = f"{base}.{a.name}" if base else a.name
                            if d in MODS:
                                out.add(d)
                            elif _norm(a.name):
                                out.add(_norm(a.name))
                            elif base:
                                out.add(base)              # 铁律 4：回退取包属性
                    elif base:
                        out.add(base)
                elif node.module:
                    m = node.module if node.module in MODS else _norm(node.module)
                    if m:
                        out.add(m)
                    for a in node.names:
                        if a.name in MODS:
                            out.add(a.name)
    return {k: {d for d in v if d} for k, v in edges.items()}


def _tarjan(nodes, edges):
    index, low, stk, on, out = {}, {}, [], {}, []

    def strong(v):
        index[v] = low[v] = len(index)
        stk.append(v)
        on[v] = True
        for w in sorted(edges.get(v, ())):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif on.get(w):
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stk.pop()
                on[w] = False
                comp.append(w)
                if w == v:
                    break
            out.append(comp)

    for v in sorted(nodes):
        if v not in index:
            strong(v)
    return out


def _graph_is_sane():
    """建图自检：口径错了会静默产出「零环」，必须先证明图本身是对的。

    这不是重复断言业务事实，而是断言**探针没坏**：
    - 建图必须包含 `admin/__init__.py` 的注册边（否则整包孤立，环会凭空消失）；
    - 必须包含 `models` / `utils` 这类真实边（否则图是空的）。
    """
    edges = _build_graph()
    assert "admin" in edges and len(edges["admin"]) >= 15, (
        "建图失败：admin 包的注册边不足 15 条，说明 from . import x 被整类丢弃（铁律 1/3）"
    )
    assert any(d == "models" for d in edges.get("admin._helpers", ())), (
        "建图失败：admin._helpers → models 这类顶层绝对导入边缺失，绝对导入没被识别"
    )
    assert "models" in edges and "_time" in edges["models"], (
        "建图失败：models → _time 边缺失"
    )
    return edges


def test_no_module_level_import_cycles():
    """模块级 import 图不得存在大于 1 的强连通分量（v3.25.0 起为零）。

    回归背景：21 模块强连通分量（admin ↔ api），已由顶层 `audit.py` 拆掉。
    """
    edges = _graph_is_sane()
    nodes = set(edges) | {d for s in edges.values() for d in s}
    cycles = [sorted(c) for c in _tarjan(nodes, edges) if len(c) > 1]
    assert not cycles, (
        "出现模块级循环依赖（Tarjan 强连通分量），导入顺序成了隐式契约，"
        "换 worker / 换导入顺序即 ImportError:\n" +
        "\n".join("  " + " ↔ ".join(c) for c in cycles)
    )


def test_admin_package_has_no_self_import_cycle():
    """admin 包内不得有子模块「回取包属性」（`from . import admin_bp` 这类）。

    这类边是 v3.25.0 那 21 模块环的另一半：`admin/__init__.py` 副作用 import 全部子模块
    完成路由注册（`admin → admin.xxx`），子模块若再 `from . import admin_bp` 回取包属性
    （`admin.xxx → admin`），17 个子模块就与 admin 包连成一片强连通。
    正确写法是 `from ._helpers import admin_bp` —— 同一个对象，来源更直接。
    """
    offenders = []
    for p in sorted((MYBLOG / "admin").glob("*.py")):
        if p.name == "__init__.py":
            continue                          # 它的 from . import xxx 是注册边，必须留
        for node in ast.parse(p.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ImportFrom) and node.level and node.module is None:
                for a in node.names:
                    # `from . import xxx` 且 xxx 不是本包子模块 → 回取包属性
                    if "admin." + a.name not in REL:
                        offenders.append("%s:%d -> from . import %s"
                                         % (p.name, node.lineno, a.name))
    assert not offenders, (
        "admin 子模块回取包属性（应为 `from ._helpers import ...`）:\n" + "\n".join(offenders)
    )


def test_audit_module_has_no_admin_dependency():
    """顶层 `audit.py` 零 admin 依赖 —— 它能被任何层导入是靠这条保证的。

    一旦 audit 反向依赖 admin，`admin → audit → admin` 立刻成新环，且这次是
    **包内**环，比原来的更难拆（api 不再是中间环节，退路全无）。
    """
    tree = ast.parse((MYBLOG / "audit.py").read_text(encoding="utf-8"))
    for node in tree.body:                      # 只看顶层 import
        if isinstance(node, ast.Import):
            assert not any(a.name.split(".")[0] == "admin" for a in node.names), \
                "audit.py 顶层不得 import admin"
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "")
            assert not mod.startswith("admin"), "audit.py 顶层不得 from admin... import"
