<template>
  <div class="layout">
    <main class="content">
      <h1 class="page-title">文章系列</h1>
      <p class="empty" v-if="!series.length">还没有系列，去后台「系列管理」添加吧。</p>
      <div class="series-grid">
        <router-link v-for="s in series" :key="s.slug" class="series-card" :to="`/series/${s.slug}`">
          <h3>{{ s.name }}</h3>
          <p class="desc">{{ s.description || "暂无简介" }}</p>
          <p class="count">{{ s.count }} 篇文章</p>
        </router-link>
      </div>
    </main>
    <Sidebar />
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { apiGet } from "../lib/api.js";
import Sidebar from "../components/Sidebar.vue";

const series = ref([]);
onMounted(async () => {
  try { series.value = await apiGet("/api/series"); }
  catch (e) { series.value = []; }
});
</script>
