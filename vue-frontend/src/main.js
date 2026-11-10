// 应用入口
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router.js";
import { setInstallPrompt } from "./store.js";
import "./styles/global.css";
import "./styles/responsive.css"; // v3.15.1 响应式基座（结构级防溢出/流式排版）
// v5.0.0 统一观感层：**必须在 responsive.css 之后** —— 它要覆盖
// responsive.css:75 的 .page-title 字号，顺序反了大标题就不会生效。
import "./styles/look.css";

// v3.21.0 PWA：仅生产构建注册 Service Worker（dev 不注册，避免缓存干扰 HMR）
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
  // 捕获浏览器「可安装」提示，交给 UI 在合适时机触发（避免默认一次性弹窗流失）
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    setInstallPrompt(e);
  });
  window.addEventListener("appinstalled", () => setInstallPrompt(null));
}

const app = createApp(App);

// v3.17.0 建、v5.8.0 升级：滚动渐入指令 v-reveal。
// 旧实现每个元素各 new 一个 IntersectionObserver（首页 8 卡 = 8 个实例），且
// 组件卸载后不 unobserve —— 路由反复进出会积累观察器。现改为模块级单例 +
// unmounted 解绑；binding.value 传列表序号，用来做 55ms 递增的错峰入场。
// 尊重 prefers-reduced-motion / 无 IntersectionObserver / data-motion=off：
// 直接可见、不做动画（off 档另在 CSS 里兜底，防止属性尚未注入时先闪一下）。
let _revealIO = null;
function _revealObserver() {
  if (_revealIO) return _revealIO;
  _revealIO = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (!en.isIntersecting) continue;
      en.target.classList.add("revealed");
      _revealIO.unobserve(en.target);   // 一次性触发，触发后即解绑
    }
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
  return _revealIO;
}
app.directive("reveal", {
  mounted(el, binding) {
    let reduce = false;
    try { reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}
    if (reduce || !("IntersectionObserver" in window)) return;
    const idx = Number(binding.value) || 0;
    // 封顶 7 档：长列表后面不再继续累加，避免第 20 张卡要等 1s 才出现。
    el.style.setProperty("--reveal-delay", Math.min(idx, 7) * 55 + "ms");
    el.classList.add("reveal");
    _revealObserver().observe(el);
  },
  unmounted(el) {
    if (_revealIO) _revealIO.unobserve(el);
  },
});

app.use(router).mount("#app");
