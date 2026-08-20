// 全局站点状态：站点设置 + 登录用户（简单响应式 store，不引额外依赖）
import { reactive, readonly } from "vue";
import { apiGet, apiPost } from "./lib/api.js";

export const state = reactive({
  site: { site_name: "我的博客", site_title: "我的博客", site_note: "",
          site_description: "", accent_color: "#1a73e8",
          footer_text: "", beian_code: "", about_content: "",
          theme_mode: "system", theme_radius: "md", theme_font: "md",
          nav_style: "light", custom_css: "" },
  user: null,           // { id, username, role, is_admin, ... } 或 null
  loaded: false,
});

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
  } catch (e) { console.warn("站点设置加载失败", e); }
  try {
    const m = await apiGet("/api/auth/me");
    state.user = m.user || null;
  } catch (e) { state.user = null; }
  state.loaded = true;
}

export async function login(username, password) {
  const data = await apiPost("/api/auth/login", { username, password });
  state.user = data.user;
  return data.user;
}

export async function register(username, email, password) {
  const data = await apiPost("/api/auth/register", { username, email, password });
  state.user = data.user;
  return data.user;
}

export async function logout() {
  try { await apiPost("/api/auth/logout", {}); } catch (e) {}
  state.user = null;
}
