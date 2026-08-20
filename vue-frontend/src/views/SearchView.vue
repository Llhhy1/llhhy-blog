<template>
  <div class="layout">
    <main class="content">
      <h1 class="page-title">搜索{{ q ? `：${q}` : "" }}</h1>
      <p v-if="q && !items.length" class="empty">没有匹配 "{{ q }}" 的文章。</p>
      <PostCard v-for="p in items" :key="p.slug" :post="p" />
    </main>
    <Sidebar />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet, apiPost } from "../lib/api.js";
import PostCard from "../components/PostCard.vue";
import Sidebar from "../components/Sidebar.vue";

const route = useRoute();
const q = ref("");
const items = ref([]);

async function load() {
  q.value = route.query.q || "";
  if (!q.value) { items.value = []; return; }
  // 搜索词埋点（统计常搜词汇）
  apiPost("/api/stats/search", { keyword: q.value }).catch(() => {});
  try {
    const data = await apiGet("/api/posts", { q: q.value, page_size: 50 });
    items.value = data.items || [];
  } catch (e) { items.value = []; }
}
onMounted(load);
watch(() => route.query.q, load);
</script>
