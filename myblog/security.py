"""v3.1.6 安全辅助模块：安全响应头 + 图形验证码 + SMTP 密码环境变量优先。

- security_headers(resp)：注入 X-Frame-Options / X-Content-Type-Options / Referrer-Policy / CSP。
- captcha 生成与校验：注册（及可选评论/留言）前端提交时先获取验证码图片，
  后端生成 4 位字符图（纯标准库 PIL，失败降级为纯文本 code），答案存会话（CAPTCHA_KEY），
  前端提交时把验证码文本随请求提交，/api/captcha/verify 校验并换一次性票据（会话标记）。
- load_mail_config 的密码优先级：环境变量 SMTP_PASSWORD 优先（若 SMTP_PASSWORD_ENV_FIRST=true），
  库中 mail_password 仅当环境变量未配置时才回退使用（避免敏感信息落库）。
"""
import io
import os
import random
import string

from flask import session, current_app

_CAPTCHA_SESSION_KEY = "captcha_answer"
_CAPTCHA_PASS_KEY = "captcha_passed"


# ---------- 安全响应头 ----------
def security_headers(resp):
    """为响应注入安全头（app.after_request 调用）。
    CSP 采用同源受限策略：允许内联样式/脚本（本站后台模板与 Vue 均为内联），
    放宽 img/connect（天气/头像/外部图片），阻止 frame 嵌套与其他站点资源。
    """
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # CSP：default-src 'self'；script/style 允许内联（后台模板 + Vue 产物）；img/connect/media 放宽；
    # 不允许 frame 嵌套（配合 X-Frame-Options）；font 同源。
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' https:; "
        "media-src 'self' https:; "
        "font-src 'self' data:; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    return resp


# ---------- 图形验证码 ----------
def _gen_captcha_text(length=4):
    """生成验证码文本：排除易混淆字符（0/O、1/I/L）。"""
    chars = "23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ"
    return "".join(random.SystemRandom().choice(chars) for _ in range(length))


def _render_captcha_image(text):
    """用 PIL 画验证码图；PIL 不可用时返回 None（调用方降级为纯文本验证码）。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None
    try:
        w, h = 120, 44
        img = Image.new("RGB", (w, h), (245, 246, 250))
        draw = ImageDraw.Draw(img)
        # 干扰线 + 噪点
        rnd = random.SystemRandom()
        for _ in range(4):
            draw.line(
                [rnd.randint(0, w), rnd.randint(0, h), rnd.randint(0, w), rnd.randint(0, h)],
                fill=(rnd.randint(150, 210), rnd.randint(150, 210), rnd.randint(150, 210)),
                width=1,
            )
        for _ in range(40):
            draw.point((rnd.randint(0, w), rnd.randint(0, h)),
                       fill=(rnd.randint(120, 220), rnd.randint(120, 220), rnd.randint(120, 220)))
        # 尝试用系统字体，找不到用默认
        font = None
        for fp in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "C:/Windows/Fonts/arialbd.ttf",
                   "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
            if os.path.exists(fp):
                try:
                    font = ImageFont.truetype(fp, 24)
                    break
                except Exception:
                    font = None
        if font is None:
            font = ImageFont.load_default()
        # 每个字符稍微错位、用不同颜色
        x = 12
        colors = [(30, 90, 200), (190, 60, 60), (40, 150, 90), (150, 100, 30)]
        for i, ch in enumerate(text):
            draw.text((x, 8 + rnd.randint(-3, 3)), ch,
                      font=font, fill=colors[i % len(colors)])
            x += 26
        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)
        return buf
    except Exception:
        return None


def generate_captcha():
    """生成验证码：答案存会话，返回 (png_bytes 或 None, 纯文本降级用 code 或空)。"""
    text = _gen_captcha_text()
    session[_CAPTCHA_SESSION_KEY] = text
    img = _render_captcha_image(text)
    return img, text


def verify_captcha(user_input):
    """校验验证码答案（恒定时间比较，一次性）。返回 True/False，成功即清除。"""
    ans = session.get(_CAPTCHA_SESSION_KEY)
    if not ans or not user_input:
        return False
    import hmac
    ok = hmac.compare_digest(str(ans).lower(), str(user_input).strip().lower())
    if ok:
        session.pop(_CAPTCHA_SESSION_KEY, None)
        session[_CAPTCHA_PASS_KEY] = True  # 标记本会话已通过验证码（一次性票据）
    else:
        # 错误保留答案允许重试；连续 5 次错误强制重新生成
        cnt = session.get("captcha_fail_count", 0) + 1
        if cnt >= 5:
            session.pop(_CAPTCHA_SESSION_KEY, None)
            session["captcha_fail_count"] = 0
        else:
            session["captcha_fail_count"] = cnt
    return ok


def captcha_required():
    """判断当前请求是否要求验证码（评论 / 注册场景，由各接口调用）。"""
    cfg = current_app.config.get("CAPTCHA_ENABLED", True)
    if not cfg:
        return False
    return True


def captcha_passed():
    """当前会话是否已通过验证码（一次性）。"""
    return bool(session.get(_CAPTCHA_PASS_KEY))


def consume_captcha_pass():
    """消费一次性验证码票据（校验通过后清除，防止复用）。"""
    passed = session.pop(_CAPTCHA_PASS_KEY, False)
    return bool(passed)


# ---------- SMTP 密码环境变量优先 ----------
def mail_password_precedence():
    """返回 SMTP 密码的读取优先级：env 优先 或 库值优先（由 SMTP_PASSWORD_ENV_FIRST 控制）。"""
    return current_app.config.get("SMTP_PASSWORD_ENV_FIRST", True)