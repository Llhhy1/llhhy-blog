<template>
  <div class="layout">
    <div class="content">
      <!-- v5.11.1：章回页首结构补齐。原来只有裸 page-title，和分类页的
           「眉标 + 衬线大标题 + 朱砂计数」是两套语言，切主题时像两个网站。 -->
      <div v-if="chapterOn()" class="zh-page-head">
        <span class="zh-page-eyebrow">{{ chapterLabels().tags_en || 'TAGS' }}</span>
        <h1 class="zh-page-title">{{ name }}</h1>
        <span class="zh-page-seal">{{ items.length }} 篇</span>
      </div>
      <h1 v-else class="page-title">标签：{{ name }}</h1>
      <p v-if="!items.length" class="empty">该标签下还没有文章。</p>
      <PostCard v-for="p in items" :key="p.slug" :post="p" />
    </div>
    <Sidebar />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { apiGet } from "../lib/api.js";
import { state } from "../store.js";
import { chapterOn, chapterLabels } from "../lib/chapter.js";
import PostCard from "../components/PostCard.vue";
import Sidebar from "../components/Sidebar.vue";

const route = useRoute();
const router = useRouter();
const items = ref([]);
const name = ref("");

async function load() {
  const slug = route.params.slug;
  try {
    const data = await apiGet(`/api/tag/${encodeURIComponent(slug)}`, { lang: state.contentLang });
    items.value = data.items || [];
    name.value = data.name ? data.name : slug;
    // v5.4.0：旧地址（中文 slug / 旧大小写写法）仍能打开，但要把地址栏换成新 slug。
    // replace 会触发下面 watch 再拉一次（仅旧地址命中时发生一次，可接受 —— 换来的是
    // 地址栏与内容严格一致）。
    if (data.moved && data.slug && data.slug !== slug) {
      router.replace({ name: "tag", params: { slug: data.slug } });
    }
  } catch (e) { items.value = []; name.value = slug; }
}
onMounted(load);
watch(() => route.params.slug, load);
watch(() => state.contentLang, load);   // v3.21.0 内容多语言：随内容语言刷新列表
</script>
