"""admin 包显式导入治理的回归守卫（v3.24.0）。

背景：v3.24.0 之前，admin 各业务子模块一律 `from ._helpers import *`，而 _helpers
的 `__all__` 是运行时 `[n for n in globals() if not n.startswith("__")]` 快照——
把 os / time / functools / Blueprint / db / Post… 等全部顶层名字灌进每个子模块。
后果：① 每模块背 15~20 个污染名；② 同名符号（time / utcnow / feed_agg / current_app…）
谁生效只取决于「星号行与自身 import 行的先后」，行序一变即 NameError，且静态检查
看不见（F403 默认放行、F821 因名字恰好存在而不报）。

本文件守住五条：
1. admin 包内禁止复活真·星号导入（AST 判定，注释里的字样不误报）；
2. _helpers.__all__ 必须是显式列表，不得退回 globals() 运行时快照；
3. 每个子模块所有函数的 LOAD_GLOBAL 都能在 fn.__globals__（= 定义处模块命名空间）
   中解析——「运行时零 NameError」的结构性证明，不依赖测试是否恰好打到该路由；
4. 包命名空间的 re-export 面与外部真实消费面一致（v3.25.0：审计 re-export 已撤）；
5. 审计写入的实现只许住在顶层 `audit.py`，`admin/_helpers.py` 只剩薄转发。

⚠️ 第 3 条解析域必须用 fn.__globals__ 而不是 vars(导入它的模块)：@login_required 等
装饰器内部用 functools.wraps 复制原函数的 __module__，导致装饰后的 wrapped 被
算进业务模块，但其字节码在 _helpers 的命名空间里解析——判错域会产出大量假阳性。
⚠️ builtins 判定用 builtins 模块的名字集合，不要用 dir(__builtins__)——pytest 里
__builtins__ 常是 dict，dir() 出来的是字典方法名，len/max/Exception 全会误报缺失。
"""
import ast
import builtins
import dis
import importlib
import pathlib
import pkgutil
import types

import admin

ADMIN_DIR = pathlib.Path(admin.__file__).parent
_BUILTINS = set(dir(builtins))


def test_admin_package_has_no_star_imports():
    """星号导入已全量退役（AST 判定 ImportFrom(name='*')，注释字样不误报）。"""
    offenders = []
    for p in sorted(ADMIN_DIR.glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
                offenders.append("%s:%d" % (p.name, node.lineno))
    assert not offenders, "admin 包内不得出现星号导入（行序依赖、静态检查盲区）: %s" % offenders


def test_helpers_all_is_explicit_not_runtime_snapshot():
    """_helpers.__all__ 必须是 ast.List 显式清单，不得是 globals() 快照。"""
    tree = ast.parse((ADMIN_DIR / "_helpers.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            assert isinstance(node.value, ast.List), (
                "_helpers.__all__ 退回了非显式形式（globals() 快照会重新灌入第三方污染名）"
            )
            return
    raise AssertionError("_helpers.py 里找不到 __all__ 赋值")


def test_every_admin_function_resolves_all_load_globals():
    """结构性零 NameError：每个函数的 LOAD_GLOBAL 都能在 fn.__globals__ 解析。

    覆盖了「没有测试打到的路由」——比逐路由访问更彻底。
    """
    missing = []
    for m in sorted(x.name for x in pkgutil.iter_modules(admin.__path__)):
        mod = importlib.import_module("admin." + m)
        for fn_name, fn in list(vars(mod).items()):
            if not isinstance(fn, types.FunctionType):
                continue
            g = fn.__globals__          # LOAD_GLOBAL 的真实解析域（见模块 docstring）
            code = fn.__code__
            local = set(code.co_varnames) | set(code.co_freevars) | set(code.co_cellvars)
            for ins in dis.get_instructions(code):
                if ins.opname != "LOAD_GLOBAL":
                    continue
                name = ins.argval
                if name in g or name in local or name in _BUILTINS:
                    continue
                missing.append("%s.%s -> %s" % (m, fn_name, name))
    assert not missing, "存在运行时 NameError（LOAD_GLOBAL 解析不到）:\n" + "\n".join(missing[:30])


def test_package_reexports_match_external_consumers():
    """包命名空间的 re-export 面与外部真实消费面一致。

    外部按名导入（grep 全仓核定）：**只剩 app.py → admin_bp**。
    少一个 = 外部 ImportError，多一个 = 借包命名空间绕过显式导入（要消灭的东西）。

    v3.25.0 变化：原先还有 api/common.py、routes.py → log_login_attempt 与
    api/theme.py → log_audit 三处；审计写入搬到顶层 `audit.py` 后消费面归零，
    三个 re-export 一并撤掉（`admin.log_audit` 若仍可按名取到，就会有人继续
    从 admin 包拿审计，环就白断了）。
    """
    assert hasattr(admin, "admin_bp"), "admin 包命名空间缺少外部依赖的 re-export: admin_bp"
    for gone in ("log_audit", "log_login_attempt"):
        assert not hasattr(admin, gone), (
            "admin 包不该再 re-export %s —— 审计已归顶层 audit.py，"
            "留着会诱导新代码继续从 admin 取审计（admin ↔ api 环就是这么长出来的）" % gone
        )


def test_audit_implementation_lives_only_in_top_level_audit_module():
    """审计写入的实现只允许存在于顶层 `audit.py`（AST 判定，防复发起）。

    v3.25.0 之前 `log_audit` / `log_login_attempt` / `_purge_audit_logs_older_than`
    的实现在 `admin/_helpers.py`，而前台 API、routes、seo_push 都要写审计 ——
    于是产生 `api → admin` 与 `admin → api` 两条顶层边，把 admin 与 api 拉进
    同一个 21 模块强连通分量。搬到顶层 `audit.py` 后 `admin/_helpers.py` 只剩
    薄转发（保 `admin._helpers.log_audit` 这个既有 API 不破）。

    这里守的是「实现不许回流」：转发层里出现 `db.session.add(AuditLog` 这类
    真正的写入代码，就说明有人把实现搬回去了。
    """
    import audit

    audit_file = pathlib.Path(audit.__file__)

    def _defines_real_writer(path, fname):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name == fname):
                continue
            # 函数体里出现 AuditLog(...) 或 db.session.add → 不是薄转发
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "add"):
                    return True
                if (isinstance(sub, ast.Name) and sub.id == "AuditLog"):
                    return True
        return False

    # 顶层 audit.py 必须是真实现（有写入）
    for fname in ("log_audit", "log_login_attempt", "_purge_audit_logs_older_than"):
        assert _defines_real_writer(audit_file, fname), (
            "顶层 audit.py 的 %s 不应是空壳/转发 —— 实现必须住在中立顶层" % fname
        )
    # admin/_helpers.py 必须只剩薄转发（不得再有真写入）
    for fname in ("log_audit", "log_login_attempt", "_purge_audit_logs_older_than"):
        assert not _defines_real_writer(ADMIN_DIR / "_helpers.py", fname), (
            "admin/_helpers.py 的 %s 里出现了真正的审计写入代码 —— "
            "实现已归顶层 audit.py，写入代码回流会让 admin ↔ api 环复活" % fname
        )
