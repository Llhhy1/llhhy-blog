"""
"""


from flask import request, jsonify, session

from .common import (api_bp, db, Moment, MomentComment, SocialAccount, User, _current_user, _moment, _mcomment, rate_limit, client_key)
import stats  # myblog/stats.py：client_ip / cached_region（动态归属地）

# ---------- 社交聚合页（广场）----------
@api_bp.route("/moments")
def moments():
    """微动态列表（倒序分页）。"""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    pagination = Moment.query.order_by(Moment.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [_moment(m) for m in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total,
    })


@api_bp.route("/moment", methods=["POST"])
def post_moment():
    """发布一条微动态（需登录，限流，纯文本存储，前端渲染时自动转义防 XSS）。"""
    u = _current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    if not rate_limit(client_key("api_moment"), limit=20, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "动态内容不能为空"}), 400
    if len(content) > 500:
        return jsonify({"error": "动态最多 500 字"}), 400
    m = Moment(author_id=u.id, content=content)
    db.session.add(m)
    db.session.commit()
    return jsonify({"ok": True, "moment": _moment(m)}), 201


@api_bp.route("/moment/<int:mid>/like", methods=["POST"])
def like_moment(mid):
    """微动态点赞（限流防刷）。"""
    m = Moment.query.get_or_404(mid)
    if not rate_limit(client_key("api_mlike:" + str(mid)), limit=20, window=60):
        return jsonify({"likes": m.likes})
    m.likes += 1
    db.session.commit()
    return jsonify({"likes": m.likes})


@api_bp.route("/moment/<int:mid>/comment", methods=["POST"])
def comment_moment(mid):
    """微动态评论（需昵称；已登录自动用用户名）。"""
    m = Moment.query.get_or_404(mid)
    if not rate_limit(client_key("api_mcomment"), limit=10, window=60):
        return jsonify({"error": "评论过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    content = (data.get("content") or "").strip()
    author = ""
    u = _current_user()
    if u:
        author = u.username
    author = author or (data.get("author") or "").strip()
    if not author or not content:
        return jsonify({"error": "昵称和评论内容不能为空"}), 400
    from utils import parse_device
    ip = stats.client_ip()
    c = MomentComment(moment_id=m.id, author=author[:80], content=content,
                      ip=ip, region=stats.cached_region(ip),
                      device=parse_device(request.headers.get("User-Agent", ""))[:120])
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "comment": _mcomment(c)}), 201


@api_bp.route("/feed/circle")
def feed_circle():
    """博客圈：抓取友链站点 RSS，按时间混排（带缓存 + SSRF 防护）。

    v3.8.6：响应附 `debug` 诊断块，无需登服务器即可看到「聚合为何为空」：
    - total_links / links_with_rss：友链总数 / 已填 RSS 数
    - feedparser_ok：feedparser 是否安装
    - fetched / skipped：成功抓取 / 跳过的源数
    - notes：每条友链的具体原因（安全校验未过 / 抓取失败 / 解析 0 条等）
    """
    try:
        import feed_agg
        force = request.args.get("refresh") == "1"
        items = feed_agg.get_circle_feed(force=force)
        debug = feed_agg.get_last_diag()
    except Exception as e:
        # v3.8.4：不再静默——异常栈落日志（gunicorn.log 可查）
        import traceback
        print("[FEED AGG] 博客圈聚合异常:", repr(e))
        traceback.print_exc()
        items = []
        debug = {"error": repr(e)}
    return jsonify({"items": items, "debug": debug})


@api_bp.route("/social-accounts")
def social_accounts():
    """作者的社交账号墙（广场页「关注」标签用）。"""
    accs = SocialAccount.query.order_by(SocialAccount.sort).all()
    return jsonify([
        {"id": a.id, "platform": a.platform, "handle": a.handle, "url": a.url}
        for a in accs
    ])

