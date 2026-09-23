// v3.17.0：轻量 Toast（无依赖）——替代原生 alert/确认提示，右下角堆叠、自动消失。
// 用法：import { toast, toastOk, toastErr } from "../lib/toast.js";
let host = null;

function ensureHost() {
  if (host && document.body && document.body.contains(host)) return host;
  host = document.createElement("div");
  host.className = "toast-host";
  // v3.20.0 a11y 修复：**live region 必须先在 DOM 中存在**，之后插进去的内容才会被朗读。
  // 原实现是给每个 toast 现建现加 `role="status"` —— 新节点与文本同帧出现，
  // 屏幕阅读器通常**不会**播报（这是 live region 的经典陷阱，也是本仓库
  // 「零 aria-live」那条审计项的真实由来）。
  // 改为：宿主本身就是常驻的 polite live region，toast 只负责往里塞文本。
  host.setAttribute("role", "status");
  host.setAttribute("aria-live", "polite");
  // aria-atomic=false：只朗读新增的那一条，不把已有堆叠整块重读一遍
  host.setAttribute("aria-atomic", "false");
  document.body.appendChild(host);
  return host;
}

export function toast(message, type = "info", duration = 2600) {
  if (!document.body) return;
  const h = ensureHost();
  const el = document.createElement("div");
  el.className = "toast toast-" + type;
  // 不再在每条 toast 上挂 role="status"：live region 已由宿主承担，
  // 嵌套声明可能被读屏忽略或造成重复播报。
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
