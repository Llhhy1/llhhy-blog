/**
 * v3.17.9：社交平台元信息（图标 / 主题色 / 点击行为）——前台社交墙共用，零依赖（emoji 图标）。
 *
 * action：
 *   link   —— 直接新窗口打开 url
 *   qq     —— url 为纯数字（QQ 号）时改为「点击复制」；否则按链接打开（含 wpa.qq.com 快捷加好友）
 *   wechat —— url 为图片地址时展示二维码；否则视为微信号，「点击复制」
 *   mail   —— 自动补 mailto:
 */
const RULES = [
  { k: ["qq"], icon: "🐧", label: "QQ", color: "#12b7f5", action: "qq" },
  { k: ["微信", "wechat", "weixin", "vx"], icon: "💚", label: "微信", color: "#07c160", action: "wechat" },
  { k: ["公众号", "mp", "official"], icon: "📰", label: "公众号", color: "#07c160", action: "wechat" },
  { k: ["微博", "weibo"], icon: "🔴", label: "微博", color: "#e6162d", action: "link" },
  { k: ["bilibili", "b站", "哔哩"], icon: "📺", label: "B站", color: "#fb7299", action: "link" },
  { k: ["知乎", "zhihu"], icon: "🀄", label: "知乎", color: "#0084ff", action: "link" },
  { k: ["小红书", "xiaohongshu", "redbook", "xhs"], icon: "📕", label: "小红书", color: "#ff2442", action: "link" },
  { k: ["抖音", "douyin", "tiktok"], icon: "🎵", label: "抖音", color: "#161823", action: "link" },
  { k: ["github"], icon: "🐙", label: "GitHub", color: "#24292f", action: "link" },
  { k: ["gitee", "gitlab", "gitcode"], icon: "🧩", label: "代码仓库", color: "#fc6d26", action: "link" },
  { k: ["邮箱", "mail", "email"], icon: "✉️", label: "邮箱", color: "#ea4335", action: "mail" },
  { k: ["rss", "订阅", "feed"], icon: "📡", label: "RSS", color: "#f26522", action: "link" },
  { k: ["telegram", "tg"], icon: "✈️", label: "Telegram", color: "#229ed9", action: "link" },
  { k: ["twitter", "推特", " x", "x("], icon: "🐦", label: "X", color: "#1d9bf0", action: "link" },
  { k: ["mastodon", "长毛象"], icon: "🐘", label: "Mastodon", color: "#6364ff", action: "link" },
  { k: ["掘金", "juejin"], icon: "⛏️", label: "掘金", color: "#1e80ff", action: "link" },
  { k: ["csdn"], icon: "📘", label: "CSDN", color: "#fc5531", action: "link" },
  { k: ["豆瓣", "douban"], icon: "🎬", label: "豆瓣", color: "#2e963d", action: "link" },
  { k: ["youtube", "油管"], icon: "▶️", label: "YouTube", color: "#ff0000", action: "link" },
  { k: ["雨雀", "语雀", "yuque"], icon: "📓", label: "语雀", color: "#25b864", action: "link" },
];

export function socialMeta(platform) {
  const p = String(platform || "").toLowerCase();
  for (const r of RULES) {
    if (r.k.some((k) => p.includes(k.trim()) && k.trim())) return r;
  }
  return { icon: "🔗", label: platform || "链接", color: "", action: "link" };
}

/** 把后台配置的一条账号转成前端展示模型：决定 href（打开）还是 copy（复制） */
export function toSocialItem(a) {
  const meta = socialMeta(a.platform);
  const url = String(a.url || "").trim();
  const digits = /^\d{5,12}$/.test(url);
  const isImg = /^https?:\/\//i.test(url) && /\.(png|jpe?g|gif|webp|svg|bmp)(\?|#|$)/i.test(url);
  let href = url;
  let tip = a.handle || url;
  let mode = "link";

  if (meta.action === "qq") {
    if (digits) {
      href = "";
      tip = "点击复制 QQ 号";
      mode = "copy";
    } else if (!/^https?:\/\//i.test(url)) {
      href = "https://wpa.qq.com/msgrd?v=3&uin=" + encodeURIComponent(url);
    }
  } else if (meta.action === "wechat") {
    if (isImg) {
      tip = "点击查看二维码";
    } else {
      href = "";
      tip = "点击复制微信号";
      mode = "copy";
    }
  } else if (meta.action === "mail") {
    href = /^mailto:/i.test(url) ? url : "mailto:" + url;
  }

  return { ...a, meta, url, href, tip, mode };
}

export default socialMeta;
