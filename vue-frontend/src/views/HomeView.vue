<template>
  <div>
    <!-- v3.4.1 首页渐变横幅：与后台 hero-card 同款设计语言 -->
    <div class="home-hero">
      <h2 class="home-hero-title">{{ state.site.site_name || state.site.site_title || '我的博客' }}</h2>
      <p class="home-hero-sub">{{ state.site.site_description || '记录思考，分享知识' }}</p>
    </div>
    <div class="layout">
      <main class="content">
        <h1 class="page-title">✨ 最新文章</h1>
        <p v-if="!items.length" class="empty">还没有文章。</p>
        <PostCard v-for="p in items" :key="p.slug" :post="p" />

      <nav v-if="totalPages > 1" class="pagination">
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

const route = useRoute();
const items = ref([]);
const page = ref(1);
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
  try {
    const data = await apiGet("/api/posts", { page: page.value, page_size: PAGE_SIZE });
    items.value = data.items || [];
    totalPages.value = data.total_pages || 1;
  } catch (e) { items.value = []; totalPages.value = 1; }
}

onMounted(load);
watch(() => route.query.page, load);
</script>
