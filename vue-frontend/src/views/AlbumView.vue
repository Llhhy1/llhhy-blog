<template>
  <div class="container album-page">
    <div v-if="loading" class="album-empty">{{ t("loading") }}</div>

    <div v-else-if="!album" class="album-empty">{{ t("album_missing") }}</div>

    <template v-else>
      <!-- 封面：不设封面时自动用第一张图（后端已回退） -->
      <div v-if="coverUrl" class="album-hero">
        <img :src="coverUrl" :alt="album.title" @click="openLightbox(0)">
        <div class="album-hero-mask">
          <h1 class="album-h1">{{ album.title }}</h1>
          <p v-if="album.summary" class="album-hero-sub">{{ album.summary }}</p>
          <p class="album-hero-meta">
            <template v-if="album.event_date">{{ album.event_date }}</template>
            <template v-if="album.location"> · {{ album.location }}</template>
            <template v-if="album.trip_days"> · {{ album.trip_days }}</template>
            <span> · {{ album.count }} {{ t("items") }}</span>
          </p>
        </div>
      </div>
      <header v-else class="album-head-plain">
        <h1 class="album-h1">{{ album.title }}</h1>
        <p v-if="album.summary" class="album-sub">{{ album.summary }}</p>
        <p class="album-meta-plain">
          <template v-if="album.event_date">{{ album.event_date }}</template>
          <template v-if="album.location"> · {{ album.location }}</template>
          <template v-if="album.trip_days"> · {{ album.trip_days }}</template>
          <span> · {{ album.count }} {{ t("items") }}</span>
        </p>
      </header>

      <!-- 行程概览：留空则整块不出现 -->
      <section v-if="introBlocks.length" class="album-block">
        <h2 class="album-block-title">{{ t("album_intro") }}</h2>
        <div class="album-prose">
          <template v-for="(b, i) in introBlocks" :key="'i' + i">
            <ul v-if="b.type === 'ul'"><li v-for="(li, j) in b.items" :key="j"><template v-for="(tk, k) in li" :key="k"><strong v-if="tk.bold">{{ tk.text }}</strong><span v-else>{{ tk.text }}</span></template></li></ul>
            <p v-else><template v-for="(ln, li) in b.lines" :key="li"><br v-if="li"><template v-for="(tk, k) in ln" :key="k"><strong v-if="tk.bold">{{ tk.text }}</strong><span v-else>{{ tk.text }}</span></template></template></p>
          </template>
        </div>
      </section>

      <!-- 章节：每组一段文字 + 一组媒体 -->
      <section v-for="s in album.sections" :key="s.id" class="album-block album-section">
        <h2 class="album-block-title">{{ s.title || t("untitled") }}</h2>
        <div v-if="s.summary" class="album-prose album-section-note">
          <template v-for="(b, i) in blocksOf(s.summary)" :key="'s' + i">
            <ul v-if="b.type === 'ul'"><li v-for="(li, j) in b.items" :key="j"><template v-for="(tk, k) in li" :key="k"><strong v-if="tk.bold">{{ tk.text }}</strong><span v-else>{{ tk.text }}</span></template></li></ul>
            <p v-else><template v-for="(ln, li) in b.lines" :key="li"><br v-if="li"><template v-for="(tk, k) in ln" :key="k"><strong v-if="tk.bold">{{ tk.text }}</strong><span v-else>{{ tk.text }}</span></template></template></p>
          </template>
        </div>
        <div class="album-media-grid">
          <figure v-for="it in s.items" :key="it.id" class="album-media">
            <div v-if="it.media.kind === 'video'" class="album-media-box is-video">
              <video :src="it.media.url" :poster="it.media.poster || undefined"
                     :data-video-id="it.id"
                     preload="metadata" playsinline
                     @click.stop="toggleVideo(it)"
                     @ended="onVideoEnded"></video>
              <button v-if="!playingIds.has(it.id)" class="album-video-play"
                      type="button" aria-label="播放"
                      @click.stop="playVideo(it)">
                <span class="album-video-play-icon">▶</span>
              </button>
            </div>
            <div v-else class="album-media-box is-image" @click="openLightboxByItem(it)">
              <img :src="it.media.url" :alt="capOf(it)" loading="lazy">
            </div>
            <figcaption v-if="capOf(it)" class="album-caption">{{ capOf(it) }}</figcaption>
          </figure>
        </div>
      </section>

      <!-- 未分组条目（没有章节时这里就是全部照片） -->
      <section v-if="album.items && album.items.length" class="album-block">
        <h2 v-if="album.sections && album.sections.length" class="album-block-title">{{ t("album_loose") }}</h2>
        <div class="album-media-grid">
          <figure v-for="it in album.items" :key="it.id" class="album-media">
            <div v-if="it.media.kind === 'video'" class="album-media-box is-video">
              <video :src="it.media.url" :poster="it.media.poster || undefined"
                     :data-video-id="it.id"
                     preload="metadata" playsinline
                     @click.stop="toggleVideo(it)"
                     @ended="onVideoEnded"></video>
              <button v-if="!playingIds.has(it.id)" class="album-video-play"
                      type="button" aria-label="播放"
                      @click.stop="playVideo(it)">
                <span class="album-video-play-icon">▶</span>
              </button>
            </div>
            <div v-else class="album-media-box is-image" @click="openLightboxByItem(it)">
              <img :src="it.media.url" :alt="capOf(it)" loading="lazy">
            </div>
            <figcaption v-if="capOf(it)" class="album-caption">{{ capOf(it) }}</figcaption>
          </figure>
        </div>
      </section>

      <!-- 小提示 -->
      <section v-if="tipBlocks.length" class="album-block album-tips">
        <h2 class="album-block-title">{{ t("album_tips") }}</h2>
        <div class="album-prose">
          <template v-for="(b, i) in tipBlocks" :key="'t' + i">
            <ul v-if="b.type === 'ul'"><li v-for="(li, j) in b.items" :key="j"><template v-for="(tk, k) in li" :key="k"><strong v-if="tk.bold">{{ tk.text }}</strong><span v-else>{{ tk.text }}</span></template></li></ul>
            <p v-else><template v-for="(ln, li) in b.lines" :key="li"><br v-if="li"><template v-for="(tk, k) in ln" :key="k"><strong v-if="tk.bold">{{ tk.text }}</strong><span v-else>{{ tk.text }}</span></template></template></p>
          </template>
        </div>
      </section>
    </template>

    <!-- 灯箱 -->
    <div v-if="lightbox !== null" class="lightbox" @click.self="closeLightbox">
      <button class="lb-close" :aria-label="t('close')" @click="closeLightbox">×</button>
      <button v-if="images.length > 1" class="lb-nav lb-prev" :aria-label="t('prev')" @click="step(-1)">‹</button>
      <figure class="lb-body">
        <img :src="images[lightbox]?.media.url" :alt="capOf(images[lightbox])">
        <figcaption v-if="capOf(images[lightbox])" class="lb-caption">
          {{ capOf(images[lightbox]) }}
          <span class="lb-count">{{ lightbox + 1 }} / {{ images.length }}</span>
        </figcaption>
      </figure>
      <button v-if="images.length > 1" class="lb-nav lb-next" :aria-label="t('next')" @click="step(1)">›</button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../lib/api.js";
import { t } from "../store.js";

const route = useRoute();
const album = ref(null);
const loading = ref(true);
const lightbox = ref(null);

const coverUrl = computed(() => {
  const c = album.value && album.value.cover;
  return c && c.url ? c.url : "";
});

/* 灯箱只收图片：视频有自己的播放器，不需要放大 */
const images = computed(() => {
  const out = [];
  if (!album.value) return out;
  for (const s of album.value.sections || []) {
    for (const it of s.items || []) if (it.media && it.media.kind === "image") out.push(it);
  }
  for (const it of album.value.items || []) if (it.media && it.media.kind === "image") out.push(it);
  return out;
});

/* 极简分段：空行分段，整段都是「- x」就渲染成列表。
   刻意不引 markdown 库、不用 v-html —— 少一个 XSS 面。 */
/**
 * 把一行文字按 `**粗体**` 切成片段。
 *
 * 为什么不直接上 markdown 库：这两块（行程概览 / 小提示）是管理员写的长文本，
 * 但只要能分段、列表、粗体就够了。引一个解析器等于把 `v-html` 请回来，
 * 多一个 XSS 面。token 化之后仍然走 Vue 插值，HTML 永远不会被当作标签执行。
 *
 * 未成对的 `**` 会被当作普通文本保留（split 后按索引奇偶判断，多余的一段
 * 仍然有内容），不会吞掉用户写错的字符。
 */
function tokenizeInline(line) {
  const out = [];
  String(line).split("**").forEach((seg, i) => {
    if (seg) out.push({ text: seg, bold: i % 2 === 1 });
  });
  return out.length ? out : [{ text: "", bold: false }];
}

function blocksOf(text) {
  const out = [];
  const paras = String(text || "").split(/\n\s*\n/);
  for (const p of paras) {
    const lines = p.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!lines.length) continue;
    if (lines.every((l) => /^[-*]\s+/.test(l))) {
      out.push({ type: "ul", items: lines.map((l) => tokenizeInline(l.replace(/^[-*]\s+/, ""))) });
    } else {
      out.push({ type: "p", lines: lines.map((l) => tokenizeInline(l)) });
    }
  }
  return out;
}

const introBlocks = computed(() => blocksOf(album.value && album.value.intro));
const tipBlocks = computed(() => blocksOf(album.value && album.value.tips));

/**
 * 图注 = 这张图的**名字**，只有一份，存在媒体库的 `media.title`。
 *
 * v5.2.0 曾把 caption（相册语境说明）与素材标题并存，靠这里回退兜底；
 * 实测用户不认这个区分 —— 在相册里起了名，回媒体库还是一串文件名。
 * v5.2.1 起名字统一走 media.title，在相册编排页改名就是改它。
 *
 * 保留 `it.caption` 分支只为兼容尚未迁移的旧数据（此时它仍优先）；
 * 迁移 b7c2e91a4d63 跑完后 caption 恒空，实际总是取 media.title。
 */
function capOf(it) {
  if (!it) return "";
  return it.caption || (it.media && it.media.title) || "";
}

function openLightbox(idx) { if (images.value.length) lightbox.value = idx; }
function openLightboxByItem(it) {
  const idx = images.value.findIndex((x) => x.id === it.id);
  if (idx >= 0) lightbox.value = idx;
}
function closeLightbox() { lightbox.value = null; }function step(d) {
  const n = images.value.length;
  if (!n) return;
  lightbox.value = (lightbox.value + d + n) % n;
}
function onKey(e) {
  if (lightbox.value === null) return;
  if (e.key === "Escape") closeLightbox();
  else if (e.key === "ArrowLeft") step(-1);
  else if (e.key === "ArrowRight") step(1);
}

/* ------------------------------------------------------------------ 视频播放 */

/**
 * 视频卡片**不用原生 `controls`** —— 这是「点一下就悬浮在最上层、挡住看图片」的根因。
 *
 * 移动端（iOS Safari / 微信内置浏览器）里，用户点到一个带 `controls` 的 `<video>`，
 * 系统会直接接管成**原生全屏播放器**：那是一层盖在整个页面上的系统浮层，
 * 退出后部分浏览器还会把 video 元素留在视口顶层继续挡着内容。
 *
 * 改成自绘播放按钮：用户点的是**按钮**（普通 DOM），JS 再调 `video.play()`。
 * 因为有 `playsinline`，这次调用走**内联播放**，不触发系统全屏接管。
 * 真需要全屏时，播放中才把原生 `controls` 挂上，用户可以在控件里自己选。
 */
const playingIds = ref(new Set());

function videoElOf(it) {
  // 用 data-video-id 找到对应的 video 元素（模板里每个 video 带这个标记）
  const box = document.querySelector('[data-video-id="' + it.id + '"]');
  return box ? box.querySelector("video") : null;
}

function playVideo(it) {
  const v = videoElOf(it);
  if (!v) return;
  // 播放中才给原生控件（用户可暂停 / 调音量 / 自己选全屏）
  v.controls = true;
  const p = v.play();
  if (p && typeof p.catch === "function") {
    p.catch(() => {
      // 自动播放被拦（未静音且无用户手势等）：退回静音再试一次
      v.muted = true;
      v.play().catch(() => {});
    });
  }
  markPlaying(it, true);
}

function toggleVideo(it) {
  const v = videoElOf(it);
  if (!v) return;
  if (v.paused) {
    playVideo(it);
  } else {
    v.pause();
    v.controls = false;
    markPlaying(it, false);
  }
}

function markPlaying(it, on) {
  const next = new Set(playingIds.value);
  if (on) next.add(it.id); else next.delete(it.id);
  playingIds.value = next;
}

function onVideoEnded(e) {
  const box = e.target.closest('[data-video-id]');
  if (!box) return;
  const id = Number(box.dataset.videoId);
  const it = allItems.value.find((x) => x.id === id);
  if (it) markPlaying(it, false);
  e.target.controls = false;
}

/** 相册里所有条目（章节内 + 未分组），供按 id 反查 */
const allItems = computed(() => {
  const out = [];
  if (!album.value) return out;
  for (const s of album.value.sections || []) {
    for (const it of s.items || []) out.push(it);
  }
  for (const it of album.value.items || []) out.push(it);
  return out;
});

onMounted(async () => {
  try {
    const slug = decodeURIComponent(route.params.slug || "");
    album.value = await apiGet("/api/albums/" + encodeURIComponent(slug));
  } catch (e) {
    album.value = null;
  } finally {
    loading.value = false;
  }
  window.addEventListener("keydown", onKey);
});
onUnmounted(() => window.removeEventListener("keydown", onKey));
</script>

<style scoped>
.album-empty {
  padding: 64px 24px;
  text-align: center;
  color: var(--text-muted, #9aa0a6);
}

/* --- 封面区：图在上、标题压在渐变底上 --- */
.album-hero {
  position: relative;
  border-radius: var(--ui-radius-card, 22px);
  overflow: hidden;
  margin-bottom: 26px;
  cursor: zoom-in;
}
.album-hero img {
  display: block;
  width: 100%;
  max-height: 460px;
  object-fit: cover;
}
.album-hero-mask {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  padding: 56px 24px 20px;
  background: linear-gradient(to top, rgba(0, 0, 0, .62), rgba(0, 0, 0, 0));
  color: rgba(255, 255, 255, .98);
}
.album-h1 {
  font-size: clamp(22px, 3.6vw, 32px);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.24;
  margin: 0 0 6px;
}
.album-hero-sub { margin: 0 0 6px; font-size: 15px; line-height: 1.6; opacity: .92; }
.album-hero-meta { margin: 0; font-size: 13px; opacity: .86; }

.album-head-plain { margin-bottom: 22px; }
.album-sub { color: var(--text-muted, #5f6368); font-size: 15px; margin: 0 0 6px; }
.album-meta-plain { color: var(--text-faint, #9aa0a6); font-size: 13px; margin: 0; }

/* --- 区块 --- */
.album-block { margin: 0 0 30px; }
.album-block-title {
  font-size: 19px;
  font-weight: 600;
  letter-spacing: -0.01em;
  margin: 0 0 10px;
  padding-left: 12px;
  border-left: 3px solid var(--accent, #196ddd);
  line-height: 1.4;
}
.album-prose { font-size: 15.5px; line-height: 1.78; color: var(--text, #1c1c1e); }
.album-prose p { margin: 0 0 .85em; }
.album-prose ul { margin: 0 0 .85em; padding-left: 1.3em; }
.album-prose li { margin: 0 0 .35em; }
.album-prose strong { font-weight: 600; }
.album-section-note {
  color: var(--text-muted, #5f6368);
  font-size: 14.5px;
  margin-bottom: 14px;
}
.album-tips .album-prose {
  background: var(--ui-fill, rgba(120, 120, 128, .10));
  border-radius: var(--ui-radius-control, 12px);
  padding: 14px 18px;
  font-size: 14.5px;
}

/* --- 媒体网格 --- */
.album-media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
.album-media { margin: 0; }
.album-media-box {
  position: relative;          /* 自绘播放按钮要绝对定位在卡片上 */
  border-radius: var(--ui-radius-group, 14px);
  overflow: hidden;
  background: var(--ui-fill, rgba(120, 120, 128, .10));
  aspect-ratio: 4 / 3;
  display: flex;
  align-items: center;
  justify-content: center;
}
.album-media-box.is-image { cursor: zoom-in; }
.album-media-box img,
.album-media-box video { width: 100%; height: 100%; object-fit: cover; display: block; }
/* 视频：手机拍的竖屏片（1080×1920）放进 4:3 的横格里，左右必然留边。
   纯黑 (#000) 的边看起来像「破图」，改成中性深灰 + 自绘播放按钮，
   视觉上就是一个完整的视频卡片，而不是黑框里夹一条画面。 */
.album-media-box.is-video video {
  object-fit: contain;
  background: rgba(28, 28, 30, .92);
  cursor: pointer;
}
.album-video-play {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.album-video-play-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: rgba(0, 0, 0, .48);
  color: #fff;
  font-size: 20px;
  line-height: 1;
  padding-left: 4px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, .3);
  backdrop-filter: blur(2px);
}
.album-video-play:hover .album-video-play-icon { background: rgba(0, 0, 0, .62); }
.album-caption {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-muted, #5f6368);
}

/* --- 灯箱 --- */
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 90;
  background: rgba(0, 0, 0, .92);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px;
}
.lb-body { margin: 0; max-width: min(1200px, 92vw); max-height: 90vh; }
.lb-body img {
  display: block;
  max-width: 100%;
  max-height: 82vh;
  object-fit: contain;
  border-radius: 8px;
  margin: 0 auto;
}
.lb-caption {
  margin-top: 12px;
  text-align: center;
  color: rgba(255, 255, 255, .88);
  font-size: 14px;
  line-height: 1.6;
}
.lb-count { margin-left: 10px; opacity: .6; font-size: 12px; }
.lb-close {
  position: absolute;
  top: 14px; right: 18px;
  width: 40px; height: 40px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, .14);
  color: #fff;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}
.lb-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 48px; height: 48px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, .14);
  color: #fff;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
}
.lb-prev { left: 16px; }
.lb-next { right: 16px; }
.lb-close:hover, .lb-nav:hover { background: rgba(255, 255, 255, .26); }

@media (max-width: 640px) {
  .album-media-grid { grid-template-columns: 1fr 1fr; gap: 10px; }
  .album-hero-mask { padding: 40px 16px 16px; }
  .lb-nav { width: 40px; height: 40px; font-size: 22px; }
}
</style>
