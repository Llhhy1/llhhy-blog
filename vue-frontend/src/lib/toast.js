// v3.17.0：轻量 Toast（无依赖）——替代原生 alert/确认提示，右下角堆叠、自动消失。
// 用法：import { toast, toastOk, toastErr } from "../lib/toast.js";
let host = null;

function ensureHost() {
  if (host && document.body && document.body.contains(host)) return host;
  host = document.createElement("div");
  host.className = "toast-host";
  document.body.appendChild(host);
  return host;
}

export function toast(message, type = "info", duration = 2600) {
  if (!document.body) return;
  const h = ensureHost();
  const el = document.createElement("div");
  el.className = "toast toast-" + type;
  el.setAttribute("role", "status");
  el.textContent = String(message == null ? "" : message);
  h.appendChild(el);
  // 下一帧再加 show，触发过渡
  requestAnimationFrame(() => el.classList.add("show"));
  const timer = setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 220);
  }, duration);
  // 点击可提前关闭
  el.addEventListener("click", () => { clearTimeout(timer); el.remove(); });
  return el;
}

export const toastOk = (m, d) => toast(m, "success", d);
export const toastErr = (m, d) => toast(m, "danger", d);
