<template>
  <div class="layout">
    <main class="content">
      <h1 class="page-title">标签：{{ name }}</h1>
      <p v-if="!items.length" class="empty">该标签下还没有文章。</p>
      <PostCard v-for="p in items" :key="p.slug" :post="p" />
    </main>
    <Sidebar />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../lib/api.js";
import PostCard from "../components/PostCard.vue";
import Sidebar from "../components/Sidebar.vue";

const route = useRoute();
const items = ref([]);
const name = ref("");

async function load() {
  const slug = route.params.slug;
  try {
    const data = await apiGet(`/api/tag/${encodeURIComponent(slug)}`);
    items.value = data.items || [];
    name.value = data.name ? data.name : slug;
  } catch (e) { items.value = []; name.value = slug; }
}
onMounted(load);
watch(() => route.params.slug, load);
</script>
