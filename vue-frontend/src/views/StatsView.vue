<template>
  <div class="stats-page">
    <h1 class="page-title">📊 运营驾驶舱</h1>

    <div v-if="!loaded" class="stats-loading">数据加载中…</div>

    <template v-else>
      <!-- 概览卡片：核心指标 + 环比（vs 昨日 / vs 上周同期） -->
      <div class="dash-cards">
        <div v-for="c in cards" :key="c.label" class="dash-card">
          <span class="dash-label">{{ c.label }}</span>
          <span class="dash-num">{{ fmt(c.value) }}</span>
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

        <!-- 访客趋势图（二期：区间切换 + 4 曲线 + 悬浮提示 + CSV 导出） -->
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
          <p v-if="!s.trend || !s.trend.length" class="stats-empty">暂无趋势数据</p>
          <div v-else class="trend-wrap" ref="trendWrap">
            <svg class="trend-chart" :viewBox="`0 0 ${trendW} ${trendH}`" preserveAspectRatio="none"
                 @mousemove="onTrendMove" @mouseleave="hoverIdx = null">
              <polyline :points="pvPoints" fill="none" stroke="#1a73e8" stroke-width="2" />
              <polyline :points="uvPoints" fill="none" stroke="#34a853" stroke-width="2" />
              <polyline :points="cmPoints" fill="none" stroke="#f4b400" stroke-width="2" stroke-dasharray="4 3" />
              <polyline :points="psPoints" fill="none" stroke="#e8710a" stroke-width="2" stroke-dasharray="4 3" />
              <line v-if="hoverIdx !== null" :x1="xAt(hoverIdx)" :x2="xAt(hoverIdx)" :y1="0" :y2="trendH" stroke="#bbb" stroke-width="1" />
              <text v-for="(d, i) in trendLabels" :key="i" :x="labelX(i)" :y="trendH - 4"
                    font-size="9" fill="#999" text-anchor="middle">{{ d }}</text>
            </svg>
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
        <section class="stats-card">
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
    { label: "今日访问 PV", value: m.pv_today, delta: d.pv_dod, deltaWow: d.pv_wow },
    { label: "今日访客 UV", value: m.uv_today, delta: d.uv_dod, deltaWow: d.uv_wow },
    { label: "今日新增订阅", value: m.new_subs_today, delta: d.subs_dod, deltaWow: d.subs_wow },
    { label: "今日新增评论", value: m.new_comments_today, delta: d.comments_dod, deltaWow: d.comments_wow },
    { label: "今日新文", value: m.new_posts_today, delta: d.posts_dod, deltaWow: d.posts_wow },
    { label: "订阅总数", value: m.subs_total },
    { label: "未读评论", value: m.comments_unread },
    { label: "文章总数", value: m.posts_total },
  ];
});

const maxReads = computed(() => Math.max(1, ...(s.value.hot_reads || []).map(p => p.reads)));
const maxRegion = computed(() => Math.max(1, ...(s.value.active_regions || []).map(r => r.count)));
const maxHour = computed(() => Math.max(1, ...(s.value.hourly || []).map(b => b.count)));

// 访客趋势图：把趋势数据映射成 SVG 折线坐标
const trendW = 660;
const trendH = 180;
const trendPad = 8;
const trendData = computed(() => s.value.trend || []);
const trendMax = computed(() => Math.max(1, ...trendData.value.map(d => d.pv)));
// 评论量 / 新文量量级远小于 PV，用各自共享的最大值做独立刻度，避免被压成贴地线
const cmPsMax = computed(() =>
  Math.max(1, ...trendData.value.map(d => Math.max(d.comments || 0, d.posts || 0))));

function _points(key, maxVal) {
  const n = trendData.value.length;
  if (!n) return "";
  return trendData.value.map((d, i) => {
    const x = (i / Math.max(1, n - 1)) * (trendW - trendPad * 2) + trendPad;
    const y = trendH - trendPad - (d[key] / maxVal) * (trendH - trendPad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}
const pvPoints = computed(() => _points("pv", trendMax.value));
const uvPoints = computed(() => _points("uv", trendMax.value));
const cmPoints = computed(() => _points("comments", cmPsMax.value));
const psPoints = computed(() => _points("posts", cmPsMax.value));
const trendLabels = computed(() => trendData.value.map((d, i) =>
  i % 5 === 0 ? d.date.slice(5) : ""));
function labelX(i) {
  const n = trendData.value.length;
  return ((i / Math.max(1, n - 1)) * (trendW - trendPad * 2) + trendPad).toFixed(1);
}
function xAt(i) {
  const n = trendData.value.length;
  return (i / Math.max(1, n - 1)) * (trendW - trendPad * 2) + trendPad;
}

// 悬浮提示：把鼠标 x 映射回数据索引，tooltip 按百分比定位在容器上
function onTrendMove(e) {
  const n = trendData.value.length;
  if (!n) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * trendW;
  const rel = (x - trendPad) / (trendW - trendPad * 2);
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
.trend-tip {
  position: absolute; top: 6px; transform: translateX(-50%);
  background: rgba(30, 30, 30, .92); color: #fff; border-radius: 8px;
  padding: 8px 10px; font-size: 12px; line-height: 1.5; pointer-events: none;
  white-space: nowrap; box-shadow: 0 4px 12px rgba(0, 0, 0, .25); z-index: 5;
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

/* 卡片环比：新增「vs 上周」次行 */
.dash-delta.wow { font-size: 11px; opacity: .85; }
.dash-delta.wow em { font-style: normal; opacity: .7; }
</style>
