# -*- coding: utf-8 -*-
"""小工具函数（v3.18.1 由单文件 utils.py 拆成包，公共 API 不变）。

各领域实现见同包子模块；本文件按“扁平命名空间”重导出全部公开与私有名，
因此既有的 ``from utils import X`` 与 ``utils.X`` 用法无需任何改动。
"""
from .timeutil import (  # noqa: F401
    BEIJING_TZ,
    to_beijing,
    fmt_bj,
)
from .render import (  # noqa: F401
    _ALLOWED_TAGS,
    _ALLOWED_ATTRS,
    clean_html,
    _upgrade_img_avif,
    render_markdown,
    _RENDER_VERSION,
    content_digest,
    render_post_html,
)
from .net import (  # noqa: F401
    _RATE,
    _REDIS_KEY_PREFIX,
    _redis,
    rate_limit,
    _parse_trusted_proxies,
    _is_trusted_proxy,
    get_client_ip,
    client_key,
)
from .slug import (  # noqa: F401
    make_slug,
    normalize_tag_key,
    split_tag_input,
    SLUG_TEMPLATE_TOKENS,
    SLUG_PRESETS,
    render_slug_template,
    apply_slug_template,
    _unique_slug_local,
)
from .text import (  # noqa: F401
    js_escape,
    count_words,
    parse_device,
    detect_bot,
)
from .security import (  # noqa: F401
    _WEAK_PASSWORDS,
    _UPPER_RE,
    _LOWER_RE,
    _DIGIT_RE,
    validate_password,
    generate_csrf_token,
    _sign_csrf,
    check_csrf_token,
    csrf_input,
)
from .settings import (  # noqa: F401
    get_setting,
    setting_bool,
)
from .web import (  # noqa: F401
    safe_redirect,
    notify_mentioned,
)
