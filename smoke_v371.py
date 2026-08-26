"""v3.7.1 冒烟测试：bot/爬虫识别。

覆盖：
1) detect_bot 纯函数：搜索引擎 / AI / 工具 / 未知 / 真人 五类 UA 识别正确
2) record_visit 落库 is_bot / bot_name / bot_category
3) compute_summary 含 bot_visits / human_visits / bot_today / bot_breakdown 且数值正确
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "myblog"))

from utils import detect_bot


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        check.failed += 1


check.failed = 0

# ---- 1) detect_bot 纯函数 ----
cases = [
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", True, "Googlebot", "search"),
    ("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", True, "Bingbot", "search"),
    ("Baiduspider/2.0", True, "Baiduspider", "search"),
    ("Mozilla/5.0 AppleWebKit (compatible; GPTBot/1.0)", True, "GPTBot", "ai"),
    ("Mozilla/5.0 (compatible; CCBot/2.0)", True, "CCBot", "ai"),
    ("Mozilla/5.0 (compatible; ClaudeBot/1.0)", True, "ClaudeBot", "ai"),
    ("python-requests/2.31", True, "python-requests", "tool"),
    ("curl/8.0", True, "curl", "tool"),
    ("Mozilla/5.0 (Linux; Android) Mobile Safari", False, "", ""),
    ("Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari", False, "", ""),
    ("SomeWeirdCrawler/1.0", True, "未知爬虫", "unknown"),
]
for ua, e_is, e_name, e_cat in cases:
    is_bot, name, cat = detect_bot(ua)
    ok = (is_bot == e_is and name == e_name and cat == e_cat)
    check(f"detect_bot[{name or 'human'}]", ok)
    if not ok:
        print(f"   got=({is_bot},{name},{cat}) want=({e_is},{e_name},{e_cat})")

# ---- 2)+3) 落库 + 汇总 ----
from flask import Flask, request
from models import db, VisitLog
import stats

tmp = tempfile.mkdtemp()
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(tmp, "blog.db")
app.config["SECRET_KEY"] = "smoke-test-secret"
db.init_app(app)
with app.app_context():
    db.create_all()
    with app.test_request_context("/", headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"}):
        stats.record_visit("/", None)
    with app.test_request_context("/post/x", headers={"User-Agent": "Mozilla/5.0 (iPhone) Chrome Mobile"}):
        stats.record_visit("/post/x", 1)
    with app.test_request_context("/", headers={"User-Agent": "GPTBot/1.0"}):
        stats.record_visit("/", None)

    rows = VisitLog.query.all()
    check("visit count == 3", len(rows) == 3)
    bot_rows = [r for r in rows if r.is_bot]
    check("bot rows == 2 (Googlebot + GPTBot)", len(bot_rows) == 2)
    names = {r.bot_name for r in bot_rows}
    check("bot names == {Googlebot, GPTBot}", names == {"Googlebot", "GPTBot"})
    cats = {r.bot_category for r in bot_rows}
    check("bot categories include search & ai", "search" in cats and "ai" in cats)

    s = stats.compute_summary()
    check("summary.bot_visits == 2", s["bot_visits"] == 2)
    check("summary.human_visits == 1", s["human_visits"] == 1)
    check("summary.bot_today == 2", s["bot_today"] == 2)
    bd = {b["name"]: b["count"] for b in s["bot_breakdown"]}
    check("breakdown Googlebot=1 & GPTBot=1", bd.get("Googlebot") == 1 and bd.get("GPTBot") == 1)

print("\nRESULT:", "ALL PASS" if check.failed == 0 else f"{check.failed} FAILED")
sys.exit(1 if check.failed else 0)
