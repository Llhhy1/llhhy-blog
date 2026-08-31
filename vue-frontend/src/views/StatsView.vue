<template>
  <div class="stats-page">
    <h1 class="page-title">📊 运营驾驶舱</h1>

    <div v-if="!loaded" class="stats-loading">数据加载中…</div>

    <template v-else>
      <!-- 概览卡片：核心指标 + 环比（vs 昨日 / vs 上周同期） -->
      <div class="dash-cards">
        <div v-for="c in cards" :key="c.label" class="dash-card">
          <span class="dash-icon">{{ c.icon }}</span>
          <span class="dash-label">{{ c.label }}</span>
          <span class="dash-num">{{ fmt(c.value) }}</span>
          <div class="dash-foot">
            <span v-if="c.delta === null" class="dash-delta new">新</span>
            <span v-else-if="c.delta !== undefined" class="dash-delta" :class="c.delta >= 0 ? 'up' : 'down'">
              {{ c.delta >= 0 ? '▲' : '▼' }} {{ Math.abs(c.delta) }}% <em>vs 昨日</em>
            </span>
            <span v-if="c.deltaWow === null" class="dash-delta new">新</span>
            <span v-else-if="c.deltaWow !== undefined" class="dash-delta wow" :class="c.deltaWow >= 0 ? 'up' : 'down'">
              {{ c.deltaWow >= 0 ? '▲' : '▼' }} {{ Math.abs(c.deltaWow) }}% <em>vs 上周</em>
            </span>
          </div>
        </div>
      </div>

      <div class="stats-grid">
        <!-- 热读 Top5 -->
        <section class="stats-card">
          <h3>📖 热读 Top 5</h3>
          <p v-if="!s.hot_reads.length" class="stats-empty">还没有阅读记录</p>
          <ul v-else class="rank-list">
            <li v-for="(p, i) in s.hot_reads" :key="p.slug" class="rank-row">
              <span class="rank-no" :class="{ top: i === 0 }">{{ i + 1 }}</span>
              <span class="rank-name post">
                <router-link :to="`/post/${p.slug}`">{{ p.title }}</router-link>
                <span class="rank-sub">{{ p.readers }} 位访客回读</span>
              </span>
              <div class="bar-track"><div class="bar-fill hot" :style="{ width: pct(p.reads, maxReads) + '%' }"></div></div>
              <span class="rank-count">{{ fmt(p.reads) }}</span>
            </li>
          </ul>
        </section>

        <!-- 热搜 Top5 -->
        <section class="stats-card">
          <h3>🔍 热搜 Top 5</h3>
          <p v-if="!s.hot_searches.length" class="stats-empty">还没有搜索记录</p>
          <div v-else class="search-tags">
            <router-link
              v-for="(t, i) in s.hot_searches" :key="t.keyword"
              :to="`/search?q=${encodeURIComponent(t.keyword)}`"
              class="search-tag" :class="{ hot: i === 0 }"
              :title="`${t.count} 次搜索`">{{ t.keyword }}<span class="search-count">{{ t.count }}</span>
            </router-link>
          </div>
        </section>

        <!-- 活跃地区 Top5 -->
        <section class="stats-card">
          <h3>🌏 活跃地区 Top 5</h3>
          <p v-if="!s.active_regions.length" class="stats-empty">今天还没有带属地的访问</p>
          <ul v-else class="rank-list">
            <li v-for="(r, i) in s.active_regions" :key="r.region" class="rank-row">
              <span class="rank-no" :class="{ top: i === 0 }">{{ i + 1 }}</span>
              <span class="rank-name">{{ r.region }}</span>
              <div class="bar-track"><div class="bar-fill" :style="{ width: pct(r.count, maxRegion) + '%' }"></div></div>
              <span class="rank-count">{{ fmt(r.count) }}</span>
            </li>
          </ul>
        </section>

        <!-- 访客趋势图（二期：区间切换 + 4 曲线 + 悬浮提示 + CSV 导出；视觉升级：面积填充 + 网格 + 悬浮高亮） -->
        <section class="stats-card trend-card">
          <div class="card-head">
            <h3>📈 近 {{ range }} 天趋势</h3>
            <div class="card-tools">
              <div class="range-switch">
                <button v-for="r in [7, 30, 90]" :key="r" :class="{ active: range === r }" @click="setRange(r)">
                  {{ r }}天
                </button>
              </div>
              <button class="export-btn" @click="exportCsv" :disabled="!trendData.length">导出 CSV</button>
            </div>
          </div>
          <p v-if="!trendData.length" class="stats-empty">暂无趋势数据</p>
          <div v-else class="trend-wrap" ref="trendWrap">
            <svg class="trend-svg" :viewBox="`0 0 ${trendW} ${trendH}`" preserveAspectRatio="none"
                 @mousemove="onTrendMove" @mouseleave="hoverIdx = null">
              <defs>
                <linearGradient id="pvGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#1a73e8" stop-opacity="0.26" />
                  <stop offset="100%" stop-color="#1a73e8" stop-opacity="0" />
                </linearGradient>
                <linearGradient id="uvGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#34a853" stop-opacity="0.18" />
                  <stop offset="100%" stop-color="#34a853" stop-opacity="0" />
                </linearGradient>
              </defs>
              <!-- 横向网格线 -->
              <line v-for="(y, i) in gridLines" :key="'g' + i" :x1="padX" :x2="trendW - padX" :y1="y" :y2="y" class="grid-line" />
              <!-- 面积填充（PV / UV 左轴） -->
              <polygon :points="pvArea" fill="url(#pvGrad)" />
              <polygon :points="uvArea" fill="url(#uvGrad)" />
              <!-- 曲线：评论/新文（右轴）虚线在底层，PV/UV（左轴）实线在上层 -->
              <polyline :points="cmLine" class="ln-cm" fill="none" />
              <polyline :points="psLine" class="ln-ps" fill="none" />
              <polyline :points="uvLine" class="ln-uv" fill="none" />
              <polyline :points="pvLine" class="ln-pv" fill="none" />
              <!-- 悬浮竖线 + 高亮点 -->
              <line v-if="hoverIdx !== null" :x1="xAt(hoverIdx)" :x2="xAt(hoverIdx)" :y1="padTop" :y2="padTop + plotH" class="hover-line" />
              <circle v-if="hoverIdx !== null && trendData[hoverIdx]" :cx="xAt(hoverIdx)" :cy="yAt(trendData[hoverIdx].pv, trendMax)" r="3.6" class="hover-dot pv" />
              <circle v-if="hoverIdx !== null && trendData[hoverIdx]" :cx="xAt(hoverIdx)" :cy="yAt(trendData[hoverIdx].uv, trendMax)" r="3.6" class="hover-dot uv" />
            </svg>
            <!-- x 轴日期刻度（HTML 叠加，避免 SVG 缩放拉伸文字） -->
            <div class="trend-axis">
              <span v-for="t in xAxisTicks" :key="t.label" class="axis-tick" :class="{ first: t.first, last: t.last }"
                    :style="{ left: t.pct + '%' }">{{ t.label }}</span>
            </div>
            <div v-if="hoverIdx !== null && trendData[hoverIdx]" class="trend-tip" :style="tipStyle">
              <div class="tip-date">{{ trendData[hoverIdx].date }}</div>
              <div class="tip-row"><span class="dot pv"></span>PV：{{ fmt(trendData[hoverIdx].pv) }}</div>
              <div class="tip-row"><span class="dot uv"></span>UV：{{ fmt(trendData[hoverIdx].uv) }}</div>
              <div class="tip-row"><span class="dot cm"></span>评论：{{ fmt(trendData[hoverIdx].comments) }}</div>
              <div class="tip-row"><span class="dot ps"></span>新文：{{ fmt(trendData[hoverIdx].posts) }}</div>
            </div>
            <div class="trend-legend">
              <span class="lg lg-pv">■ PV（总访问）</span>
              <span class="lg lg-uv">■ UV（独立访客）</span>
              <span class="lg lg-cm">▨ 评论量（右轴）</span>
              <span class="lg lg-ps">▨ 新文量（右轴）</span>
            </div>
          </div>
        </section>

        <!-- 阅读时段分布 -->
        <section class="stats-card hour-card">
          <h3>🕐 访客阅读时段分布</h3>
          <p v-if="!s.total_visits" class="stats-empty">暂无访问数据</p>
          <div v-else class="hour-chart">
            <div v-for="b in s.hourly" :key="b.hour" class="hour-col" :title="b.hour + ' 时 · ' + b.count + ' 次'">
              <div class="hour-bar" :style="{ height: hourPct(b) + '%' }"></div>
              <span class="hour-label">{{ b.hour }}</span>
            </div>
          </div>
        </section>
      </div>
    </template>

    <p class="stats-tip" v-if="loaded">数据实时累计：每次打开页面/切换页面记一次访问；区域属地由服务器异步识别。最后更新 {{ s.generated_at }}</p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const loaded = ref(false);
const range = ref(30);
const hoverIdx = ref(null);
const trendWrap = ref(null);
const s = ref({
  metrics: {}, deltas: {},
  hot_reads: [], hot_searches: [], active_regions: [],
  trend: [], hourly: [], total_visits: 0, generated_at: "",
});

const cards = computed(() => {
  const m = s.value.metrics || {};
  const d = s.value.deltas || {};
  return [
    { icon: "👁", label: "今日访问 PV", value: m.pv_today, delta: d.pv_dod, deltaWow: d.pv_wow },
    { icon: "🧭", label: "今日访客 UV", value: m.uv_today, delta: d.uv_dod, deltaWow: d.uv_wow },
    { icon: "🔔", label: "今日新增订阅", value: m.new_subs_today, delta: d.subs_dod, deltaWow: d.subs_wow },
    { icon: "💬", label: "今日新增评论", value: m.new_comments_today, delta: d.comments_dod, deltaWow: d.comments_wow },
    { icon: "✍️", label: "今日新文", value: m.new_posts_today, delta: d.posts_dod, deltaWow: d.posts_wow },
    { icon: "📨", label: "订阅总数", value: m.subs_total },
    { icon: "📬", label: "未读评论", value: m.comments_unread },
    { icon: "📚", label: "文章总数", value: m.posts_total },
  ];
});

const maxReads = computed(() => Math.max(1, ...(s.value.hot_reads || []).map(p => p.reads)));
const maxRegion = computed(() => Math.max(1, ...(s.value.active_regions || []).map(r => r.count)));
const maxHour = computed(() => Math.max(1, ...(s.value.hourly || []).map(b => b.count)));

// ---------- 访客趋势图（SVG 坐标映射） ----------
const trendW = 720;
const trendH = 240;
const padX = 14;
const padTop = 18;
const padBottom = 26;
const plotH = computed(() => trendH - padTop - padBottom);

const trendData = computed(() => s.value.trend || []);
const trendMax = computed(() => Math.max(1, ...trendData.value.map(d => d.pv)));
// 评论量 / 新文量量级远小于 PV，用各自共享的最大值做独立刻度，避免被压成贴地线
const cmPsMax = computed(() =>
  Math.max(1, ...trendData.value.map(d => Math.max(d.comments || 0, d.posts || 0))));

function xAt(i) {
  const n = trendData.value.length;
  return padX + (i / Math.max(1, n - 1)) * (trendW - 2 * padX);
}
function yAt(v, max) {
  return padTop + (1 - v / max) * plotH.value;
}
function linePts(key, max) {
  const n = trendData.value.length;
  if (!n) return "";
  return trendData.value.map((d, i) => `${xAt(i).toFixed(1)},${yAt(d[key], max).toFixed(1)}`).join(" ");
}
function areaPts(key, max) {
  const n = trendData.value.length;
  if (!n) return "";
  const baseY = (padTop + plotH.value).toFixed(1);
  return `${padX},${baseY} ${linePts(key, max)} ${(xAt(n - 1)).toFixed(1)},${baseY}`;
}
const pvLine = computed(() => linePts("pv", trendMax.value));
const uvLine = computed(() => linePts("uv", trendMax.value));
const cmLine = computed(() => linePts("comments", cmPsMax.value));
const psLine = computed(() => linePts("posts", cmPsMax.value));
const pvArea = computed(() => areaPts("pv", trendMax.value));
const uvArea = computed(() => areaPts("uv", trendMax.value));
// 4 条横向网格线
const gridLines = computed(() => {
  const arr = [];
  for (let k = 0; k <= 4; k++) arr.push((padTop + (k / 4) * plotH.value).toFixed(1));
  return arr;
});
// x 轴刻度：首 / 1/3 / 2/3 / 尾
const xAxisTicks = computed(() => {
  const n = trendData.value.length;
  if (!n) return [];
  const idxs = n <= 1 ? [0] : [0, Math.floor((n - 1) / 3), Math.floor(2 * (n - 1) / 3), n - 1];
  return idxs.map((i, k) => ({
    pct: (xAt(i) / trendW * 100).toFixed(1),
    label: trendData.value[i].date.slice(5),
    first: k === 0,
    last: k === idxs.length - 1,
  }));
});

// 悬浮提示：把鼠标 x 映射回数据索引，tooltip 按百分比定位在容器上
function onTrendMove(e) {
  const n = trendData.value.length;
  if (!n) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * trendW;
  const rel = (x - padX) / (trendW - 2 * padX);
  let idx = Math.round(rel * (n - 1));
  idx = Math.max(0, Math.min(n - 1, idx));
  hoverIdx.value = idx;
}
const tipStyle = computed(() => {
  if (hoverIdx.value === null) return {};
  return { left: (xAt(hoverIdx.value) / trendW) * 100 + "%" };
});

// CSV 导出：带 BOM 让 Excel 正确识别中文；列 = 日期/PV/UV/评论量/新文量
function exportCsv() {
  const rows = [["日期", "PV", "UV", "评论量", "新文量"]];
  for (const d of trendData.value) {
    rows.push([d.date, d.pv, d.uv, d.comments, d.posts]);
  }
  const csv = "﻿" + rows.map(r => r.join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `dashboard_trend_${range.value}days.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function pct(v, max) { return Math.max(2, Math.round((v / max) * 100)); }
function hourPct(b) { return pct(b.count, maxHour.value); }
function fmt(n) { return Number(n || 0).toLocaleString(); }

async function load() {
  try {
    s.value = await apiGet("/api/stats/dashboard?range=" + range.value);
  } catch (e) { console.warn("驾驶舱加载失败", e); }
  loaded.value = true;
}
async function setRange(r) {
  if (r === range.value) return;
  range.value = r;
  hoverIdx.value = null;
  await load();
}

onMounted(load);
</script>

<style scoped>
/* ===== 概览指标卡片 ===== */
.dash-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}
.dash-card {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  background: var(--surface, #fff);
  border: 1px solid var(--border-strong, #ececf0);
  border-radius: var(--theme-radius, 14px);
  padding: 16px 16px 14px;
  box-shadow: 0 1px 3px rgba(20, 30, 50, 0.05);
  transition: transform .18s ease, box-shadow .18s ease;
}
.dash-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 24px rgba(20, 30, 50, 0.12);
}
.dash-card::after {
  content: "";
  position: absolute;
  right: -22px;
  top: -22px;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: radial-gradient(circle at center,
    color-mix(in srgb, var(--accent, #1a73e8) 14%, transparent), transparent 70%);
}
.dash-icon {
  font-size: 17px;
  line-height: 1;
  margin-bottom: 9px;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--accent, #1a73e8) 10%, transparent);
  border-radius: 10px;
}
.dash-label {
  font-size: 13px;
  color: var(--text-soft, #8a8f98);
  margin-bottom: 3px;
}
.dash-num {
  font-size: 28px;
  font-weight: 800;
  color: var(--accent, #1a73e8);
  line-height: 1.1;
  letter-spacing: -.5px;
}
.dash-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.dash-delta {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-weight: 600;
  white-space: nowrap;
}
.dash-delta.up { color: #1a9d54; background: rgba(26, 157, 84, .10); }
.dash-delta.down { color: #e0533d; background: rgba(224, 83, 61, .10); }
.dash-delta.new { color: #b07400; background: rgba(244, 180, 0, .14); }
.dash-delta em { font-style: normal; opacity: .65; font-weight: 500; }
.dash-delta.wow { font-size: 11px; opacity: .9; }

/* ===== 网格布局：三列小卡 + 趋势/时段全宽 ===== */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
}
.trend-card,
.hour-card { grid-column: 1 / -1; }
@media (max-width: 980px) {
  .stats-grid { grid-template-columns: 1fr; }
}

/* ===== 趋势图 ===== */
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.card-head h3 { margin: 0; }
.card-tools { display: flex; align-items: center; gap: 10px; }
.range-switch { display: inline-flex; border: 1px solid var(--border, #e3e3e3); border-radius: 8px; overflow: hidden; }
.range-switch button {
  border: none; background: var(--card, #fff); color: var(--text, #333);
  padding: 4px 10px; cursor: pointer; font-size: 12px;
}
.range-switch button.active { background: var(--accent, #1a73e8); color: #fff; }
.export-btn {
  border: 1px solid var(--border, #e3e3e3); background: var(--card, #fff);
  color: var(--text, #333); border-radius: 8px; padding: 4px 10px;
  cursor: pointer; font-size: 12px;
}
.export-btn:disabled { opacity: .5; cursor: not-allowed; }

.trend-wrap { position: relative; }
.trend-svg { width: 100%; height: 240px; display: block; }
.grid-line { stroke: var(--border-strong, #ececec); stroke-width: 1; vector-effect: non-scaling-stroke; }
.ln-pv { stroke: #1a73e8; stroke-width: 2.4; vector-effect: non-scaling-stroke; stroke-linejoin: round; stroke-linecap: round; }
.ln-uv { stroke: #34a853; stroke-width: 2.4; vector-effect: non-scaling-stroke; stroke-linejoin: round; stroke-linecap: round; }
.ln-cm { stroke: #f4b400; stroke-width: 2; stroke-dasharray: 5 4; vector-effect: non-scaling-stroke; }
.ln-ps { stroke: #e8710a; stroke-width: 2; stroke-dasharray: 5 4; vector-effect: non-scaling-stroke; }
.hover-line { stroke: #c2c6cc; stroke-width: 1; vector-effect: non-scaling-stroke; }
.hover-dot.pv { fill: #1a73e8; stroke: #fff; stroke-width: 1.5; }
.hover-dot.uv { fill: #34a853; stroke: #fff; stroke-width: 1.5; }

.trend-axis { position: relative; height: 16px; margin-top: 2px; }
.axis-tick {
  position: absolute;
  transform: translateX(-50%);
  font-size: 10px;
  color: #9aa0a6;
  white-space: nowrap;
}
.axis-tick.first { transform: translateX(0); }
.axis-tick.last { transform: translateX(-100%); }

.trend-tip {
  position: absolute;
  top: 6px;
  transform: translateX(-50%);
  background: rgba(30, 30, 30, .92);
  color: #fff;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  pointer-events: none;
  white-space: nowrap;
  box-shadow: 0 4px 12px rgba(0, 0, 0, .25);
  z-index: 5;
}
.tip-date { font-weight: 600; margin-bottom: 2px; }
.tip-row { display: flex; align-items: center; gap: 6px; }
.tip-row .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.pv { background: #1a73e8; }
.dot.uv { background: #34a853; }
.dot.cm { background: #f4b400; }
.dot.ps { background: #e8710a; }
.trend-legend { margin-top: 8px; display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: #777; }
.trend-legend .lg-pv { color: #1a73e8; }
.trend-legend .lg-uv { color: #34a853; }
.trend-legend .lg-cm { color: #f4b400; }
.trend-legend .lg-ps { color: #e8710a; }
</style>
