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
          <span v-if="post.word_count"> · 📖 {{ post.word_count }} 字 / {{ post.reading_minutes }} 分钟</span>
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

        <div v-if="post.series" class="series-nav">
          <span class="series-name">📚 系列：<router-link :to="`/series/${post.series.slug}`">{{ post.series.name }}</router-link></span>
          <div class="series-prev-next">
            <router-link v-if="post.series.prev" :to="`/post/${post.series.prev.slug}`" class="series-link">← {{ post.series.prev.title }}</router-link>
            <span v-else class="series-link disabled">已是第一篇</span>
            <router-link v-if="post.series.next" :to="`/post/${post.series.next.slug}`" class="series-link">{{ post.series.next.title }} →</router-link>
            <span v-else class="series-link disabled">已是最后一篇</span>
          </div>
        </div>

        <div v-if="related.length" class="related-box">
          <h3 class="related-title">看了又看</h3>
          <ul class="related-list">
            <li v-for="r in related" :key="r.slug">
              <router-link :to="`/post/${r.slug}`">{{ r.title }}</router-link>
            </li>
          </ul>
        </div>

        <!-- 文章打赏（v3.0.0 功能14：仅超管开启时显示） -->
        <div v-if="post.reward_enabled" class="reward-box">
          <p class="reward-title">💝 觉得有用？请作者喝杯咖啡</p>
          <img v-if="post.reward_qr || rewardQrDefault" class="reward-qr" :src="post.reward_qr || rewardQrDefault" alt="打赏二维码" />
          <p v-else class="reward-hint">作者暂未上传收款二维码</p>
        </div>

        <div class="share-row">
          <SharePanel :title="post.title" :slug="post.slug" />
        </div>

        <LikeButton :slug="post.slug" :count="post.likes || 0" />
        <CommentForm :slug="post.slug" />
      </article>
    </main>
    <Sidebar />

    <!-- v3.16.0 图片灯箱：点击正文图片放大预览，支持 ←/→ 切换、Esc 关闭 -->
    <div v-if="lbIndex >= 0" class="lightbox" @click="lbClose">
      <button class="lb-close" type="button" aria-label="关闭" @click.stop="lbClose">×</button>
      <img class="lb-img" :src="lbImgs[lbIndex]" alt="预览大图" @click.stop />
      <button v-if="lbImgs.length > 1" class="lb-nav lb-prev" type="button" aria-label="上一张" @click.stop="lbStep(-1)">‹</button>
      <button v-if="lbImgs.length > 1" class="lb-nav lb-next" type="button" aria-label="下一张" @click.stop="lbStep(1)">›</button>
      <span class="lb-count" v-if="lbImgs.length > 1">{{ lbIndex + 1 }} / {{ lbImgs.length }}</span>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from "vue";
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
import SharePanel from "../components/SharePanel.vue";

const route = useRoute();
const post = ref(null);
const notFound = ref(false);
const bodyEl = ref(null);
const tocItems = ref([]);
const related = ref([]);
const rewardQrDefault = ref("");
// v3.16.0 图片灯箱
const lbImgs = ref([]);
const lbIndex = ref(-1);
function lbClose() { lbIndex.value = -1; }
function lbStep(d) {
  if (!lbImgs.value.length) return;
  lbIndex.value = (lbIndex.value + d + lbImgs.value.length) % lbImgs.value.length;
}
function lbKey(e) {
  if (lbIndex.value < 0) return;
  if (e.key === "Escape") lbClose();
  if (e.key === "ArrowLeft") lbStep(-1);
  if (e.key === "ArrowRight") lbStep(1);
}

async function load() {
  const slug = route.params.slug;
  notFound.value = false;
  post.value = null;
  tocItems.value = [];
  try {
    const data = await apiGet(`/api/post/${encodeURIComponent(slug)}`);
    post.value = data;
    related.value = [];
    rewardQrDefault.value = state.site.reward_qr_default || "";
    await nextTick();
    renderBody(data.html || "");
    buildToc();
    highlight();
    enhanceBody();
    setOgMeta(data);
    // 阅读埋点（统计"反复阅读"的文章）
    apiPost("/api/stats/read", { slug }).catch(() => {});
    // 「看了又看」协同过滤推荐（v3.0.0 功能8）
    apiGet(`/api/post/${encodeURIComponent(slug)}/also-viewed`)
      .then((r) => { related.value = r.items || []; }).catch(() => {});
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

// v3.16.0 正文增强：图片灯箱 + 代码块复制（在 highlight 之后调用）
function enhanceBody() {
  const root = bodyEl.value;
  if (!root) return;
  // 1) 图片灯箱（跳过被链接包裹的图片，避免与外链冲突）
  const imgs = [...root.querySelectorAll("img")].filter((i) => !i.closest("a"));
  imgs.forEach((img) => {
    img.classList.add("img-zoomable");
    img.addEventListener("click", () => {
      lbImgs.value = imgs.map((i) => i.currentSrc || i.src);
      lbIndex.value = imgs.indexOf(img);
    });
  });
  // 2) 代码块复制按钮（pre 定位锚点，按钮绝对定位右上角）
  root.querySelectorAll("pre").forEach((pre) => {
    if (pre.querySelector(".code-copy-btn")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "code-copy-btn";
    btn.textContent = "复制";
    btn.addEventListener("click", async () => {
      const text = (pre.querySelector("code") || pre).innerText;
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = "已复制 ✓";
      } catch (e) {
        btn.textContent = "复制失败";
      }
      setTimeout(() => { btn.textContent = "复制"; }, 1800);
    });
    pre.appendChild(btn);
  });
}

// 动态注入 Open Graph 分享元信息（D1 · 分享卡片）
function setOgMeta(p) {
  document.title = (p.title || "") + " · " + (state.site.site_name || state.site.site_title);
  const set = (prop, content) => {
    let m = document.querySelector(`meta[property="${prop}"]`) || document.querySelector(`meta[name="${prop}"]`);
    if (!m) {
      m = document.createElement("meta");
      m.setAttribute(prop.startsWith("og:") ? "property" : "name", prop);
      document.head.appendChild(m);
    }
    m.setAttribute("content", content || "");
  };
  set("og:title", p.title);
  set("og:description", p.seo_description || p.summary || (p.content || "").slice(0, 120));
  // v3.15.0：og:image 必须是绝对 URL，且无封面时回退站点默认分享图（微信/QQ 卡片硬性要求）
  let img = p.cover || "";
  try { if (img && !/^https?:\/\//i.test(img)) img = new URL(img, location.origin).href; } catch (e) {}
  if (!img) img = new URL("/og-default.png", location.origin).href;
  set("og:image", img);
  set("og:url", location.href);
  set("og:type", "article");
  set("description", p.seo_description || p.summary || "");
  set("keywords", p.seo_keywords || (p.tags || []).map((t) => t.name).join(","));
}

onMounted(() => {
  load();
  document.addEventListener("keydown", lbKey);
});
onBeforeUnmount(() => {
  document.removeEventListener("keydown", lbKey);
});
watch(() => route.params.slug, () => { load(); });
</script>

<style scoped>
.share-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
  margin-top: 18px;
}

/* v3.16.0 正文增强：图片灯箱 + 代码复制（作用于 v-html 注入的内容，必须用 :deep 命中） */
.post-body :deep(.img-zoomable) {
  cursor: zoom-in; transition: transform .2s ease;
}
.post-body :deep(.img-zoomable:hover) { transform: scale(1.012); }

.post-body :deep(pre) { position: relative; }
.post-body :deep(.code-copy-btn) {
  position: absolute; top: 8px; right: 8px; z-index: 5;
  border: 1px solid var(--border, #e2e2e2); background: rgba(255,255,255,.9); color: #444;
  border-radius: 8px; padding: 3px 10px; font-size: 12px; cursor: pointer;
  opacity: .82; transition: opacity .18s ease, color .18s ease, border-color .18s ease;
}
.post-body :deep(pre):hover .code-copy-btn { opacity: 1; }
.post-body :deep(.code-copy-btn:hover) { color: var(--accent, #1a73e8); border-color: var(--accent, #1a73e8); }

/* v3.16.0 图片灯箱（模板内元素，scoped 正常生效） */
.lightbox {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.86); padding: 24px;
  animation: lb-fade .2s ease;
}
@keyframes lb-fade { from { opacity: 0; } to { opacity: 1; } }
.lb-img {
  max-width: 92vw; max-height: 88vh; border-radius: 10px;
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
  animation: lb-pop .24s cubic-bezier(.2,.8,.2,1);
}
@keyframes lb-pop { from { transform: scale(.94); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.lb-close {
  position: fixed; top: 18px; right: 22px; z-index: 1001;
  width: 42px; height: 42px; border-radius: 50%; border: none;
  background: rgba(255,255,255,.16); color: #fff; font-size: 26px; line-height: 1;
  cursor: pointer; transition: background .18s ease;
}
.lb-close:hover { background: rgba(255,255,255,.32); }
.lb-nav {
  position: fixed; top: 50%; transform: translateY(-50%); z-index: 1001;
  width: 48px; height: 48px; border-radius: 50%; border: none;
  background: rgba(255,255,255,.16); color: #fff; font-size: 30px; line-height: 1;
  cursor: pointer; transition: background .18s ease;
}
.lb-nav:hover { background: rgba(255,255,255,.32); }
.lb-prev { left: 20px; }
.lb-next { right: 20px; }
.lb-count {
  position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%);
  color: #fff; font-size: 13px; background: rgba(0,0,0,.4);
  padding: 4px 12px; border-radius: 999px;
}
</style>
