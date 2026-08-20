<template>
  <div class="stats-page">
    <h1 class="page-title">📊 站点统计</h1>

    <!-- 概览 -->
    <div class="stats-cards">
      <div class="stats-big-card">
        <span class="stat-big-num">{{ fmt(s.total_visits) }}</span>
        <span class="stat-big-label">累计访问次数</span>
      </div>
      <div class="stats-big-card">
        <span class="stat-big-num">{{ fmt(s.today_visits) }}</span>
        <span class="stat-big-label">今日访问（{{ s.today_date }}）</span>
      </div>
    </div>

    <div v-if="!loaded" class="stats-loading">统计加载中…</div>

    <div v-else class="stats-grid">
      <!-- 访客区域排行榜（今日） -->
      <section class="stats-card">
        <h3>🌏 今日访客区域 TOP 10</h3>
        <p v-if="!s.regions_today.length" class="stats-empty">今天还没有带属地的访问，稍后再来看看～</p>
        <ul v-else class="rank-list">
          <li v-for="(r, i) in s.regions_today" :key="r.region" class="rank-row">
            <span class="rank-no" :class="{ top: i === 0 }">{{ i + 1 }}</span>
            <span class="rank-name">{{ r.region }}</span>
            <div class="bar-track"><div class="bar-fill" :style="{ width: pct(r.count, maxToday) + '%' }"></div></div>
            <span class="rank-count">{{ fmt(r.count) }}</span>
          </li>
        </ul>
        <h3 class="sub-title">🌏 累计访客区域 TOP 10</h3>
        <ul v-if="s.regions_all.length" class="rank-list">
          <li v-for="(r, i) in s.regions_all" :key="r.region" class="rank-row">
            <span class="rank-no" :class="{ top: i === 0 }">{{ i + 1 }}</span>
            <span class="rank-name">{{ r.region }}</span>
            <div class="bar-track"><div class="bar-fill" :style="{ width: pct(r.count, maxAll) + '%' }"></div></div>
            <span class="rank-count">{{ fmt(r.count) }}</span>
          </li>
        </ul>
      </section>

      <!-- 最受关注 / 反复阅读的文章 -->
      <section class="stats-card">
        <h3>📖 最受关注的文章</h3>
        <p v-if="!s.hot_posts.length" class="stats-empty">还没有阅读记录</p>
        <ul v-else class="rank-list">
          <li v-for="(p, i) in s.hot_posts" :key="p.slug" class="rank-row">
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

      <!-- 常搜词汇 -->
      <section class="stats-card">
        <h3>🔍 常搜词汇 TOP 10</h3>
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

    <p class="stats-tip">数据实时累计：每次打开页面/切换页面记一次访问；区域属地由服务器异步识别。最后更新 {{ s.updated_at }}</p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const loaded = ref(false);
const s = ref({ total_visits: 0, today_visits: 0, today_date: "",
                regions_today: [], regions_all: [], hot_posts: [],
                hot_searches: [], hourly: [], updated_at: "" });

const maxToday = computed(() => Math.max(1, ...s.value.regions_today.map(r => r.count)));
const maxAll = computed(() => Math.max(1, ...s.value.regions_all.map(r => r.count)));
const maxReads = computed(() => Math.max(1, ...s.value.hot_posts.map(p => p.reads)));
const maxHour = computed(() => Math.max(1, ...s.value.hourly.map(b => b.count)));

function pct(v, max) { return Math.max(2, Math.round((v / max) * 100)); }
function hourPct(b) { return pct(b.count, maxHour.value); }
function fmt(n) { return Number(n || 0).toLocaleString(); }

onMounted(async () => {
  try {
    s.value = await apiGet("/api/stats/summary");
  } catch (e) { console.warn("统计加载失败", e); }
  loaded.value = true;
});
</script>
