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
});

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
