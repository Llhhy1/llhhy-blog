<template>
  <div class="container play-page">
    <template v-if="loading"><p class="empty">加载中…</p></template>
    <template v-else-if="notFound">
      <h1 class="page-title">游戏不存在</h1>
      <p class="empty">可能已下架或链接错误。<router-link to="/games">← 返回游戏</router-link></p>
    </template>
    <template v-else-if="g">
      <div class="play-head">
        <div>
          <h1 class="page-title">{{ g.title }}</h1>
          <p class="play-meta">v{{ g.version }}<template v-if="g.author"> · {{ g.author }}</template> · 已在隔离沙箱中运行</p>
        </div>
        <div class="play-actions">
          <button type="button" class="btn-ghost" @click="toggleFull">⛶ 全屏</button>
          <router-link class="btn-ghost" to="/games">← 返回游戏厅</router-link>
        </div>
      </div>
      <div class="frame-wrap">
        <iframe
          :src="frameSrc"
          sandbox="allow-scripts"
          allow="autoplay; fullscreen; clipboard-write"
          class="game-frame"
          title="游戏沙箱"
          @load="loadedFrame = true"
        ></iframe>
      </div>
      <details class="sandbox-note" :open="false">
        <summary>🛡️ 关于安全沙箱（点击展开）</summary>
        <p>第三方/原创小游戏在本页面 <code>iframe sandbox</code>（不授予 same-origin）内运行，
           配合资源响应头的 <code>CSP sandbox</code>：游戏读不到本站 Cookie 与登录态、不能访问本站接口、
           不能跳出到外站。上传前均经过静态扫描与（可选）大模型代码审计。</p>
      </details>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../lib/api.js";

const route = useRoute();
const g = ref(null);
const notFound = ref(false);
const loading = ref(true);
const loadedFrame = ref(false);

const frameSrc = computed(() =>
  g.value ? `/api/game-files/${g.value.slug}/${g.value.entry || "index.html"}` : ""
);

onMounted(async () => {
  try {
    const slug = route.params.slug;
    const data = await apiGet(`/api/game/${encodeURIComponent(slug)}`);
    if (!data || data.error) throw new Error("none");
    g.value = data;
    document.title = `${data.title} · ${(data.version || "")} - 游戏`;
  } catch (e) {
    notFound.value = true;
  } finally {
    loading.value = false;
  }
});

function toggleFull() {
  const f = document.querySelector(".game-frame");
  if (!f) return;
  if (!document.fullscreenElement) f.requestFullscreen?.().catch(() => {});
  else document.exitFullscreen?.().catch(() => {});
}
</script>

<style scoped>
.play-head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.play-head .page-title { margin-bottom: 2px; }
.play-actions { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }
.btn-ghost {
  border: 1px solid #ddd; background: none; color: inherit; padding: 6px 12px;
  border-radius: 8px; cursor: pointer; font-size: 13px; text-decoration: none;
}
.play-meta { color: #888; font-size: 13px; margin: 0 0 10px; }
.frame-wrap {
  border: 1px solid #e3e3e3; border-radius: 12px; overflow: hidden;
  background: #0b1220;
}
.game-frame {
  display: block; width: 100%;
  height: min(76vh, 900px); min-height: 420px;
  border: 0; background: transparent;
}
/* 手机优先：竖屏拉满，横屏适度限高 */
@media (max-width: 640px) {
  .game-frame { height: calc(100dvh - 220px); min-height: 60vh; }
}
.sandbox-note { margin-top: 12px; color: #777; font-size: 13px; }
.sandbox-note code { background: #f0f0f0; padding: 1px 5px; border-radius: 4px; }
.empty { color: #999; padding: 20px 0; }
</style>
