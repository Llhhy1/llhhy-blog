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
          <button class="share-btn" type="button" @click="shareTip ? closeTip() : openShare()">📤 分享到…</button>
          <div v-if="shareOpen" class="share-panel">
            <p class="share-panel-title">分享「{{ (post.title || '').slice(0, 30) }}」</p>
            <div class="share-grid">
              <button class="share-item" type="button" @click="sharePost">🔗 复制链接</button>
              <a class="share-item" :href="shareUrl('weibo')" target="_blank" rel="noopener">🅾️ 微博</a>
              <a class="share-item" :href="shareUrl('qq')" target="_blank" rel="noopener">🐧 QQ</a>
              <button class="share-item" type="button" @click="sharePost">💬 微信（复制后去微信粘贴）</button>
              <a class="share-item" :href="shareUrl('x')" target="_blank" rel="noopener">𝕏 Twitter/X</a>
              <a class="share-item" :href="shareUrl('telegram')" target="_blank" rel="noopener">✈️ Telegram</a>
              <a class="share-item" :href="shareUrl('facebook')" target="_blank" rel="noopener">f Facebook</a>
              <a class="share-item" :href="shareUrl('linkedin')" target="_blank" rel="noopener">in LinkedIn</a>
            </div>
            <p class="share-hint">微博/QQ/X/TG/FB/LinkedIn 会自动抓取文章卡片（标题/摘要/封面由服务端渲染）。</p>
          </div>
          <span v-if="shareTip" class="share-tip">{{ shareTip }}</span>
        </div>

        <LikeButton :slug="post.slug" :count="post.likes || 0" />
        <CommentForm :slug="post.slug" />
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
const notFound = ref(false);
const bodyEl = ref(null);
const tocItems = ref([]);
const related = ref([]);
const shareTip = ref("");
const shareOpen = ref(false);
const rewardQrDefault = ref("");

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

function sharePost() {
  const url = location.href;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).then(() => {
      shareTip.value = "链接已复制，去分享吧！";
      setTimeout(() => { shareTip.value = ""; }, 2000);
    }).catch(() => { shareTip.value = url; });
  } else {
    shareTip.value = url;
  }
}

function openShare() {
  shareOpen.value = !shareOpen.value;
  shareTip.value = "";
}
function closeTip() { shareTip.value = ""; }

function shareUrl(platform) {
  const url = location.href;
  const title = (post.value && post.value.title) || document.title;
  const desc = (post.value && (post.value.seo_description || post.value.summary)) || "";
  const u = encodeURIComponent(url);
  const t = encodeURIComponent(title + (desc ? "：" + desc.slice(0, 80) : ""));
  const map = {
    weibo: `https://service.weibo.com/share/share.php?url=${u}&title=${t}`,
    qq: `https://connect.qq.com/widget/shareqq/index.html?url=${u}&title=${t}&summary=${encodeURIComponent(desc.slice(0, 120))}`,
    x: `https://twitter.com/intent/tweet?url=${u}&text=${t}`,
    telegram: `https://t.me/share/url?url=${u}&text=${t}`,
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${u}`,
    linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${u}`,
  };
  return map[platform] || u;
}

onMounted(() => {
  load();
});
watch(() => route.params.slug, () => { load(); });
</script>

<style scoped>
.share-row {
  position: relative;
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
  margin-top: 18px;
}
.share-btn {
  border: 1px solid #ddd; background: #fff; color: #333; cursor: pointer;
  padding: 7px 14px; border-radius: 999px; font-size: 14px;
}
.share-tip { color: #2e7d32; font-size: 13px; }
.share-panel {
  position: absolute; left: 0; top: calc(100% + 8px); z-index: 30;
  width: min(420px, 92vw);
  background: var(--surface, #fff); border: 1px solid #e2e2e2;
  border-radius: 14px; padding: 12px 14px;
  box-shadow: 0 10px 30px rgba(20, 30, 60, .14);
}
.share-panel-title { margin: 0 0 10px; font-size: 13px; color: #666; }
.share-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
.share-item {
  display: block; text-align: center; text-decoration: none;
  border: 1px solid #e5e5e5; background: #fafafa; color: #333;
  border-radius: 10px; padding: 8px 6px; font-size: 13px; cursor: pointer;
}
.share-item:hover { border-color: var(--accent, #1a73e8); color: var(--accent, #1a73e8); }
.share-hint { margin: 10px 0 0; font-size: 12px; color: #999; line-height: 1.6; }
</style>
