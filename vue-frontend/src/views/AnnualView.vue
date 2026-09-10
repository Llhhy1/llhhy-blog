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

      <!-- v3.17.3 访客地图（DataV 合规底图，后端缓存；仅省级聚合，失败降级为地域榜） -->
      <section class="ar-card">
        <h2>🗺️ 访客地图<em class="ar-badge-count">近一年 · 按省</em></h2>
        <div v-if="geoLoading" class="ar-loading">地图数据加载中…</div>
        <template v-else-if="!geoFailed && geoPaths.length">
          <svg class="geo-svg" viewBox="0 0 640 500" role="img" aria-label="访客省份分布地图">
            <path v-for="p in geoPaths" :key="p.name" :d="p.d" class="geo-prov"
                  :fill="p.count ? heatColor(p.count) : 'var(--surface-2)'"
                  stroke="var(--border)" stroke-width="0.5">
              <title>{{ p.name }}：{{ p.count ? p.count + ' 次访问' : '暂无访问' }}</title>
            </path>
          </svg>
          <p class="ar-badge-tip">底图：阿里云 DataV 行政区划（含港澳台及南海诸岛）· 仅按省级聚合，不含任何个人位置数据</p>
        </template>
        <p v-else class="ar-empty">地图底图加载失败，请参考下方地域榜</p>
      </section>

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

      <section class="ar-card">
        <h2>🏅 成就徽章<em class="ar-badge-count">{{ ms.unlocked }}/{{ ms.total }}</em></h2>
        <div class="ar-badges">
          <div v-for="b in ms.items" :key="b.id" class="ar-badge" :class="{ on: b.unlocked }" :title="b.desc">
            <span class="ar-badge-icon">{{ b.icon }}</span>
            <span class="ar-badge-name">{{ b.name }}</span>
            <span class="ar-badge-prog">{{ b.unlocked ? '已解锁' : b.current + '/' + b.target }}</span>
          </div>
        </div>
        <p class="ar-badge-tip">连续更新 {{ ms.streak }} 天 · 开博 {{ ms.running_days }} 天</p>
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
const ms = ref({ unlocked: 0, total: 0, items: [], streak: 0, running_days: 0 });
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
  } catch (e) {}
  // v3.17.2：成就徽章（独立接口，失败不影响页面）
  apiGet("/api/milestones").then((r) => { if (r) ms.value = r; }).catch(() => {});
  loading.value = false;
}
onMounted(load);

// v3.17.3 访客地图：合规底图（DataV 行政区划，后端缓存 7 天）+ 自绘墨卡托 SVG；
// 仅省级聚合渲染，不含任何个人位置；底图/数据任一失败则降级为地域榜。
const geoLoading = ref(false);
const geoFailed = ref(false);
const geoPaths = ref([]);
const geoMax = ref(1);
let geoTried = false;
async function loadMap() {
  if (geoTried) return;
  geoTried = true;
  geoLoading.value = true;
  try {
    const [g, d] = await Promise.all([
      fetch("/api/geo/china.json").then((r) => { if (!r.ok) throw new Error("geo unavailable"); return r.json(); }),
      apiGet("/api/geo/visitors?days=365").catch(() => ({ provinces: [] })),
    ]);
    buildMap(g, (d && d.provinces) || []);
  } catch (e) {
    geoFailed.value = true;
  } finally {
    geoLoading.value = false;
  }
}
function buildMap(g, provinces) {
  const feats = (g && g.features) || [];
  const proj = ([lng, lat]) => [lng, Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI / 180) / 2)) * 180 / Math.PI];
  let minX = 180, minY = 90, maxX = -180, maxY = -90;
  feats.forEach((f) => {
    const polys = f.geometry.type === "MultiPolygon" ? f.geometry.coordinates : [f.geometry.coordinates];
    polys.forEach((pl) => pl.forEach((ring) => ring.forEach((pt) => {
      const [x, y] = proj(pt);
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
    })));
  });
  const W = 640, H = 500, pad = 6;
  const s = Math.min((W - pad * 2) / (maxX - minX), (H - pad * 2) / (maxY - minY));
  const cnt = {};
  provinces.forEach((p) => { cnt[p.name] = p.count; });
  geoPaths.value = feats.map((f) => {
    const polys = f.geometry.type === "MultiPolygon" ? f.geometry.coordinates : [f.geometry.coordinates];
    let d = "";
    polys.forEach((pl) => pl.forEach((ring) => {
      ring.forEach((pt, i) => {
        const [x, y] = proj(pt);
        d += (i ? "L" : "M") + (pad + (x - minX) * s).toFixed(1) + " " + (pad + (maxY - y) * s).toFixed(1);
      });
      d += "Z";
    }));
    const name = (f.properties && f.properties.name) || "";
    return { name, d, count: cnt[name] || 0 };
  });
  geoMax.value = Math.max(1, ...geoPaths.value.map((p) => p.count));
}
function heatColor(c) {
  const t = Math.min(1, Math.max(0, c / geoMax.value));
  return `color-mix(in srgb, var(--accent) ${Math.round(25 + t * 75)}%, var(--surface-2))`;
}
loadMap();
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
/* v3.17.2 成就徽章 */
.ar-badge-count { font-style: normal; color: var(--text-muted); font-size: 13px; margin-left: 6px; }
.ar-badges { display: grid; grid-template-columns: repeat(auto-fill, minmax(108px, 1fr)); gap: 10px; }
.ar-badge { display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 12px 8px;
  border: 1px solid var(--border); border-radius: var(--radius-md, 12px); background: var(--surface-2);
  filter: grayscale(1); opacity: .5;
  transition: transform var(--transition, 160ms ease), opacity var(--transition, 160ms ease); }
.ar-badge.on { filter: none; opacity: 1; background: var(--surface); border-color: var(--accent); }
.ar-badge.on:hover { transform: translateY(-2px); }
.ar-badge-icon { font-size: 22px; line-height: 1; }
.ar-badge-name { font-size: 12.5px; font-weight: 600; }
.ar-badge-prog { font-size: 11px; color: var(--text-muted); }
.ar-badge-tip { margin: 12px 0 0; font-size: 12px; color: var(--text-faint); }
/* v3.17.3 访客地图 */
.geo-svg { width: 100%; height: auto; display: block; }
.geo-prov { cursor: default; }
@media (max-width: 720px) {
  .ar-stats { grid-template-columns: repeat(2, 1fr); }
  .ar-two { grid-template-columns: 1fr; }
}
</style>
