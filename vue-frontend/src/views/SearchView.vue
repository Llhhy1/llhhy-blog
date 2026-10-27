<template>
  <div class="layout">
    <div class="content">
      <h1 class="page-title">搜索{{ q ? `：${q}` : "" }}</h1>

      <!-- 搜索历史（v4.9.0）：纯前端 localStorage，最近 10 条，可点可删 -->
      <div v-if="history.length" class="search-history">
        <span class="sh-label">最近搜索</span>
        <button
          v-for="h in history"
          :key="h"
          class="sh-chip"
          :title="`搜索「${h}」`"
          @click="useHistory(h)"
        >
          {{ h }}
          <span class="sh-del" role="button" :aria-label="`删除历史 ${h}`" @click.stop="remove(h)">×</span>
        </button>
        <button class="sh-clear" @click="clearAll">清空</button>
      </div>

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
    </div>
    <Sidebar />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { apiGet, apiPost } from "../lib/api.js";
import Sidebar from "../components/Sidebar.vue";
import { getHistory, addHistory, removeHistory, clearHistory } from "../lib/searchHistory.js";

const route = useRoute();
const router = useRouter();
const q = ref("");
const items = ref([]);
const page = ref(1);
const pages = ref(1);
const loading = ref(false);
const history = ref(getHistory());

async function load() {
  q.value = route.query.q || "";
  page.value = parseInt(route.query.page || "1", 10) || 1;
  if (!q.value) { items.value = []; return; }
  history.value = addHistory(q.value);
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

function useHistory(kw) {
  router.push({ path: "/search", query: { q: kw } });
}

function remove(kw) {
  history.value = removeHistory(kw);
}

function clearAll() {
  history.value = clearHistory();
}

onMounted(load);
watch(() => route.query.q + (route.query.page || ""), load);
</script>

<style scoped>
/* 搜索历史（v4.9.0）：全部走 tokens.css 变量，明暗主题自动跟随，不硬编码颜色 */
.search-history {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1, 6px);
  margin: 0 0 16px;
}
.sh-label {
  font-size: 12px;
  color: var(--text-muted);
}
.sh-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--ui-radius-pill, 999px);
  cursor: pointer;
  transition: background var(--transition-fast, 0.15s ease),
              transform var(--ui-dur-fast, 180ms) var(--ui-ease, cubic-bezier(.32, .72, 0, 1));
}
.sh-chip:hover {
  background: var(--accent-soft);
  border-color: var(--accent);
}
/* v5.0.0 观感层：按压回弹 —— 胶囊类控件统一带触觉反馈 */
.sh-chip:active { transform: scale(.94); }
.sh-del {
  color: var(--text-faint);
  font-size: 13px;
  line-height: 1;
}
.sh-del:hover {
  color: var(--danger);
}
.sh-clear {
  padding: 2px 10px;
  font-size: 12px;
  color: var(--text-muted);
  background: var(--ui-fill, rgba(120, 120, 128, .10));
  border: 1px solid transparent;
  border-radius: var(--ui-radius-pill, 999px);
  cursor: pointer;
  text-decoration: none;
}
.sh-clear:hover {
  color: var(--danger);
}
</style>
