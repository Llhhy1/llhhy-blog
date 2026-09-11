<template>
  <div>
    <!-- v3.4.1 首页渐变横幅：与后台 hero-card 同款设计语言 -->
    <div class="home-hero">
      <h2 class="home-hero-title">{{ state.site.site_name || state.site.site_title || '我的博客' }}</h2>
      <p class="home-hero-sub">{{ state.site.site_description || '记录思考，分享知识' }}</p>
    </div>

    <!-- v3.17.0 Bento Grid：站点概览数据卡 -->
    <section class="bento" aria-label="站点概览">
      <router-link class="bento-card bento-wide" to="/archive">
        <span class="bento-k">文章</span>
        <span class="bento-v">{{ siteStats.posts }}</span>
        <span class="bento-s">全部归档 →</span>
      </router-link>
      <div class="bento-card">
        <span class="bento-k">累计阅读</span>
        <span class="bento-v">{{ fmtNum(siteStats.views) }}</span>
      </div>
      <div class="bento-card">
        <span class="bento-k">分类</span>
        <span class="bento-v">{{ (state.site.categories || []).length }}</span>
      </div>
      <router-link class="bento-card" to="/hot-tags">
        <span class="bento-k">标签</span>
        <span class="bento-v">{{ (state.site.tags || []).length }}</span>
      </router-link>
      <router-link class="bento-card bento-wide" to="/links">
        <span class="bento-k">友链</span>
        <span class="bento-v">{{ (state.site.links || []).length }}</span>
        <span class="bento-s">博客圈 →</span>
      </router-link>
      <div class="bento-card">
        <span class="bento-k">评论</span>
        <span class="bento-v">{{ fmtNum(siteStats.comments) }}</span>
      </div>
    </section>

    <!-- v3.17.9：社交账号墙入口（独立页 /social；此处展示前 6 个） -->
    <section v-if="socials.length" class="home-social" aria-label="找到我">
      <div class="home-social-head">
        <h2>🔗 找到我</h2>
        <router-link to="/social" class="home-social-more">全部 {{ socials.length }} 个 →</router-link>
      </div>
      <div class="home-social-grid">
        <component
          :is="s.href ? 'a' : 'button'"
          v-for="s in socials.slice(0, 6)"
          :key="s.id"
          class="home-social-item"
          :href="s.href || null"
          :target="s.href ? '_blank' : null"
          :rel="s.href ? 'noopener' : null"
          :type="s.href ? null : 'button'"
          :title="s.handle || s.tip"
          @click="s.href ? null : onCopySocial(s)"
        >
          <span class="hs-icon" :style="{ background: s.meta.color || 'var(--surface-2)' }">{{ s.meta.icon }}</span>
          <span class="hs-label">{{ s.meta.label }}</span>
        </component>
      </div>
    </section>

    <div class="layout">
      <main class="content">
        <h1 class="page-title">✨ 最新文章</h1>
        <!-- v3.17.0 骨架屏：首屏加载中显示占位，避免「还没有文章」闪现 -->
        <template v-if="loading">
          <div v-for="n in 3" :key="n" class="skel-card">
            <div class="skel-line skel-title"></div>
            <div class="skel-line"></div>
            <div class="skel-line skel-short"></div>
          </div>
        </template>
        <template v-else>
          <p v-if="!items.length" class="empty">还没有文章。</p>
          <PostCard v-for="p in items" :key="p.slug" :post="p" v-reveal />
        </template>

      <nav v-if="!loading && totalPages > 1" class="pagination">
          <router-link v-if="page > 1" :to="{ query: { page: page - 1 } }">← 上一页</router-link>
          <span v-else class="disabled">← 上一页</span>
          <template v-for="(p, i) in pages" :key="i">
            <span v-if="p === '…'" class="ellipsis">…</span>
            <span v-else-if="p === page" class="current">{{ p }}</span>
            <router-link v-else :to="{ query: { page: p } }">{{ p }}</router-link>
          </template>
          <router-link v-if="page < totalPages" :to="{ query: { page: page + 1 } }">下一页 →</router-link>
          <span v-else class="disabled">下一页 →</span>
        </nav>
      </main>
      <Sidebar />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../lib/api.js";
import { state } from "../store.js";
import PostCard from "../components/PostCard.vue";
import Sidebar from "../components/Sidebar.vue";
import { copyText } from "../lib/clipboard.js";
import { toastOk, toastErr } from "../lib/toast.js";
import { toSocialItem } from "../lib/social.js";

const route = useRoute();
const items = ref([]);
const loading = ref(true);   // v3.17.0 骨架屏
const page = ref(1);
// v3.17.0 Bento 概览数据（/api/site 的 stats + categories/tags/links）
const siteStats = computed(() => state.site.stats || { posts: 0, views: 0, comments: 0 });

// v3.17.9：社交账号墙（独立页 /social；主页展示前 6 个）
const rawSocials = ref([]);
const socials = computed(() => (rawSocials.value || []).map(toSocialItem));
async function loadSocials() {
  try { rawSocials.value = (await apiGet("/api/social-accounts")) || []; } catch (e) { rawSocials.value = []; }
}
async function onCopySocial(s) {
  const ok = await copyText(s.url);
  if (ok) toastOk("已复制：" + s.url);
  else toastErr("已弹窗，请手动复制");
}
onMounted(loadSocials);
function fmtNum(n) {
  n = Number(n) || 0;
  if (n >= 10000) return (n / 10000).toFixed(1) + "w";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}
const totalPages = ref(1);
const PAGE_SIZE = 8;

const pages = computed(() => {
  const list = [];
  const total = totalPages.value;
  const cur = page.value;
  if (total <= 7) { for (let i = 1; i <= total; i++) list.push(i); }
  else {
    list.push(1);
    if (cur > 4) list.push("…");
    for (let i = Math.max(2, cur - 1); i <= Math.min(total - 1, cur + 1); i++) list.push(i);
    if (cur < total - 3) list.push("…");
    list.push(total);
  }
  return list;
});

async function load() {
  page.value = parseInt(route.query.page || "1", 10) || 1;
  loading.value = true;
  try {
    const data = await apiGet("/api/posts", { page: page.value, page_size: PAGE_SIZE });
    items.value = data.items || [];
    totalPages.value = data.total_pages || 1;
  } catch (e) { items.value = []; totalPages.value = 1; }
  finally { loading.value = false; }
}

onMounted(load);
watch(() => route.query.page, load);
</script>
