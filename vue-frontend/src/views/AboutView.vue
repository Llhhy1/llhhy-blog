<template>
  <div class="container">
    <h1 class="page-title">关于</h1>
    <div class="about-content" v-html="html"></div>

    <!-- 仅保留本站「实时在线访客」指标（与生态注册表无关，是本站 VisitLog 近似值）。
         跨站点的「生态统计」已独立成 /ecosystem 页面。 -->
    <section class="live-box" v-if="online > 0">
      <p class="live-line">
        当前有 <b>{{ online }}</b> 位访客正在浏览本站
        <span class="live-note">（近 10 分钟独立访客数，近似值）</span>
      </p>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const html = ref("<p>暂无简介。</p>");
const online = ref(0);

onMounted(async () => {
  try {
    const s = await apiGet("/api/site");
    html.value = s.about_content || html.value;
  } catch (e) {}
  try {
    const o = await apiGet("/api/stats/online");
    online.value = Number(o.online) || 0;
  } catch (e) {}
});
</script>

<style scoped>
.live-box { margin: 28px 0 0; padding: 14px 20px; border: 1px solid var(--border, #ececec);
  border-radius: 12px; background: var(--surface, #fff); }
.live-line { margin: 0; font-size: 14px; color: var(--text, #2c2c2c); }
.live-line b { color: var(--accent, #196ddd); font-size: 16px; }
.live-note { color: var(--text-muted, #9aa0a6); font-size: 12px; }
</style>
