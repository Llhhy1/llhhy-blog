<template>
  <div class="stats-page">
    <h1 class="page-title">📊 运营驾驶舱</h1>

    <div v-if="!loaded" class="stats-loading">数据加载中…</div>

    <template v-else>
      <!-- 概览卡片：核心指标 + 环比（vs 昨日） -->
      <div class="dash-cards">
        <div v-for="c in cards" :key="c.label" class="dash-card">
          <span class="dash-label">{{ c.label }}</span>
          <span class="dash-num">{{ fmt(c.value) }}</span>
          <span v-if="c.delta === null" class="dash-delta new">新</span>
          <span v-else-if="c.delta !== undefined" class="dash-delta" :class="c.delta >= 0 ? 'up' : 'down'">
            {{ c.delta >= 0 ? '▲' : '▼' }} {{ Math.abs(c.delta) }}% <em>vs 昨日</em>
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

        <!-- 访客趋势图 -->
        <section class="stats-card">
          <h3>📈 近 30 天访客趋势</h3>
          <p v-if="!s.trend || !s.trend.length" class="stats-empty">暂无趋势数据</p>
          <svg v-else class="trend-chart" :viewBox="`0 0 ${trendW} ${trendH}`" preserveAspectRatio="none">
            <polyline :points="pvPoints" fill="none" stroke="#1a73e8" stroke-width="2" />
            <polyline :points="uvPoints" fill="none" stroke="#34a853" stroke-width="2" />
            <text v-for="(d, i) in trendLabels" :key="i" :x="labelX(i)" :y="trendH - 4"
                  font-size="9" fill="#999" text-anchor="middle">{{ d }}</text>
          </svg>
          <div class="trend-legend">
            <span class="lg lg-pv">■ PV（总访问次数）</span>
            <span class="lg lg-uv">■ UV（独立访客）</span>
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
const s = ref({
  metrics: {}, deltas: {},
  hot_reads: [], hot_searches: [], active_regions: [],
  trend: [], hourly: [], total_visits: 0, generated_at: "",
});

const cards = computed(() => {
  const m = s.value.metrics || {};
  const d = s.value.deltas || {};
  return [
    { label: "今日访问 PV", value: m.pv_today, delta: d.pv_dod },
    { label: "今日访客 UV", value: m.uv_today, delta: d.uv_dod },
    { label: "今日新增订阅", value: m.new_subs_today, delta: d.subs_dod },
    { label: "今日新增评论", value: m.new_comments_today, delta: d.comments_dod },
    { label: "今日新文", value: m.new_posts_today, delta: d.posts_dod },
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
function _points(key) {
  const n = trendData.value.length;
  if (!n) return "";
  return trendData.value.map((d, i) => {
    const x = (i / Math.max(1, n - 1)) * (trendW - trendPad * 2) + trendPad;
    const y = trendH - trendPad - (d[key] / trendMax.value) * (trendH - trendPad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}
const pvPoints = computed(() => _points("pv"));
const uvPoints = computed(() => _points("uv"));
const trendLabels = computed(() => trendData.value.map((d, i) =>
  i % 5 === 0 ? d.date.slice(5) : ""));
function labelX(i) {
  const n = trendData.value.length;
  return ((i / Math.max(1, n - 1)) * (trendW - trendPad * 2) + trendPad).toFixed(1);
}

function pct(v, max) { return Math.max(2, Math.round((v / max) * 100)); }
function hourPct(b) { return pct(b.count, maxHour.value); }
function fmt(n) { return Number(n || 0).toLocaleString(); }

onMounted(async () => {
  try {
    s.value = await apiGet("/api/stats/dashboard");
  } catch (e) { console.warn("驾驶舱加载失败", e); }
  loaded.value = true;
});
</script>
