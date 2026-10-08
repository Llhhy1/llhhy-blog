# 排错必备：常见问题 / 忘记密码 / 安全组

> 本文摘自 `myblog/deploy_guide.md` 的「可选配置」部分，独立成文以降低主文档体量。
> **主线部署请回到 [部署手册](../../myblog/deploy_guide.md)。**

## 常见问题排查

| 现象 | 原因与解决 |
|---|---|
| 打开网站 502 | Python 项目没起来：到「网站 → Python项目」看是否「运行中」，点日志看报错（端口被占/依赖没装全最常见） |
| 页面刷新 404 | Nginx 少了 `try_files $uri $uri/ /index.html;`，检查第 4 步 |
| **后台能打开但完全没样式（全文本）** | **Nginx 少了 `location /static/` 反代**！`/static/admin.css` 返回 404。检查第 4 步，把 `/static/` 那段加上并重载配置 |
| 改了后台样式没变化 | admin.css 有缓存：重启 Python 项目（刷新版本戳）+ 浏览器强刷 Ctrl+F5 |
| 页面白屏 | 按 F12 → Network：`/api/site` 若 404/502，说明 `/api/` 反代没生效或 Python 项目没启动 |
| 登录后点「退出」没反应 | 旧版前端的 bug：前台退出已改为调用接口（不再用 /logout 链接），重新上传 `vue-frontend-dist.zip` 并强刷 |
| 后台登录提示密码错误 | 已设置过新密码；忘了就用下面的「重置密码」命令 |
| 上传图片 500 | `static/uploads/` 无写权限：文件管理右键该目录 → 权限 → 755 |
| 天气不显示 / 定位报错 | 已改双源（wttr.in 优先 + Open-Meteo 兜底）：定位被拒会自动回退默认城市；也可手动输城市名，无需 Key |
| 备案号怎么填 | 后台 → 站点设置 → 页脚备案号，填 `京ICP备xxxxxx号` 格式 |

## 忘记后台密码怎么办

宝塔左侧 **「终端」** → 粘贴执行（把 `新密码123` 换成你的）：

```bash
cd /www/wwwroot/myblog
# 找到项目的虚拟环境 python（宝塔 Python 项目详情里可看到，一般是 /www/wwwroot/myblog/venv/bin/python 或类似）
python -c "
from app import app
from models import db, User
from werkzeug.security import generate_password_hash
with app.app_context():
    u = User.query.filter_by(role='super').first()
    u.password_hash = generate_password_hash('新密码123')
    u.must_change_password = True
    db.session.commit()
    print('超级管理员密码已重置')
"
```

若 `python` 找不到，先用 `ls /www/wwwroot/myblog/venv/bin/python` 确认路径，把命令开头的 `python` 换成完整路径。执行后用 `新密码123` 登录（会再次要求设置新密码）。

---

## 云服务器安全组（如果端口访问不通）

本博客对外只需 **80（HTTP）/ 443（HTTPS）** 两个端口。若部署后域名打不开，请到你的云厂商控制台 → 云服务器 → 安全组 → 确认入方向放行了 `80` 和 `443`（能正常打开面板一般说明安全组是通的，通常无需改动）。
