<template>
  <div class="layout">
    <main class="content">
      <div v-if="notFound" class="post-detail">
        <h1>找不到这篇文章</h1>
        <p class="post-meta">可能已被删除或链接错误</p>
        <p style="margin-top: 18px;"><router-link to="/">← 回到首页</router-link></p>
      </div>

      <article v-else-if="post" class="post-detail">
        <img v-if="post.cover" class="post-cover-hero" :src="post.cover" :alt="post.title" />
        <h1>{{ post.title }}</h1>
        <p class="post-meta">
          <span>{{ (post.created_at || "").slice(0, 16) }}</span>
          <span v-if="post.author"> · ✍️ {{ post.author }}</span>
          <span v-else-if="state.site.site_name"> · ✍️ {{ state.site.site_name }}</span>
          <span v-if="post.category"> · <router-link :to="`/category/${post.category.slug}`">{{ post.category.name }}</router-link></span>
          <span> · {{ post.views }} 阅读</span>
        </p>
        <nav v-if="tocItems.length" class="toc" aria-label="文章目录">
          <p class="toc-title">目录</p>
          <ul>
            <li v-for="t in tocItems" :key="t.id" :class="t.level === 3 ? 'toc-sub' : ''">
              <a :href="'#' + t.id">{{ t.text }}</a>
            </li>
          </ul>
        </nav>
        <!-- 正文渲染 -->
        <div class="post-body" ref="bodyEl"></div>
        <div v-if="post.tags && post.tags.length" class="post-tags">
          <router-link v-for="t in post.tags" :key="t.slug" class="tag" :to="`/tag/${t.slug}`">{{ t.name }}</router-link>
        </div>
        <LikeButton :slug="post.slug" :count="post.likes || 0" />
        <CommentForm :slug="post.slug" :comments="comments" />
      </article>
    </main>
    <Sidebar />
  </div>
</template>

<script setup>
import { onMounted, ref, watch, nextTick } from "vue";
import { useRoute } from "vue-router";
import { apiGet, apiPost } from "../lib/api.js";
import { state } from "../store.js";
import hljs from "highlight.js/lib/core";
import "highlight.js/styles/github.css";
import bash from "highlight.js/lib/languages/bash";
import css from "highlight.js/lib/languages/css";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("css", css);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("python", python);
hljs.registerLanguage("sql", sql);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("xml", xml);
import Sidebar from "../components/Sidebar.vue";
import LikeButton from "../components/LikeButton.vue";
import CommentForm from "../components/CommentForm.vue";

const route = useRoute();
const post = ref(null);
const comments = ref([]);
const notFound = ref(false);
const bodyEl = ref(null);
const tocItems = ref([]);

async function load() {
  const slug = route.params.slug;
  notFound.value = false;
  post.value = null;
  tocItems.value = [];
  try {
    const data = await apiGet(`/api/post/${encodeURIComponent(slug)}`);
    post.value = data;
    comments.value = data.comments || [];
    await nextTick();
    renderBody(data.html || "");
    buildToc();
    highlight();
    // 阅读埋点（统计"反复阅读"的文章）
    apiPost("/api/stats/read", { slug }).catch(() => {});
  } catch (e) {
    notFound.value = true;
  }
}

function renderBody(html) {
  if (bodyEl.value) bodyEl.value.innerHTML = html;
}

function buildToc() {
  tocItems.value = [];
  if (!bodyEl.value) return;
  const hs = bodyEl.value.querySelectorAll("h2, h3");
  hs.forEach((h, i) => {
    if (!h.id) h.id = "h-" + i;
    tocItems.value.push({ id: h.id, text: h.textContent || "", level: h.tagName === "H2" ? 2 : 3 });
  });
}

function highlight() {
  // 使用本地打包的 highlight.js（不再依赖外部 CDN，避免供应链劫持风险）
  if (!bodyEl.value) return;
  bodyEl.value.querySelectorAll("pre code").forEach((block) => {
    try { hljs.highlightElement(block); } catch (e) {}
  });
}

onMounted(load);
watch(() => route.params.slug, load);
</script>
