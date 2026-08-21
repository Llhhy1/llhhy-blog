<template>
  <aside class="sidebar">
    <div class="widget">
      <h3>站内搜索</h3>
      <form class="search-box" @submit.prevent="doSearch">
        <input type="text" v-model="q" placeholder="搜索文章…" />
        <button type="submit">搜索</button>
      </form>
    </div>

    <div class="widget">
      <h3>📬 邮件订阅</h3>
      <p class="sub-tip">新文章发布第一时间邮件通知你</p>
      <form class="sub-box" @submit.prevent="doSubscribe">
        <input type="email" v-model="subEmail" placeholder="输入邮箱地址" autocomplete="email" :disabled="subDone" />
        <button type="submit" :disabled="subBusy || subDone">{{ subBtnText }}</button>
      </form>
      <p v-if="subMsg" class="sub-msg" :class="subOk ? 'ok' : 'err'">{{ subMsg }}</p>
    </div>

    <WeatherWidget />

    <div class="widget">
      <h3>分类</h3>
      <ul class="list-clean">
        <li v-for="c in cats" :key="c.slug">
          <router-link :to="`/category/${c.slug}`">{{ c.name }}</router-link>
        </li>
        <li v-if="!cats.length">暂无分类</li>
      </ul>
    </div>

    <div class="widget">
      <h3>标签</h3>
      <div class="tag-cloud">
        <router-link v-for="t in tags" :key="t.slug" class="tag" :to="`/tag/${t.slug}`">{{ t.name }}</router-link>
        <span v-if="!tags.length">暂无标签</span>
      </div>
    </div>

    <div class="widget">
      <h3>最新文章</h3>
      <ul class="list-clean">
        <li v-for="p in recent" :key="p.slug">
          <router-link :to="`/post/${p.slug}`">{{ p.title }}</router-link>
        </li>
        <li v-if="!recent.length">暂无文章</li>
      </ul>
    </div>

    <div class="widget">
      <h3>🔥 热门文章</h3>
      <ul class="list-clean">
        <li v-for="p in hotPosts" :key="p.slug">
          <router-link :to="`/post/${p.slug}`">{{ p.title }}</router-link>
          <span style="font-size: 11px; color: #aaa; margin-left: 6px;">{{ p.reads }} 读</span>
        </li>
        <li v-if="!hotPosts.length">暂无数据</li>
      </ul>
    </div>

    <div class="widget">
      <h3>站点统计</h3>
      <p style="font-size: 13px; color: #666;">文章 {{ totalPosts }} 篇 · 评论 {{ totalComments }} 条</p>
    </div>

    <div v-if="links.length" class="widget">
      <h3>友情链接</h3>
      <ul class="list-clean">
        <li v-for="l in links.slice(0, 6)" :key="l.url">
          <a :href="l.url" target="_blank" rel="noopener">{{ l.name }}</a>
        </li>
      </ul>
    </div>
  </aside>
</template>

<script setup>
import { onMounted, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { apiGet, apiPost } from "../lib/api.js";
import WeatherWidget from "./WeatherWidget.vue";

const router = useRouter();
const q = ref("");
const cats = ref([]);
const tags = ref([]);
const links = ref([]);
const recent = ref([]);
const totalPosts = ref(0);
const totalComments = ref(0);
const hotPosts = ref([]);

// 邮件订阅
const subEmail = ref("");
const subBusy = ref(false);
const subDone = ref(false);
const subMsg = ref("");
const subOk = ref(false);
const subBtnText = computed(() => (subBusy.value ? "提交中…" : subDone.value ? "已订阅 ✓" : "订阅"));

async function doSubscribe() {
  const email = subEmail.value.trim();
  if (!email) {
    subMsg.value = "请输入邮箱地址";
    subOk.value = false;
    return;
  }
  subBusy.value = true;
  subMsg.value = "";
  try {
    const d = await apiPost("/api/subscribe", { email });
    subOk.value = true;
    subDone.value = true;
    subMsg.value = d.message || "订阅成功";
  } catch (e) {
    subOk.value = false;
    subMsg.value = e.message || "订阅失败，请稍后再试";
  } finally {
    subBusy.value = false;
  }
}

function doSearch() {
  if (q.value.trim()) router.push({ path: "/search", query: { q: q.value.trim() } });
}

onMounted(async () => {
  try {
    const [c, t, l, r] = await Promise.all([
      apiGet("/api/categories").catch(() => []),
      apiGet("/api/tags").catch(() => []),
      apiGet("/api/links").catch(() => []),
      apiGet("/api/posts", { page_size: 5 }).catch(() => ({ items: [] })),
    ]);
    cats.value = c;
    tags.value = t;
    links.value = l;
    recent.value = r.items || [];
    totalPosts.value = r.total || recent.value.length;
  } catch (e) {}
  try {
    const st = await apiGet("/api/site");
    totalComments.value = st.total_comments || 0;
  } catch (e) {}
  try {
    const sum = await apiGet("/api/stats/summary");
    hotPosts.value = (sum.hot_posts || []).slice(0, 5);
  } catch (e) {}
});
</script>
