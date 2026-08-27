<template>
  <div class="layout">
    <main class="content">
      <div v-if="notFound" class="series-detail-head"><h1>找不到该系列</h1></div>
      <template v-else-if="series">
        <div class="series-detail-head">
          <h1>📚 {{ series.name }}</h1>
          <p class="desc">{{ series.description || "" }}</p>
          <p class="series-count">共 {{ series.posts.length }} 篇</p>
        </div>
        <!-- v3.8.6：本系列热门标签（按该系列文章标签出现频次排序，点击跳转到 /tag/:slug） -->
        <div v-if="hotTags.length" class="series-hot-tags">
          <div class="series-hot-tags-title">🔥 本系列热门标签</div>
          <div class="hot-tag-cloud">
            <router-link
              v-for="t in hotTags"
              :key="t.slug"
              :to="`/tag/${t.slug}`"
              class="hot-tag"
              :style="{ fontSize: sizeOf(t), opacity: opacityOf(t) }"
            >
              {{ t.name }} <span class="hot-tag-count">{{ t.count }}</span>
            </router-link>
          </div>
        </div>
        <!-- 系列目录页（v3.0.0 功能1）：编号章节索引，点击直达 -->
        <ol v-if="series.posts.length" class="series-toc">
          <li v-for="(p, i) in series.posts" :key="p.slug">
            <span class="chapter-no">{{ i + 1 }}</span>
            <router-link :to="`/post/${p.slug}`">{{ p.title }}</router-link>
            <span class="chapter-meta">{{ (p.created_at || "").slice(0, 10) }}</span>
          </li>
        </ol>
        <PostCard v-for="p in series.posts" :key="p.slug" :post="p" />
        <p v-if="!series.posts.length" class="empty">该系列还没有文章。</p>
      </template>
    </main>
    <Sidebar />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../lib/api.js";
import PostCard from "../components/PostCard.vue";
import Sidebar from "../components/Sidebar.vue";

const route = useRoute();
const series = ref(null);
const notFound = ref(false);

// v3.8.6：本系列热门标签（统计该系列所有文章标签的出现频次，取前 20）
const hotTags = computed(() => {
  if (!series.value || !series.value.posts) return [];
  const freq = {};
  for (const p of series.value.posts) {
    for (const tag of (p.tags || [])) {
      if (!tag.slug) continue;
      freq[tag.slug] = freq[tag.slug] || { slug: tag.slug, name: tag.name, count: 0 };
      freq[tag.slug].count += 1;
    }
  }
  const list = Object.values(freq).sort((a, b) => b.count - a.count).slice(0, 20);
  maxCount.value = Math.max(1, ...list.map((t) => t.count));
  return list;
});
const maxCount = ref(1);
function sizeOf(t) {
  const ratio = t.count / maxCount.value;
  return (14 + ratio * 14).toFixed(0) + "px";
}
function opacityOf(t) {
  const ratio = t.count / maxCount.value;
  return (0.6 + ratio * 0.4).toFixed(2);
}

async function load() {
  notFound.value = false;
  series.value = null;
  try {
    const d = await apiGet(`/api/series/${route.params.slug}`);
    series.value = d;
  } catch (e) {
    notFound.value = true;
  }
}
onMounted(load);
watch(() => route.params.slug, load);
</script>

<style scoped>
.series-hot-tags {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 22px;
}
.series-hot-tags-title {
  font-size: 14px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 12px;
}
.hot-tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  align-items: center;
}
.hot-tag {
  color: var(--accent, #3b82f6);
  text-decoration: none;
  line-height: 1.4;
  transition: color 0.15s;
}
.hot-tag:hover {
  text-decoration: underline;
}
.hot-tag-count {
  font-size: 11px;
  color: #94a3b8;
  vertical-align: super;
}
[data-theme="dark"] .series-hot-tags {
  background: #1d2025;
  border-color: #2a2e35;
}
[data-theme="dark"] .series-hot-tags-title {
  color: #c7ccd1;
}
[data-theme="dark"] .hot-tag-count {
  color: #64748b;
}
</style>

