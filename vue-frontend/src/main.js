// 应用入口
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router.js";
import "./styles/global.css";
import "./styles/responsive.css"; // v3.15.1 响应式基座（结构级防溢出/流式排版）

createApp(App).use(router).mount("#app");
