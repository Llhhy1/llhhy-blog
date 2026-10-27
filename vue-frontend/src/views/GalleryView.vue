<template>
  <div class="container">
    <h1 class="page-title">{{ t("gallery") }}</h1>
    <p class="gallery-sub">{{ t("gallery_sub") }}</p>

    <div v-if="loading" class="gallery-empty">{{ t("loading") }}</div>

    <div v-else-if="!albums.length" class="gallery-empty">{{ t("gallery_empty") }}</div>

    <template v-else>
      <div class="album-grid">
        <router-link v-for="a in albums" :key="a.id" class="album-card"
                     :to="'/album/' + encodeURIComponent(a.slug)">
          <div class="album-cover">
            <img v-if="a.cover && a.cover.url" :src="a.cover.url" :alt="a.title" loading="lazy">
            <span v-else class="album-nocover">{{ t("untitled") }}</span>
          </div>

          <div class="album-body">
            <h2 class="album-title">{{ a.title || t("untitled") }}</h2>
            <p v-if="a.summary" class="album-summary">{{ a.summary }}</p>
            <p class="album-meta">
              <template v-if="a.event_date">{{ a.event_date }}</template>
              <template v-if="a.location"> · {{ a.location }}</template>
              <template v-if="a.trip_days"> · {{ a.trip_days }}</template>
              <span> · {{ a.count }} {{ t("items") }}</span>
            </p>

            <div v-if="a.preview && a.preview.length > 1" class="album-preview">
              <span v-for="p in a.preview.slice(0, 4)" :key="p.id" class="album-preview-cell">
                <img v-if="p.kind === 'image'" :src="p.poster || p.url" alt="" loading="lazy">
                <span v-else class="album-preview-video">{{ t("videos") }}</span>
              </span>
            </div>
          </div>
        </router-link>
      </div>

      <div v-if="hasMore" class="more">
        <button class="btn" :disabled="loadingMore" @click="load(page + 1)">
          {{ loadingMore ? t("loading") : t("load_more") }}
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";
import { t } from "../store.js";

const albums = ref([]);
const page = ref(1);
const total = ref(0);
const size = 12;
const loading = ref(true);
const loadingMore = ref(false);
const hasMore = computed(() => albums.value.length < total.value);

async function load(p) {
  if (p === 1) loading.value = true; else loadingMore.value = true;
  try {
    const data = await apiGet(`/api/albums?page=${p}&size=${size}`);
    total.value = Number(data.total) || 0;
    page.value = Number(data.page) || p;
    albums.value = p === 1 ? (data.items || []) : albums.value.concat(data.items || []);
  } catch (e) {
    if (p === 1) albums.value = [];
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
}

onMounted(() => load(1));
</script>

<style scoped>
.gallery-sub { margin: -8px 0 22px; color: var(--text-muted, #9aa0a6); font-size: 15px; }
.gallery-empty {
  padding: 56px 24px;
  text-align: center;
  color: var(--text-muted, #9aa0a6);
  border-radius: var(--ui-radius-card, 22px);
  border: 1px dashed var(--ui-hairline, rgba(60, 60, 67, .12));
}
.more { display: flex; justify-content: center; padding: 28px 0 8px; }
.btn { border: 1px solid var(--ui-hairline, rgba(60, 60, 67, .12)); background: var(--surface, #fff);
  color: var(--text, #1c1c1e); padding: 8px 22px; border-radius: 999px; cursor: pointer; font-size: 14px; }
.btn:disabled { opacity: .5; cursor: default; }

.album-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}
.album-card {
  display: block;
  border-radius: var(--ui-radius-card, 22px);
  border: 1px solid var(--ui-hairline, rgba(60, 60, 67, .12));
  background: var(--surface, #fff);
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  transition: transform var(--ui-dur, 280ms) var(--ui-ease, cubic-bezier(.32, .72, 0, 1)),
              box-shadow var(--ui-dur, 280ms) var(--ui-ease, cubic-bezier(.32, .72, 0, 1));
}
.album-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--ui-shadow-lift, 0 2px 8px rgba(0, 0, 0, .07));
}

/* 封面固定比例：不同尺寸首图不会把卡片撑成高低不齐 */
.album-cover {
  aspect-ratio: 16 / 10;
  background: var(--ui-fill, rgba(120, 120, 128, .10));
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.album-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 420ms var(--ui-ease, cubic-bezier(.32, .72, 0, 1));
}
.album-card:hover .album-cover img { transform: scale(1.03); }
.album-nocover { font-size: 13px; color: var(--text-faint, #9aa0a6); }

.album-body { padding: 16px 18px 18px; }
.album-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.35;
  margin: 0 0 6px;
}
.album-summary {
  color: var(--text-muted, #5f6368);
  font-size: 14px;
  line-height: 1.6;
  margin: 0 0 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.album-meta { color: var(--text-faint, #9aa0a6); font-size: 12.5px; margin: 0; }

/* 预览带：让人一眼看出「里面有东西」 */
.album-preview {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px;
  margin-top: 12px;
}
.album-preview-cell {
  aspect-ratio: 1;
  border-radius: 6px;
  overflow: hidden;
  background: var(--ui-fill, rgba(120, 120, 128, .10));
  display: flex;
  align-items: center;
  justify-content: center;
}
.album-preview-cell img { width: 100%; height: 100%; object-fit: cover; }
.album-preview-video { font-size: 11px; color: var(--text-faint, #9aa0a6); }

@media (max-width: 640px) {
  .album-grid { grid-template-columns: 1fr; }
}
</style>
