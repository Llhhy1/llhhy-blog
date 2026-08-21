<template>
  <div class="layout">
    <main class="content">
      <div v-if="notFound" class="series-detail-head"><h1>找不到该系列</h1></div>
      <template v-else-if="series">
        <div class="series-detail-head">
          <h1>📚 {{ series.name }}</h1>
          <p class="desc">{{ series.description || "" }}</p>
        </div>
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
