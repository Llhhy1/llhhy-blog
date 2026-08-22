<template>
  <div class="layout">
    <main class="content">
      <h1 class="page-title">搜索{{ q ? `：${q}` : "" }}</h1>
      <p v-if="q && !items.length && !loading" class="empty">没有匹配 "{{ q }}" 的文章。</p>
      <p v-if="loading" class="empty">搜索中…</p>
      <div v-for="p in items" :key="p.slug" class="search-item">
        <h2>
          <span v-if="p.is_pinned" class="pin-badge" title="置顶文章">📌</span>
          <router-link :to="`/post/${p.slug}`">{{ p.title }}</router-link>
        </h2>
        <p class="post-meta">
          <span>{{ (p.created_at || "").slice(0, 10) }}</span>
          <span v-if="p.category"> · <router-link :to="`/category/${p.category.slug}`">{{ p.category.name }}</router-link></span>
          <span> · {{ p.views || 0 }} 阅读</span>
        </p>
        <!-- 命中词高亮（v3.0.0 功能3）：服务端已转义并包裹 <mark>，此处可信渲染 -->
        <p class="search-snippet" v-html="p.highlight || p.summary || ''"></p>
      </div>

      <!-- 分页（v3.0.0 功能3） -->
      <nav v-if="pages > 1" class="pagination">
        <button :disabled="page <= 1" @click="go(page - 1)">← 上一页</button>
        <span class="current">{{ page }} / {{ pages }}</span>
        <button :disabled="page >= pages" @click="go(page + 1)">下一页 →</button>
      </nav>
    </main>
    <Sidebar />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { apiGet, apiPost } from "../lib/api.js";
import Sidebar from "../components/Sidebar.vue";

const route = useRoute();
const router = useRouter();
const q = ref("");
const items = ref([]);
const page = ref(1);
const pages = ref(1);
const loading = ref(false);

async function load() {
  q.value = route.query.q || "";
  page.value = parseInt(route.query.page || "1", 10) || 1;
  if (!q.value) { items.value = []; return; }
  loading.value = true;
  apiPost("/api/stats/search", { keyword: q.value }).catch(() => {});
  try {
    const data = await apiGet("/api/search", { q: q.value, page: page.value, per_page: 10 });
    items.value = data.items || [];
    pages.value = data.pages || 1;
    page.value = data.page || 1;
  } catch (e) { items.value = []; }
  loading.value = false;
}

function go(p) {
  if (p < 1 || p > pages.value) return;
  router.push({ path: "/search", query: { q: q.value, page: p } });
}

onMounted(load);
watch(() => route.query.q + (route.query.page || ""), load);
</script>
