<template>
  <div>
    <div class="page-head">
      <h1 class="page-title">📅 {{ year }} 年度回顾</h1>
      <select v-if="years.length > 1" v-model.number="year" @change="load" class="year-select" aria-label="选择年份">
        <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
      </select>
    </div>

    <div v-if="loading" class="ar-loading">加载中…</div>
    <template v-else>
      <section class="ar-stats">
        <div class="ar-stat"><span class="k">发文</span><span class="v">{{ d.posts }}</span></div>
        <div class="ar-stat"><span class="k">阅读</span><span class="v">{{ fmt(d.views) }}</span></div>
        <div class="ar-stat"><span class="k">评论</span><span class="v">{{ fmt(d.comments) }}</span></div>
        <div class="ar-stat"><span class="k">访客</span><span class="v">{{ fmt(d.visitors) }}</span></div>
        <div class="ar-stat"><span class="k">字数</span><span class="v">{{ fmt(d.words) }}</span></div>
      </section>

      <section class="ar-card">
        <h2>月度发文</h2>
        <div class="ar-months">
          <div v-for="(n, i) in d.months" :key="i" class="ar-month" :title="(i + 1) + '月：' + n + ' 篇'">
            <div class="ar-bar" :style="{ height: barH(n) }"></div>
            <span class="ar-mlabel">{{ i + 1 }}</span>
          </div>
        </div>
      </section>

      <div class="ar-two">
        <section class="ar-card">
          <h2>🔥 最热文章</h2>
          <ol class="ar-hot">
            <li v-for="p in d.hot_posts" :key="p.slug">
              <router-link :to="`/post/${p.slug}`">{{ p.title }}</router-link>
              <span class="ar-num">{{ p.views }}</span>
            </li>
            <li v-if="!d.hot_posts.length" class="ar-empty">该年暂无文章</li>
          </ol>
        </section>

        <section class="ar-card">
          <h2>🏷️ 高频标签</h2>
          <div class="ar-tags">
            <router-link v-for="t in d.tags" :key="t.slug" :to="`/tag/${t.slug}`" class="ar-tag">
              {{ t.name }}<em>{{ t.count }}</em>
            </router-link>
            <span v-if="!d.tags.length" class="ar-empty">暂无</span>
          </div>
        </section>
      </div>

      <section class="ar-card">
        <h2>🌏 访客地域 TOP8</h2>
        <div class="ar-regions">
          <div v-for="r in d.regions" :key="r.region" class="ar-region">
            <span class="ar-rname" :title="r.region">{{ r.region }}</span>
            <span class="ar-rbar"><i :style="{ width: regionW(r.count) }"></i></span>
            <span class="ar-rnum">{{ r.count }}</span>
          </div>
          <p v-if="!d.regions.length" class="ar-empty">暂无地域数据</p>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const year = ref(new Date().getFullYear());
const years = ref([]);
const loading = ref(true);
const d = ref({
  posts: 0, views: 0, comments: 0, visitors: 0, words: 0,
  months: new Array(12).fill(0), hot_posts: [], tags: [], regions: [],
});

function fmt(n) {
  n = Number(n) || 0;
  if (n >= 100000) return (n / 10000).toFixed(1) + "w";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

function barH(n) {
  const max = Math.max(1, ...(d.value.months || [1]));
  return Math.max(2, Math.round((n / max) * 100)) + "%";
}
function regionW(n) {
  const max = Math.max(1, ...(d.value.regions || []).map((r) => r.count));
  return Math.max(4, Math.round((n / max) * 100)) + "%";
}

async function load() {
  loading.value = true;
  try {
    const res = await apiGet("/api/review/annual", { year: year.value });
    d.value = res;
    if (res.years && res.years.length) years.value = res.years;
    if (res.year) year.value = res.year;
  } catch (e) {} finally { loading.value = false; }
}
onMounted(load);
</script>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.year-select { padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text); }
.ar-loading { color: var(--text-muted); padding: 20px 0; }
.ar-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 18px; }
.ar-stat { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md, 12px); padding: 12px 14px; display: flex; flex-direction: column; gap: 2px; }
.ar-stat .k { font-size: 12px; color: var(--text-muted); }
.ar-stat .v { font-size: 22px; font-weight: 700; }
.ar-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md, 12px); padding: 16px 18px; margin-bottom: 18px; }
.ar-card h2 { font-size: 15px; margin: 0 0 12px; }
.ar-two { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.ar-months { display: flex; align-items: flex-end; gap: 6px; height: 120px; }
.ar-month { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 4px; }
.ar-bar { width: 100%; max-width: 26px; background: linear-gradient(180deg, var(--accent), var(--accent-soft)); border-radius: 4px 4px 0 0; }
.ar-mlabel { font-size: 11px; color: var(--text-faint); }
.ar-hot { margin: 0; padding-left: 20px; }
.ar-hot li { display: flex; justify-content: space-between; gap: 10px; padding: 5px 0; font-size: 14px; }
.ar-hot a { color: var(--text); text-decoration: none; }
.ar-hot a:hover { color: var(--accent); }
.ar-num { color: var(--text-muted); font-size: 12px; flex-shrink: 0; }
.ar-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.ar-tag { display: inline-flex; align-items: center; gap: 5px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 999px; padding: 4px 10px; font-size: 13px; color: var(--text); text-decoration: none; }
.ar-tag em { color: var(--text-muted); font-style: normal; font-size: 12px; }
.ar-regions { display: flex; flex-direction: column; gap: 8px; }
.ar-region { display: grid; grid-template-columns: 84px 1fr 46px; align-items: center; gap: 10px; font-size: 13px; }
.ar-rname { color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ar-rbar { background: var(--surface-2); border-radius: 999px; height: 8px; overflow: hidden; }
.ar-rbar i { display: block; height: 100%; background: var(--accent); border-radius: 999px; transition: width var(--transition, 160ms ease); }
.ar-rnum { text-align: right; color: var(--text-muted); }
.ar-empty { color: var(--text-faint); font-size: 13px; }
@media (max-width: 720px) {
  .ar-stats { grid-template-columns: repeat(2, 1fr); }
  .ar-two { grid-template-columns: 1fr; }
}
</style>
