<template>
  <div class="container">
    <h1 class="page-title">🌐 生态</h1>
    <p class="eco-intro">
      本系统被部署到了哪些地方？下面由「部署实例主动上报」的数据回答。每一行代表一个正在运行的实例。
    </p>

    <div v-if="loading" class="eco-loading">加载中…</div>
    <template v-else>
      <div class="eco-summary">
        <div class="eco-stat">
          <span class="eco-num">{{ eco.total }}</span>
          <span class="eco-label">在用站点总数</span>
        </div>
        <div class="eco-stat">
          <span class="eco-num">{{ eco.active }}</span>
          <span class="eco-label">近 24 小时活跃</span>
        </div>
      </div>

      <p v-if="!eco.sites.length" class="eco-empty">暂时没有公开的站点在列。</p>
      <ul v-else class="eco-list">
        <li v-for="(s, i) in eco.sites" :key="i" class="eco-item">
          <a v-if="safeUrl(s.url)" :href="safeUrl(s.url)" target="_blank" rel="noopener nofollow" class="eco-url">{{ s.url }}</a>
          <span v-else class="eco-url eco-anon">匿名站点（未公开地址）</span>
          <span class="eco-tag" v-if="s.version">v{{ s.version }}</span>
          <span class="eco-time">首次 {{ s.first_seen || "—" }} · 最近 {{ s.last_seen || "—" }}</span>
        </li>
      </ul>

      <p class="eco-note">
        数据由使用者<b>自愿上报</b>：仅包含站点地址与版本号，不含任何访客数据、文章内容或账号信息；上报可随时在后台关闭。
        超过 24 小时没有心跳的站点会被<b>自动移除</b>，因此上面的数字只反映「当前仍在运行」的实例。
      </p>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const loading = ref(true);
const eco = ref({ total: 0, active: 0, sites: [] });

/** 只放行 http/https —— 站点地址是「自报」的，不能想当然当可信。 */
function safeUrl(u) {
  const s = String(u || "");
  return /^https?:\/\//i.test(s) ? s : "";
}

onMounted(async () => {
  try {
    const e = await apiGet("/api/ecosystem/stats");
    eco.value = e || { total: 0, active: 0, sites: [] };
  } catch (e) {}
  loading.value = false;
});
</script>

<style scoped>
.eco-intro { margin: 0 0 18px; font-size: 14px; color: var(--text-muted, #8a8f98); line-height: 1.7; }
.eco-loading { padding: 24px 0; color: var(--text-muted, #8a8f98); }

.eco-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.eco-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 18px 20px;
  border: 1px solid var(--border, #ececec);
  border-radius: 12px;
  background: var(--surface, #fff);
}
.eco-num {
  font-size: 30px;
  font-weight: 800;
  line-height: 1.1;
  color: var(--accent, #196ddd);
  letter-spacing: -.5px;
}
.eco-label { font-size: 13px; color: var(--text-muted, #8a8f98); }

.eco-list { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 10px; }
.eco-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 12px 16px;
  border: 1px solid var(--border, #ececec);
  border-radius: 10px;
  background: var(--surface, #fff);
}
.eco-url {
  font-size: 14px;
  color: var(--text, #2c2c2c);
  text-decoration: none;
  border-bottom: 1px dotted var(--border, #d5d5d5);
  word-break: break-all;
}
.eco-url:hover { color: var(--accent, #196ddd); }
.eco-anon { border-bottom: none; color: var(--text-muted, #9aa0a6); font-style: italic; }
.eco-tag {
  font-size: 11px;
  color: var(--text-muted, #9aa0a6);
  background: var(--surface-2, #f7f8fa);
  border: 1px solid var(--border, #ececec);
  border-radius: 999px;
  padding: 1px 8px;
}
.eco-time { font-size: 12px; color: var(--text-muted, #9aa0a6); margin-left: auto; }

.eco-empty { font-size: 14px; color: var(--text-muted, #8a8f98); }
.eco-note {
  margin: 22px 0 0;
  padding: 14px 16px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-muted, #8a8f98);
  background: var(--surface-2, #f7f8fa);
  border: 1px solid var(--border, #ececec);
  border-radius: 10px;
}
.eco-note b { color: var(--text-muted); }

@media (max-width: 560px) {
  .eco-time { margin-left: 0; width: 100%; }
}
</style>
