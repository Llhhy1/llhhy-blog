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
      // /static 也必须走后端：自托管字体（/static/fonts/kinghua.css）与壁纸/配图
      //（/static/uploads/…）都住在 Flask 的 static 目录里。少了这条，本地 dev 看到的
      // 是「字体没生效、壁纸 404」，与线上表现不一致，容易误判成实现有问题。
      "/static": "http://127.0.0.1:8080",
    },
  },
  build: {
    outDir: "_vite_build30",
  },
});
