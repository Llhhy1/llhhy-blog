// 全局站点状态：站点设置 + 登录用户（简单响应式 store，不引额外依赖）
import { reactive, readonly } from "vue";
import { apiGet, apiPost, setCsrfToken, clearCsrfToken } from "./lib/api.js";

export const state = reactive({
  site: { site_name: "我的博客", site_title: "我的博客", site_note: "",
          site_description: "", accent_color: "#1a73e8",
          footer_text: "", beian_code: "", about_content: "",
          theme_mode: "system", theme_radius: "md", theme_font: "md",
          nav_style: "light", custom_css: "", site_lang: "zh" },
  user: null,           // { id, username, role, is_admin, ... } 或 null
  reader: { points: 0, badges: [] },  // v3.21.0 gamification：当前读者积分与勋章
  loaded: false,
  lang: "zh",           // v3.0.0 功能11：界面语言（zh / en）
  contentLang: "zh",    // v3.21.0 内容多语言：当前阅读的内容语言（译文切换驱动，独立于 UI i18n）
  installPrompt: null,  // v3.21.0 PWA：浏览器 beforeinstallprompt 事件（可安装时非 null）
  oauthProviders: [],   // v3.21.0 OAuth：后端已配置的第三方登录 provider（空=未配置，按钮不显）
});

// v3.0.0 功能11：轻量 i18n 词典（覆盖核心导航与常用文案）
const I18N = {
  zh: {
    "home": "首页", "archive": "归档", "stats": "统计", "about": "关于", "docs": "文档",
    "links": "友链", "square": "广场", "series": "系列", "hot_tags": "热门标签",
    "ecosystem": "生态",
    "gallery": "相册", "gallery_sub": "一次旅程、一段日子的照片与视频归档",
    "all": "全部", "images": "图片", "videos": "视频", "untitled": "未命名",
    "loading": "加载中…", "load_more": "加载更多", "gallery_empty": "这里还没有公开的相册",
    "items": "项", "album_missing": "相册不存在，或未公开",
    "album_intro": "行程概览", "album_tips": "小提示", "album_loose": "更多",
    "close": "关闭", "prev": "上一张", "next": "下一张",
    "guestbook": "留言墙", "login": "登录", "register": "注册", "logout": "退出",
    "admin": "后台", "write": "写文章", "theme": "主题",
    "search_placeholder": "搜索文章…",
    "annual": "回顾", "social": "社交", "more": "更多",
    "notifications": "通知", "unread": "未读", "all_read": "全部已读", "no_notifications": "暂无通知",
    "blog": "博客", "back_to_top": "回到顶部",
    "skip_to_content": "跳到正文",
    "open_menu": "打开菜单", "close_menu": "关闭菜单", "nav_menu": "导航菜单",
    "toolbox": "工具箱",
    "toggle_theme": "切换亮暗主题", "switch_lang": "切换语言",
    "install_app": "安装应用",
    "login_github": "用 GitHub 登录", "login_google": "用 Google 登录",
    "oauth_being_redirected": "正在跳转到授权页…",
    /* v4.8.1 全局组件（侧栏 / 天气 / App 壳）—— 这些每页都可见，英文界面必须跟着切 */
    "site_search": "站内搜索", "search": "搜索", "search_go": "搜索",
    "email_subscribe": "📬 邮件订阅",
    "sub_tip": "新文章发布第一时间邮件通知你",
    "email_placeholder": "输入邮箱地址",
    "subscribe": "订阅", "sub_busy": "提交中…", "sub_done": "已订阅 ✓",
    "email_required": "请输入邮箱地址",
    "subscribe_ok": "订阅成功", "subscribe_fail": "订阅失败，请稍后再试",
    "categories": "分类", "no_categories": "暂无分类",
    "tags": "标签", "no_tags": "暂无标签",
    "recent_posts": "最新文章", "no_posts": "暂无文章",
    "hot_posts": "🔥 热门文章", "no_data": "暂无数据", "reads": "读",
    "site_stats": "站点统计",
    "stats_line": "文章 {p} 篇 · 评论 {c} 条",
    "friend_links": "友情链接",
    /* v5.3.0 订阅入口（页脚 / 侧栏 / /feed 页共用） */
    "rss_entry": "📡 RSS 订阅",
    "rss_tip": "用阅读器订阅，新文自动推送",
    "rss_title": "订阅本站",
    "rss_intro": "订阅后，我在这里发的新文章会自动出现在你的阅读器里 —— 不用专门来刷首页，也不会错过更新。",
    "rss_copy": "复制地址", "rss_copied": "已复制 ✓", "rss_copy_fail": "复制失败，请手动选中地址",
    "rss_open": "打开",
    "rss_pick": "两个地址内容完全一样，挑你阅读器支持的那个就行（绝大多数阅读器两个都支持）。",
    "rss_how": "怎么用",
    "rss_s1": "复制上面的地址；",
    "rss_s2": "打开你的 RSS 阅读器，找到「添加订阅源 / 添加频道」；",
    "rss_s3": "把地址粘进去并确认 —— 之后新文章会自动进你的订阅流。",
    "rss_latest": "源里最近的文章",
    "rss_empty": "暂无文章",
    "weather": "天气", "loading": "加载中…",
    "weather_city_ph": "输入城市，如 上海",
    "query": "查询", "use_my_location": "使用我的位置", "locate": "📍 定位",
    "net_error": "网络错误，请稍后再试",
    "city_required": "请输入城市名",
    "locate_unsupported": "当前环境不支持定位，已显示默认城市",
    "locating": "正在获取位置…",
    "locate_failed": "定位失败，已显示默认城市",
    "unknown": "未知",
    "online_count": "{n} 人正在浏览",
    "plugin_sidebar": "插件",
    "close": "关闭", "close_note": "关闭便签",
    "w_0": "晴", "w_1": "晴间多云", "w_2": "多云", "w_3": "阴",
    "w_45": "雾", "w_48": "雾凇",
    "w_51": "毛毛雨", "w_53": "小雨", "w_55": "中雨",
    "w_61": "小雨", "w_63": "中雨", "w_65": "大雨",
    "w_71": "小雪", "w_73": "雪", "w_75": "大雪",
    "w_80": "阵雨", "w_81": "阵雨", "w_82": "强阵雨",
    "w_95": "雷阵雨", "w_96": "雷阵雨伴冰雹", "w_99": "强雷暴",
  },
  en: {
    "home": "Home", "archive": "Archive", "stats": "Stats", "about": "About", "docs": "Docs",
    "links": "Links", "square": "Square", "series": "Series", "hot_tags": "Hot Tags",
    "ecosystem": "Ecosystem",
    "gallery": "Albums", "gallery_sub": "Photos and videos from one trip or one stretch of time",
    "all": "All", "images": "Images", "videos": "Videos", "untitled": "Untitled",
    "loading": "Loading…", "load_more": "Load more", "gallery_empty": "No public albums yet",
    "items": "items", "album_missing": "Album not found, or not public",
    "album_intro": "Overview", "album_tips": "Tips", "album_loose": "More",
    "close": "Close", "prev": "Previous", "next": "Next",
    "guestbook": "Guestbook", "login": "Login", "register": "Register", "logout": "Logout",
    "admin": "Admin", "write": "Write", "theme": "Theme",
    "search_placeholder": "Search posts…",
    "annual": "Review", "social": "Social", "more": "More",
    "notifications": "Notifications", "unread": "unread", "all_read": "Mark all read", "no_notifications": "No notifications",
    "blog": "Blog", "back_to_top": "Back to top",
    "skip_to_content": "Skip to content",
    "open_menu": "Open menu", "close_menu": "Close menu", "nav_menu": "Navigation",
    "toolbox": "Toolbox",
    "toggle_theme": "Toggle dark mode", "switch_lang": "Switch language",
    "install_app": "Install app",
    "login_github": "Sign in with GitHub", "login_google": "Sign in with Google",
    "oauth_being_redirected": "Redirecting to authorization…",
    /* v4.8.1 全局组件（与 zh 键一一对应；缺键时 t() 会退回中文，所以这里必须齐平） */
    "site_search": "Site Search", "search": "Search", "search_go": "Search",
    "email_subscribe": "📬 Email Updates",
    "sub_tip": "Get new posts by email the moment they publish",
    "email_placeholder": "Your email address",
    "subscribe": "Subscribe", "sub_busy": "Submitting…", "sub_done": "Subscribed ✓",
    "email_required": "Please enter your email",
    "subscribe_ok": "Subscribed", "subscribe_fail": "Subscription failed, please retry",
    "categories": "Categories", "no_categories": "No categories",
    "tags": "Tags", "no_tags": "No tags",
    "recent_posts": "Recent Posts", "no_posts": "No posts",
    "hot_posts": "🔥 Popular", "no_data": "No data yet", "reads": "reads",
    "site_stats": "Site Stats",
    "stats_line": "{p} posts · {c} comments",    "friend_links": "Links",
    /* v5.3.0 subscribe entry (footer / sidebar / /feed page) */
    "rss_entry": "📡 RSS Feed",
    "rss_tip": "Follow in any RSS reader",
    "rss_title": "Subscribe",
    "rss_intro": "Subscribe once and new posts show up in your reader automatically — no need to keep checking back.",
    "rss_copy": "Copy URL", "rss_copied": "Copied ✓", "rss_copy_fail": "Copy failed, please select the URL manually",
    "rss_open": "Open",
    "rss_pick": "Both URLs carry the same content — pick whichever your reader supports (most support both).",
    "rss_how": "How to subscribe",
    "rss_s1": "Copy one of the URLs above;",
    "rss_s2": "Open your RSS reader and find “Add feed” / “Add channel”;",
    "rss_s3": "Paste the URL and confirm — new posts will flow in from then on.",
    "rss_latest": "Latest in the feed",
    "rss_empty": "No posts yet",
    "weather": "Weather", "loading": "Loading…",
    "weather_city_ph": "City, e.g. Shanghai",
    "query": "Search", "use_my_location": "Use my location", "locate": "📍 Locate",
    "net_error": "Network error, please retry",
    "city_required": "Please enter a city",
    "locate_unsupported": "Location unavailable; showing default city",
    "locating": "Getting location…",
    "locate_failed": "Location failed; showing default city",
    "unknown": "Unknown",
    "online_count": "{n} online",
    "plugin_sidebar": "Plugins",
    "close": "Close", "close_note": "Dismiss note",
    "w_0": "Clear", "w_1": "Partly Cloudy", "w_2": "Cloudy", "w_3": "Overcast",
    "w_45": "Fog", "w_48": "Rime",
    "w_51": "Light Drizzle", "w_53": "Light Rain", "w_55": "Moderate Rain",
    "w_61": "Light Rain", "w_63": "Moderate Rain", "w_65": "Heavy Rain",
    "w_71": "Light Snow", "w_73": "Snow", "w_75": "Heavy Snow",
    "w_80": "Showers", "w_81": "Showers", "w_82": "Strong Showers",
    "w_95": "Thunderstorm", "w_96": "Thunderstorm w/ Hail", "w_99": "Severe Storm",
  },
};

// 取翻译（缺省回退中文，再回退原 key）。vars 可选：`t('stats_line', {p: 8, c: 12})`
export function t(key, vars) {
  const dict = I18N[state.lang] || I18N.zh;
  let s = dict[key] || I18N.zh[key] || key;
  if (vars) {
    for (const k in vars) {
      s = s.split("{" + k + "}").join(String(vars[k]));
    }
  }
  return s;
}

// 切换语言并持久化（v3.0.0 功能11）
export function setLang(lang) {
  if (!I18N[lang]) lang = "zh";
  state.lang = lang;
  try { localStorage.setItem("lang", lang); } catch (e) {}
  document.documentElement.setAttribute("lang", lang === "en" ? "en" : "zh-CN");
}

// 初次加载时按优先级决定语言：本地选择 > 后台 site_lang > 默认中文
export function initLang(siteLang) {
  let lang = "zh";
  try {
    const saved = localStorage.getItem("lang");
    if (saved && I18N[saved]) lang = saved;
    else if (siteLang && I18N[siteLang]) lang = siteLang;
  } catch (e) {}
  state.lang = lang;
  document.documentElement.setAttribute("lang", lang === "en" ? "en" : "zh-CN");
  // v3.21.0 内容多语言：恢复上次选择的内容语言（列表 ?lang= 与文章 <html lang> 用）
  try {
    const c = localStorage.getItem("contentLang");
    if (c) state.contentLang = c;
  } catch (e) {}
}

// v3.21.0 内容多语言：内容语言（与 UI i18n 解耦，由译文切换器驱动）
export function setContentLang(lang) {
  if (!lang) lang = "zh";
  state.contentLang = lang;
  try { localStorage.setItem("contentLang", lang); } catch (e) {}
  applyContentLangAttr(lang);
}

// 把内容语言映射到 <html lang>（zh → zh-CN，其余直接用代码）
export function applyContentLangAttr(lang) {
  const map = { zh: "zh-CN" };
  const v = map[lang] || lang || "zh-CN";
  document.documentElement.setAttribute("lang", v);
}

// 主题美化：把后台设置转成 CSS 变量（圆角/字号）
// v3.17.0：不再在此写导航变量——否则内联 --nav-bg 会压死 [data-theme=dark]，
// 造成「一调深色模式顶部就一整条白色」。导航改由主题包 token 或 applyNavVars 提供。
function applyThemeVars(s) {
  const radiusMap = { sm: "8px", md: "12px", lg: "20px" };
  const fontMap = { sm: "14px", md: "15px", lg: "17px" };
  const el = document.documentElement;
  el.style.setProperty("--theme-radius", radiusMap[s.theme_radius] || "12px");
  el.style.setProperty("--theme-font-size", fontMap[s.theme_font] || "15px");
}

// v3.17.0：无完整主题包时的导航兜底（按后台 nav_style 设置）
function applyNavVars(s) {
  const darkNav = (s && s.nav_style) === "dark";
  const el = document.documentElement;
  el.style.setProperty("--nav-bg", darkNav ? "#1d2025" : "#ffffff");
  el.style.setProperty("--nav-fg", darkNav ? "#e6e8eb" : "#555555");
  el.style.setProperty("--nav-border", darkNav ? "#2a2e35" : "#ececec");
}

// v3.16.0 主题中心：把完整 token 映射（颜色+圆角+字号+导航）整体写入 :root
// v3.17.0 修复：themes.py 的 key 用下划线（nav_bg/surface_2…），而 CSS 变量用短横线
// （--nav-bg/--surface-2）；原先原样写 "--"+k 得到无效变量名，导致主题包换肤从未生效
// （也是深色白条的成因之一）。现统一转换，并在写入前清除上一轮变量，避免亮/暗切换残留。
let _appliedTokenNames = [];
export function applyThemeTokens(map) {
  if (!map) return;
  const el = document.documentElement;
  for (const name of _appliedTokenNames) el.style.removeProperty(name);
  _appliedTokenNames = [];
  for (const k in map) {
    if (Object.prototype.hasOwnProperty.call(map, k)) {
      const name = "--" + k.replace(/_/g, "-");
      el.style.setProperty(name, map[k]);
      _appliedTokenNames.push(name);
    }
  }
}

// v3.16.0：按当前/指定模式应用「当前激活主题」的亮或暗 token（含导航变量，覆盖默认暗色块）
export function applyActiveTheme(mode) {
  const m = mode || (document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");
  const map = m === "dark" ? state.site.theme_dark_tokens : state.site.theme_tokens;
  if (map) {
    applyThemeTokens(map);
  } else {
    // 无完整主题包（默认/旧版）：回退圆角/字号 + 按 nav_style 设导航变量
    applyThemeVars(state.site);
    applyNavVars(state.site);
  }
}

// 默认主题：用户没手动切过时，按后台 theme_mode 定（system=跟随系统）
function applyDefaultTheme(s) {
  try { if (localStorage.getItem("theme")) return; } catch (e) {}
  const mode = s.theme_mode || "system";
  const dark = mode === "dark" ||
    (mode === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
}

// 自定义 CSS 注入（覆盖样式，优先级最高）
function injectCustomCss(css) {
  if (!css) return;
  let st = document.getElementById("site-custom-css");
  if (!st) {
    st = document.createElement("style");
    st.id = "site-custom-css";
    document.head.appendChild(st);
  }
  st.textContent = css;
}

// 一次性加载站点设置 + 登录态
let inited = false;
export async function initSite() {
  if (inited) return;
  inited = true;
  try {
    const s = await apiGet("/api/site");
    Object.assign(state.site, s);
    // 主题色注入
    document.documentElement.style.setProperty("--accent", s.accent_color || "#1a73e8");
    applyThemeVars(s);
    applyDefaultTheme(s);
    // v3.16.0 主题中心：若有完整主题包，整体换肤（亮/暗按当前模式）
    applyActiveTheme();
    injectCustomCss(s.custom_css);
    document.title = s.site_name || s.site_title || "我的博客";
    initLang(s.site_lang);  // v3.0.0 功能11：按本地/后台设置初始化语言
  } catch (e) { console.warn("站点设置加载失败", e); }
  try {
    const m = await apiGet("/api/auth/me");
    state.user = m.user || null;
    if (m.csrf_token) setCsrfToken(m.csrf_token);
  } catch (e) { state.user = null; }
  await initReader();  // v3.21.0 gamification：拉取积分/勋章（发请求即创建/命中读者档案）
  state.loaded = true;
}

export async function login(username, password) {
  const data = await apiPost("/api/auth/login", { username, password });
  // v3.21.0 2FA：账号已绑两步验证时，第一步只建立「挂起态」，不建立登录态。
  // 返回标记对象（而非 user），由登录页转入第二步骤；此路径下 state.user 保持 null。
  if (data && data.twofa_required) {
    return { twofa_required: true, username: data.username || username };
  }
  state.user = data.user;
  // 登录成功后会话变化：更新 CSRF Token 缓存（auth/me 或登录响应均带新 token）
  if (data.csrf_token) setCsrfToken(data.csrf_token);
  return data.user;
}

// v3.21.0 2FA：登录第二步——提交验证器 App 的 6 位动态码（或恢复码）完成登录。
export async function verify2fa(code) {
  const data = await apiPost("/api/auth/2fa/verify", { code });
  state.user = data.user;
  if (data.csrf_token) setCsrfToken(data.csrf_token);
  return data.user;
}

export async function register(username, email, password, captcha = "") {
  const data = await apiPost("/api/auth/register", { username, email, password, captcha });
  state.user = data.user;
  if (data.csrf_token) setCsrfToken(data.csrf_token);
  return data.user;
}

export async function logout() {
  try { await apiPost("/api/auth/logout", {}); } catch (e) {}
  state.user = null;
  clearCsrfToken();
}

// v3.21.0 gamification：拉取当前读者积分与勋章（服务器用 cookie 标识匿名读者）。
// 任何访问都会创建/命中读者档案（便于正确累计积分），不影响主流程。
export async function initReader() {
  try {
    const d = await apiGet("/api/reader/me");
    if (d && d.reader) state.reader = d.reader;
  } catch (e) {}
}

// v3.21.0 OAuth：拉取已配置的第三方登录 provider（config-gated，未配置则为空数组，
// 前端据此显隐「用 GitHub/Google 登录」按钮，绝不展示不可用的入口）。
export async function initOAuthProviders() {
  try {
    const d = await apiGet("/api/auth/oauth/providers");
    if (d && Array.isArray(d.providers)) state.oauthProviders = d.providers;
  } catch (e) { state.oauthProviders = []; }
}

// v3.21.0 OAuth：跳转到某 provider 授权页（start 返回 authorize_url）。
export async function startOAuth(provider) {
  const d = await apiGet("/api/auth/oauth/" + provider + "/start");
  if (d && d.authorize_url) {
    window.location.href = d.authorize_url;  // 整页跳转，callback 用 ?oauth=ok|error 回首页
  } else {
    throw new Error("oauth_start_failed");
  }
}

// v3.21.0 PWA：缓存浏览器安装提示事件；用户在 UI 点击「安装」时再触发（一次性）
export function setInstallPrompt(e) {
  state.installPrompt = e || null;
}

export async function installApp() {
  const e = state.installPrompt;
  if (!e) return false;
  try {
    e.prompt();
    await e.userChoice;
  } catch (err) {
    return false;
  } finally {
    state.installPrompt = null;
  }
  return true;
}
