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
import { ref, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../lib/api.js";
import PostCard from "../components/PostCard.vue";
import Sidebar from "../components/Sidebar.vue";

const route = useRoute();
const series = ref(null);
const notFound = ref(false);

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
