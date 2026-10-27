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
            <ul v-if="b.type === 'ul'"><li v-for="(li, j) in b.items" :key="j">{{ li }}</li></ul>
            <p v-else>{{ b.text }}</p>
          </template>
        </div>
      </section>

      <!-- 章节：每组一段文字 + 一组媒体 -->
      <section v-for="s in album.sections" :key="s.id" class="album-block album-section">
        <h2 class="album-block-title">{{ s.title || t("untitled") }}</h2>
        <div v-if="s.summary" class="album-prose album-section-note">
          <template v-for="(b, i) in blocksOf(s.summary)" :key="'s' + i">
            <ul v-if="b.type === 'ul'"><li v-for="(li, j) in b.items" :key="j">{{ li }}</li></ul>
            <p v-else>{{ b.text }}</p>
          </template>
        </div>
        <div class="album-media-grid">
          <figure v-for="it in s.items" :key="it.id" class="album-media">
            <div v-if="it.media.kind === 'video'" class="album-media-box">
              <video :src="it.media.url" :poster="it.media.poster || undefined"
                     controls preload="metadata" playsinline></video>
            </div>
            <div v-else class="album-media-box is-image" @click="openLightboxByItem(it)">
              <img :src="it.media.url" :alt="it.caption || ''" loading="lazy">
            </div>
            <figcaption v-if="it.caption" class="album-caption">{{ it.caption }}</figcaption>
          </figure>
        </div>
      </section>

      <!-- 未分组条目（没有章节时这里就是全部照片） -->
      <section v-if="album.items && album.items.length" class="album-block">
        <h2 v-if="album.sections && album.sections.length" class="album-block-title">{{ t("album_loose") }}</h2>
        <div class="album-media-grid">
          <figure v-for="it in album.items" :key="it.id" class="album-media">
            <div v-if="it.media.kind === 'video'" class="album-media-box">
              <video :src="it.media.url" :poster="it.media.poster || undefined"
                     controls preload="metadata" playsinline></video>
            </div>
            <div v-else class="album-media-box is-image" @click="openLightboxByItem(it)">
              <img :src="it.media.url" :alt="it.caption || ''" loading="lazy">
            </div>
            <figcaption v-if="it.caption" class="album-caption">{{ it.caption }}</figcaption>
          </figure>
        </div>
      </section>

      <!-- 小提示 -->
      <section v-if="tipBlocks.length" class="album-block album-tips">
        <h2 class="album-block-title">{{ t("album_tips") }}</h2>
        <div class="album-prose">
          <template v-for="(b, i) in tipBlocks" :key="'t' + i">
            <ul v-if="b.type === 'ul'"><li v-for="(li, j) in b.items" :key="j">{{ li }}</li></ul>
            <p v-else>{{ b.text }}</p>
          </template>
        </div>
      </section>
    </template>

    <!-- 灯箱 -->
    <div v-if="lightbox !== null" class="lightbox" @click.self="closeLightbox">
      <button class="lb-close" :aria-label="t('close')" @click="closeLightbox">×</button>
      <button v-if="images.length > 1" class="lb-nav lb-prev" :aria-label="t('prev')" @click="step(-1)">‹</button>
      <figure class="lb-body">
        <img :src="images[lightbox]?.media.url" :alt="images[lightbox]?.caption || ''">
        <figcaption v-if="images[lightbox]?.caption" class="lb-caption">
          {{ images[lightbox].caption }}
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
function blocksOf(text) {
  const out = [];
  const paras = String(text || "").split(/\n\s*\n/);
  for (const p of paras) {
    const lines = p.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!lines.length) continue;
    if (lines.every((l) => /^[-*]\s+/.test(l))) {
      out.push({ type: "ul", items: lines.map((l) => l.replace(/^[-*]\s+/, "")) });
    } else {
      out.push({ type: "p", text: lines.join(" ") });
    }
  }
  return out;
}

const introBlocks = computed(() => blocksOf(album.value && album.value.intro));
const tipBlocks = computed(() => blocksOf(album.value && album.value.tips));

function openLightbox(idx) { if (images.value.length) lightbox.value = idx; }
function openLightboxByItem(it) {
  const idx = images.value.findIndex((x) => x.id === it.id);
  if (idx >= 0) lightbox.value = idx;
}
function closeLightbox() { lightbox.value = null; }
function step(d) {
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
.album-media-box video { object-fit: contain; background: #000; }
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
