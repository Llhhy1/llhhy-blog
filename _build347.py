import os, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import package as pkg

ROOT = os.path.dirname(os.path.abspath(__file__))
version = pkg.expected_version()
print("version:", version)
assert version == "3.4.7", "期望 3.4.7，实际 %s" % version

# 1) 后端（含 IP 属地多源兜底 + 防注入 + 自愈 + 筛选表单美化 + config 3.4.7）
backend = pkg.package_backend(version)

# 2) 前端复用（本轮未改前端）
frontend = os.path.join(ROOT, "vue-frontend-dist.zip")
assert os.path.isfile(frontend), "前端 zip 缺失"
with zipfile.ZipFile(frontend) as zf:
    assert "index.html" in zf.namelist() and any(n.startswith("assets/") for n in zf.namelist())
print("  [frontend] reuse %s" % frontend)

# 3) 部署脚本包（顶层 update.sh + deploy.sh，沿用 v3.4.6 自动重启加固）
ds = os.path.join(ROOT, "deploy_scripts_v347fix.zip")
if os.path.exists(ds):
    os.remove(ds)
with zipfile.ZipFile(ds, "w", zipfile.ZIP_DEFLATED) as zf:
    for name in ("update.sh", "deploy.sh"):
        p = os.path.join(ROOT, name)
        assert os.path.isfile(p), "缺少 %s" % p
        zf.write(p, name)
print("  [deploy_scripts] %s" % ds)

# 4) 双源互证：向三个 zip 注释内嵌内容区哈希，并写 sha256.txt（三行）
pkg.write_checksums([backend, frontend, ds])
print("DONE build v3.4.7")
