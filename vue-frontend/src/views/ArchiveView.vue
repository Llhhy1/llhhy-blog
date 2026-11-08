<template>
  <div class="container">
    <!-- v5.6.0 P2：章回结构钩子；经典分支保留原 h1，零影响。 -->
    <div v-if="chapterOn()" class="zh-page-head">
      <span class="zh-page-eyebrow">{{ chapterLabels().volume_en || 'CHAPTERS' }}</span>
      <h1 class="zh-page-title">归档</h1>
      <span class="zh-page-seal">{{ groups.length }} 卷</span>
    </div>
    <h1 v-else class="page-title">归档</h1>
    <!-- v5.6.0 P1：四态统一，加载失败不再伪装成「暂无文章」。 -->
    <AsyncState
      :state="viewState"
      :message="viewState === 'error' ? '归档加载失败，请重试' : '暂无文章。'"
      :retry="loadArchive"
    >
      <div class="timeline">
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
    </AsyncState>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";
import { chapterOn, chapterLabels } from "../lib/chapter.js";
import AsyncState from "../components/AsyncState.vue";

const groups = ref([]);
const viewState = ref("loading");

async function loadArchive() {
  viewState.value = "loading";
  try {
    groups.value = await apiGet("/api/archive");
    viewState.value = groups.value.length ? "ready" : "empty";
  } catch (e) {
    groups.value = [];
    viewState.value = "error";
  }
}
onMounted(loadArchive);
</script>
