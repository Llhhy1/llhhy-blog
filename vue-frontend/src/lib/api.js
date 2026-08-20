// 调用后端 API 的封装（与 Astro 版 api.js 等价，Vue 版用 fetch）。
const API_BASE = ""; // 开发走 Vite 代理，生产走 Nginx 反代，都是相对路径

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
  const resp = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body || {}),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || "请求失败: " + resp.status);
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
