// Vite 配置：开发时把 /api 代理到 Flask 后端，避免跨域。
// 生产构建后是纯静态文件，由 Nginx 托管，Nginx 负责反代 /api 到 Flask（见 deploy_guide）。
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": "http://127.0.0.1:8080",
    },
  },
  build: {
    outDir: "dist_v317",
  },
});
