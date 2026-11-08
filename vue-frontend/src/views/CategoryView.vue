<template>
  <div class="layout">
    <div class="content">
      <!-- v5.6.0 P2：章回结构钩子（眉标 / 衬线大标题 / 朱砂计数）；
           v-else 分支保留经典标题，DOM 零影响。 -->
      <div v-if="chapterOn()" class="zh-page-head">
        <span class="zh-page-eyebrow">{{ chapterLabels().categories_en || 'CATEGORIES' }}</span>
        <h1 class="zh-page-title">{{ name }}</h1>
        <span class="zh-page-seal">{{ items.length }} 篇</span>
      </div>
      <h1 v-else class="page-title">分类：{{ name }}</h1>
      <!-- v5.6.0 P1：四态统一。原来只有「空」一种，请求失败会把分类名
           冒充空列表，用户看不出是没文章还是加载挂了。 -->
      <AsyncState
        :state="viewState"
        :message="viewState === 'error' ? '分类加载失败，请重试' : '该分类下还没有文章。'"
        :retry="load"
      >
        <PostCard v-for="p in items" :key="p.slug" :post="p" />
      </AsyncState>
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
import AsyncState from "../components/AsyncState.vue";
import PostCard from "../components/PostCard.vue";
import Sidebar from "../components/Sidebar.vue";

const route = useRoute();
const router = useRouter();
const items = ref([]);
const name = ref("");
const viewState = ref("loading");

async function load() {
  const slug = route.params.slug;
  viewState.value = "loading";
  try {
    const data = await apiGet(`/api/category/${encodeURIComponent(slug)}`, { lang: state.contentLang });
    items.value = data.items || [];
    name.value = data.name ? data.name : slug;
    viewState.value = items.value.length ? "ready" : "empty";
    // v5.4.0：旧地址（中文 slug / 旧大小写写法）→ 地址栏换成新 slug
    if (data.moved && data.slug && data.slug !== slug) {
      router.replace({ name: "category", params: { slug: data.slug } });
    }
  } catch (e) { items.value = []; name.value = slug; viewState.value = "error"; }
}
onMounted(load);
watch(() => route.params.slug, load);
watch(() => state.contentLang, load);   // v3.21.0 内容多语言：随内容语言刷新列表
</script>
