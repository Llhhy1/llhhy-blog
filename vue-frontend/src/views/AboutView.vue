<template>
  <div class="container">
    <h1 class="page-title">关于</h1>
    <div class="about-content" v-html="html"></div>

    <!-- v4.7.5 生态统计 -->
    <section class="eco-box" v-if="eco.total > 0 || online > 0">
      <h2 class="eco-h">🌐 生态</h2>
      <p class="eco-line" v-if="online > 0">
        当前有 <b>{{ online }}</b> 位访客正在浏览本站
        <span class="eco-note">（近 10 分钟独立访客数）</span>
      </p>
      <p class="eco-line" v-if="eco.total > 0">
        已知有 <b>{{ eco.total }}</b> 个站点在用本系统
        <span class="eco-note" v-if="eco.active > 0">，其中 {{ eco.active }} 个在过去 24 小时有活动</span>
      </p>
      <ul class="eco-list" v-if="eco.sites && eco.sites.length">
        <li v-for="(s, i) in eco.sites" :key="i">
          <a :href="safeUrl(s.url)" target="_blank" rel="noopener nofollow">{{ s.url }}</a>
          <span class="eco-tag" v-if="s.version">v{{ s.version }}</span>
        </li>
      </ul>
      <p class="eco-note eco-disclaimer">
        站点由使用者<b>自愿</b>上报，仅包含站点地址与版本号，不含任何访客数据。
      </p>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const html = ref("<p>暂无简介。</p>");
const online = ref(0);
const eco = ref({ total: 0, active: 0, sites: [] });

/** 只放行 http/https —— 站点地址是「自报」的，不能想当然当可信。 */
function safeUrl(u) {
  const s = String(u || "");
  return /^https?:\/\//i.test(s) ? s : "#";
}

onMounted(async () => {
  try {
    const s = await apiGet("/api/site");
    html.value = s.about_content || html.value;
  } catch (e) {}
  try {
    const o = await apiGet("/api/stats/online");
    online.value = Number(o.online) || 0;
  } catch (e) {}
  try {
    const e = await apiGet("/api/ecosystem/stats");
    eco.value = e || { total: 0, active: 0, sites: [] };
  } catch (e) {}
});
</script>

<style scoped>
.eco-box { margin: 28px 0 0; padding: 18px 20px; border: 1px solid var(--border, #ececec);
  border-radius: 12px; background: var(--surface, #fff); }
.eco-h { margin: 0 0 10px; font-size: 15px; font-weight: 500; color: var(--accent, #1a73e8); }
.eco-line { margin: 4px 0; font-size: 14px; color: var(--text, #2c2c2c); }
.eco-line b { color: var(--accent, #1a73e8); font-size: 16px; }
.eco-note { color: var(--text-muted, #9aa0a6); font-size: 12px; }
.eco-list { margin: 10px 0 0; padding: 0; list-style: none; display: flex;
  flex-wrap: wrap; gap: 8px; }
.eco-list li { font-size: 13px; }
.eco-list a { color: var(--text, #2c2c2c); text-decoration: none;
  border-bottom: 1px dotted var(--border, #d5d5d5); }
.eco-list a:hover { color: var(--accent, #1a73e8); }
.eco-tag { margin-left: 4px; font-size: 11px; color: var(--text-muted, #9aa0a6); }
.eco-disclaimer { margin: 12px 0 0; }
</style>
