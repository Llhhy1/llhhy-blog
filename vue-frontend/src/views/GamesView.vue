<template>
  <div class="container games-page">
    <div class="games-head">
      <h1 class="page-title">🎮 解压小游戏</h1>
      <router-link to="/games/dev" class="dev-link">📘 开发者接入文档</router-link>
    </div>
    <p class="games-sub">轻量 · 无广告 · 沙箱运行 · 专注放松几分钟。全部游戏均为原创。</p>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!games.length" class="empty">
      <p>还没有上架的小游戏。</p>
      <p style="margin-top:8px;font-size:13px;color:#888;">游戏由站长收录审核后上架，欢迎通过<router-link to="/games/dev">接入文档</router-link>了解如何贡献原创小游戏。</p>
    </div>
    <div v-else class="games-grid">
      <div v-for="g in games" :key="g.slug" class="game-card">
        <router-link :to="`/games/${g.slug}`" class="game-cover">
          <span v-if="!g.cover" class="game-cover-fallback">{{ g.title.slice(0, 1) }}</span>
          <img v-else :src="g.cover" :alt="g.title" loading="lazy" />
        </router-link>
        <div class="game-card-body">
          <h3><router-link :to="`/games/${g.slug}`">{{ g.title }}</router-link></h3>
          <p class="game-meta">v{{ g.version }}<template v-if="g.author"> · {{ g.author }}</template></p>
          <p class="game-desc">{{ g.description }}</p>
          <router-link class="play-btn" :to="`/games/${g.slug}`">▶ 开始玩</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const games = ref([]);
const loading = ref(true);

onMounted(async () => {
  try {
    const data = await apiGet("/api/games");
    games.value = data.items || [];
  } catch (e) {
    /* 列表加载失败仅显示空态 */
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.games-head { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
.dev-link { margin-left: auto; font-size: 13px; color: var(--accent, #1a73e8); }
.games-sub { color: #777; margin-bottom: 16px; }
.games-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 16px;
}
.game-card {
  background: var(--surface, #fff); border: 1px solid #eee;
  border-radius: var(--theme-radius, 12px); overflow: hidden;
  display: flex; flex-direction: column;
  box-shadow: 0 1px 3px rgba(0,0,0,.04);
  transition: transform .18s ease, box-shadow .18s ease;
}
.game-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(20,30,50,.08); }
.game-cover {
  display: block; aspect-ratio: 16/9; overflow: hidden; background: linear-gradient(135deg,#1a73e8,#0b3d91);
}
.game-cover img { width: 100%; height: 100%; object-fit: cover; }
.game-cover-fallback {
  display: flex; align-items: center; justify-content: center; width: 100%; height: 100%;
  font-size: 48px; color: rgba(255,255,255,.85);
}
.game-card-body { padding: 12px 14px 14px; display: flex; flex-direction: column; flex: 1; }
.game-card-body h3 { margin: 0 0 2px; font-size: 16px; }
.game-card-body h3 a { color: inherit; text-decoration: none; }
.game-meta { color: #999; font-size: 12px; margin: 0 0 6px; }
.game-desc {
  color: #666; font-size: 13px; line-height: 1.5; flex: 1;
  overflow-wrap: anywhere; word-break: break-word;
}
.play-btn {
  margin-top: 10px; text-align: center; padding: 7px 0; border-radius: 8px;
  background: var(--accent, #1a73e8); color: #fff; text-decoration: none; font-size: 14px;
}
.empty { color: #999; padding: 30px 0; text-align: center; }
</style>
