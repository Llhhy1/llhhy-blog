// 应用入口
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router.js";
import "./styles/global.css";
import "./styles/responsive.css"; // v3.15.1 响应式基座（结构级防溢出/流式排版）

const app = createApp(App);

// v3.17.0：滚动渐入指令 v-reveal（IntersectionObserver 一次性触发）
// 尊重 prefers-reduced-motion / 无 IntersectionObserver 的浏览器：直接可见、不做动画。
app.directive("reveal", {
  mounted(el) {
    let reduce = false;
    try { reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}
    if (reduce || !("IntersectionObserver" in window)) return;
    el.classList.add("reveal");
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (en.isIntersecting) { el.classList.add("revealed"); io.disconnect(); break; }
      }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    io.observe(el);
  },
});

app.use(router).mount("#app");
