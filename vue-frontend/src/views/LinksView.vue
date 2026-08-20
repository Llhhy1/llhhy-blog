<template>
  <div class="container">
    <h1 class="page-title">友情链接</h1>
    <p v-if="!links.length" class="empty">还没有友链。</p>
    <ul v-else class="friend-links">
      <li v-for="l in links" :key="l.url">
        <a :href="l.url" target="_blank" rel="noopener">{{ l.name }}</a>
        <div v-if="l.description" class="desc">{{ l.description }}</div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const links = ref([]);
onMounted(async () => {
  try { links.value = await apiGet("/api/links"); } catch (e) { links.value = []; }
});
</script>
