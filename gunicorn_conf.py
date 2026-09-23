# gunicorn 生产配置（v3.20.0 起入库）
#
# ## 为什么现在才入库
#
# 线上这份配置是**宝塔面板自动生成**的（`/www/wwwroot/myblog/gunicorn_conf.py`），
# 从来没进过仓库。风险很实在：删站重建 / 换机器时这份文件会凭空消失，
# 而它决定了并发能力与稳定性，且**重建后静默退化**（没人会注意到）。
# 入库后「重建站点」有据可依。
#
# ## 关键事实：这里写 `worker_class = 'sync'` 但线上实际跑的是 gthread
#
# 宝塔生成的原始配置是 `workers = 4, threads = 2, worker_class = 'sync'`。
# 而 **gunicorn 22 只要看到 `threads > 1`，就会自动把 worker 升级为 `gthread`**
# （config.py 的线程设置文档明说：*"If you try to use the sync worker type and
# set the threads setting to more than 1, the gthread worker type will be used
# instead."*）。启动日志可见 `[INFO] Using worker: gthread`，
# 每个 worker 进程内 4 个线程（2 个工作线程 + 主线程 + 日志线程）。
#
# → **实际并发槽 = workers × threads = 4 × 2 = 8**，不是 4。
# 排查「慢请求/自请求占满 worker」类问题时，请按 gthread 判断；
# 曾有一份第三方审计报告据此误判为「2~3 个 sync worker、两个并发点击即可打挂全站」。
# 详见 `myblog/SECURITY_AUDIT.md` R91。
#
# ## 调参建议
#
# * 机器是 **2 核**（`nproc` = 2）。gunicorn 官方建议 `(2 × 核数) + 1`，
#   据此 4 个 worker 是合理的；再加 worker 只会加剧 SQLite 写锁竞争。
# * `threads` 对**本项目**的意义：多数请求是 SQLite 读 + 模板渲染（IO/等锁型），
#   多线程有收益。但因为 `worker_class` 断言的是 sync，实际靠 gunicorn 自动升级，
#   语义略显隐晦 —— 这里**刻意保留宝塔原样**（不改 worker_class），
#   理由是「线上就是它、已验证、改它没有收益」，而不是「这样写更好」。
#   若日后需要显式化，可改为 `worker_class = 'gthread'`，行为完全一致。
# * `timeout` 保持默认 30s。注意本项目有几处**同步外网调用**（如 `notify.py`
#   每个渠道 6s、游戏 LLM 审计 120s），worker 超时被 kill 会造成请求 502 ——
#   这也是 ROADMAP §5.9 把「请求路径内的同步外网调用」列为待还债务的原因。
#
# ## 部署方式
#
# 本文件**不在部署包（`myblog-backend.zip`）里** —— `package.py` 只收 `myblog/`，
# 而这份配置在仓库根。所以：
#   * 首次部署 / 重建站点时，进宝塔「网站 → Python 项目」把 `启动文件` 的
#     `-c` 参数指向本文件（或在项目根放一份副本）；
#   * 日常升级（update.sh）不覆盖它，无需关心。

# 项目目录
chdir = '/www/wwwroot/myblog'

# 进程数：2 核机器按 (2 × nproc) + 1 = 5 的官方建议偏保守取 4
workers = 4

# 每个进程的工作线程数。
# ⚠️ >1 会让 gunicorn 自动把 worker_class 升级为 gthread（见上文）
threads = 2

# 启动用户（宝塔 Python 项目默认 www）
user = 'www'

# 启动模式。保留上游宝塔生成的 'sync' 字面值（实际会被自动升级为 gthread），
# 见上文「调参建议」——这里不改是为了与线上逐字一致。
worker_class = 'sync'

# 绑定的 ip 与端口
bind = '0.0.0.0:8686'

# 进程文件目录（用于停止/重启服务，请勿删除）
pidfile = '/www/wwwroot/myblog/gunicorn.pid'

# 访问日志与错误日志
accesslog = '/www/wwwlogs/python/myblog/gunicorn_acess.log'
errorlog = '/www/wwwlogs/python/myblog/gunicorn_error.log'

# 日志级别（错误日志级别；访问日志级别无法在此设置）
# debug / info / warning / error / critical
loglevel = 'info'
