// 调用后端 API 的封装（与 Astro 版 api.js 等价，Vue 版用 fetch）。
const API_BASE = ""; // 开发走 Vite 代理，生产走 Nginx 反代，都是相对路径

// v3.1.6：CSRF Token 缓存（会话级，登录/登出/刷新后重新获取）
let csrfToken = "";
let csrfPromise = null;

async function ensureCsrfToken() {
  if (csrfToken) return csrfToken;
  if (!csrfPromise) {
    csrfPromise = fetch(API_BASE + "/api/csrf", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then((r) => r.json())
      .then((d) => {
        csrfToken = d.csrf_token || "";
        return csrfToken;
      })
      .catch(() => "");
  }
  const tok = await csrfPromise;
  csrfPromise = null;
  return tok;
}

export function setCsrfToken(tok) {
  csrfToken = tok || "";
}

export function clearCsrfToken() {
  csrfToken = "";
  csrfPromise = null;
}

export async function apiGet(path, params) {
  let url = API_BASE + path;
  if (params) {
    const qs = new URLSearchParams(params).toString();
    if (qs) url += "?" + qs;
  }
  const resp = await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
  if (!resp.ok) throw new Error("请求失败: " + resp.status);
  return resp.json();
}

export async function apiPost(path, body) {
  // v3.1.6：POST 自动携带 CSRF Token（后端所有状态变更接口都校验）
  const tok = await ensureCsrfToken();
  const resp = await fetch(API_BASE + path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(tok ? { "X-CSRF-Token": tok } : {}),
    },
    credentials: "same-origin",
    body: JSON.stringify(body || {}),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || "请求失败: " + resp.status);
  // 若响应携带新 token（登录/初始化后），更新缓存
  if (data.csrf_token) csrfToken = data.csrf_token;
  return data;
}

// 简易 HTML 转义，渲染用户内容前调用
export function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
