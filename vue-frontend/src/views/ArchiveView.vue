<template>
  <div class="container">
    <h1 class="page-title">归档</h1>
    <p v-if="!groups.length" class="empty">暂无文章。</p>
    <div v-else class="timeline">
      <div v-for="g in groups" :key="g.year">
        <h3 class="tl-year">{{ g.year }}</h3>
        <div v-for="m in g.months" :key="m.month">
          <h4 class="tl-month">{{ m.month }} 月</h4>
          <p v-for="p in m.posts" :key="p.slug" class="tl-item">
            <router-link :to="`/post/${p.slug}`">{{ p.title }}</router-link>
            <span class="tl-date">{{ (p.created_at || "").slice(0, 10) }}<template v-if="p.author"> · {{ p.author }}</template></span>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const groups = ref([]);
onMounted(async () => {
  try { groups.value = await apiGet("/api/archive"); } catch (e) { groups.value = []; }
});
</script>
