<template>
  <div class="layout">
    <main class="content">
      <h1 class="page-title">🔥 热门标签</h1>
      <p class="empty" v-if="!tags.length">还没有标签数据</p>
      <div class="hot-tag-cloud">
        <router-link
          v-for="t in tags"
          :key="t.slug"
          :to="`/tag/${t.slug}`"
          class="hot-tag"
          :style="{ fontSize: sizeOf(t), opacity: opacityOf(t) }"
        >
          {{ t.name }} <span class="hot-tag-count">{{ t.count }}</span>
        </router-link>
      </div>
    </main>
    <Sidebar />
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";
import Sidebar from "../components/Sidebar.vue";

const tags = ref([]);
const maxCount = ref(1);

async function load() {
  try {
    const d = await apiGet("/api/hot-tags", { limit: 30 });
    tags.value = d.items || [];
    maxCount.value = Math.max(1, ...tags.value.map((t) => t.count));
  } catch (e) { tags.value = []; }
}

function sizeOf(t) {
  // 字号随文章数在 14~28px 之间映射
  const ratio = t.count / maxCount.value;
  return (14 + ratio * 14).toFixed(0) + "px";
}
function opacityOf(t) {
  const ratio = t.count / maxCount.value;
  return (0.6 + ratio * 0.4).toFixed(2);
}

onMounted(load);
</script>
