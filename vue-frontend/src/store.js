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
  loaded: false,
  lang: "zh",           // v3.0.0 功能11：界面语言（zh / en）
});

// v3.0.0 功能11：轻量 i18n 词典（覆盖核心导航与常用文案）
const I18N = {
  zh: {
    "home": "首页", "archive": "归档", "stats": "统计", "about": "关于",
    "links": "友链", "square": "广场", "series": "系列", "hot_tags": "热门标签",
    "guestbook": "留言墙", "login": "登录", "register": "注册", "logout": "退出",
    "admin": "后台", "write": "写文章", "theme": "主题",
    "search_placeholder": "搜索文章…",
  },
  en: {
    "home": "Home", "archive": "Archive", "stats": "Stats", "about": "About",
    "links": "Links", "square": "Square", "series": "Series", "hot_tags": "Hot Tags",
    "guestbook": "Guestbook", "login": "Login", "register": "Register", "logout": "Logout",
    "admin": "Admin", "write": "Write", "theme": "Theme",
    "search_placeholder": "Search posts…",
  },
};

// 取翻译（缺省回退中文，再回退原 key）
export function t(key) {
  const dict = I18N[state.lang] || I18N.zh;
  return dict[key] || I18N.zh[key] || key;
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
}

// 主题美化：把后台设置转成 CSS 变量（圆角/字号/导航栏）
function applyThemeVars(s) {
  const radiusMap = { sm: "8px", md: "12px", lg: "20px" };
  const fontMap = { sm: "14px", md: "15px", lg: "17px" };
  const darkNav = s.nav_style === "dark";
  const el = document.documentElement;
  el.style.setProperty("--theme-radius", radiusMap[s.theme_radius] || "12px");
  el.style.setProperty("--theme-font-size", fontMap[s.theme_font] || "15px");
  el.style.setProperty("--nav-bg", darkNav ? "#1d2025" : "#ffffff");
  el.style.setProperty("--nav-fg", darkNav ? "#e6e8eb" : "#555555");
  el.style.setProperty("--nav-border", darkNav ? "#2a2e35" : "#ececec");
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
    injectCustomCss(s.custom_css);
    document.title = s.site_name || s.site_title || "我的博客";
    initLang(s.site_lang);  // v3.0.0 功能11：按本地/后台设置初始化语言
  } catch (e) { console.warn("站点设置加载失败", e); }
  try {
    const m = await apiGet("/api/auth/me");
    state.user = m.user || null;
    if (m.csrf_token) setCsrfToken(m.csrf_token);
  } catch (e) { state.user = null; }
  state.loaded = true;
}

export async function login(username, password) {
  const data = await apiPost("/api/auth/login", { username, password });
  state.user = data.user;
  // 登录成功后会话变化：更新 CSRF Token 缓存（auth/me 或登录响应均带新 token）
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
