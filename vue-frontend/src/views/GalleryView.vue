<template>
  <div class="container">
    <h1 class="page-title">{{ t("gallery") }}</h1>
    <p class="gallery-sub">{{ t("gallery_sub") }}</p>

    <div class="gallery-bar">
      <div class="tabs">
        <button v-for="tab in kinds" :key="tab.value"
                :class="['tab', { active: kind === tab.value }]"
                @click="setKind(tab.value)">{{ tab.label }}</button>
      </div>
      <div class="folders" v-if="folders.length">
        <button :class="['chip', { active: !folder }]" @click="setFolder('')">{{ t("all") }}</button>
        <button v-for="f in folders" :key="f.folder"
                :class="['chip', { active: folder === f.folder }]"
                @click="setFolder(f.folder)">{{ f.folder }} · {{ f.count }}</button>
      </div>
    </div>

    <div v-if="loading" class="gallery-empty">{{ t("loading") }}</div>

    <div v-else-if="!items.length" class="gallery-empty">{{ t("gallery_empty") }}</div>

    <div v-else class="grid">
      <figure v-for="it in items" :key="it.id" class="card">
        <!-- 外链播放器（B站/YouTube）：域名在后台登记时已按白名单校验 -->
        <div v-if="it.source === 'embed'" class="thumb embed">
          <iframe :src="it.url" loading="lazy" allowfullscreen
                  referrerpolicy="no-referrer"
                  sandbox="allow-scripts allow-same-origin allow-presentation"></iframe>
        </div>
        <div v-else-if="it.kind === 'video'" class="thumb">
          <video :src="it.url" :poster="it.poster || undefined"
                 controls preload="metadata" playsinline></video>
        </div>
        <a v-else class="thumb" :href="it.url" target="_blank" rel="noopener noreferrer">
          <img :src="it.url" :alt="it.title" loading="lazy">
        </a>

        <figcaption>
          <span class="title">{{ it.title || t("untitled") }}</span>
          <span class="meta">
            <template v-if="it.width && it.height">{{ it.width }}×{{ it.height }} · </template>
            {{ it.created_at }}
            <template v-if="it.folder"> · {{ it.folder }}</template>
          </span>
        </figcaption>
      </figure>
    </div>

    <div class="more" v-if="hasMore">
      <button class="btn" :disabled="loadingMore" @click="loadMore">
        {{ loadingMore ? t("loading") : t("load_more") }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";
import { t } from "../store.js";

const kinds = computed(() => [
  { value: "", label: t("all") },
  { value: "image", label: t("images") },
  { value: "video", label: t("videos") },
]);

const items = ref([]);
const folders = ref([]);
const kind = ref("");
const folder = ref("");
const page = ref(1);
const size = 24;
const total = ref(0);
const loading = ref(true);
const loadingMore = ref(false);
const hasMore = computed(() => items.value.length < total.value);

async function fetchList(reset) {
  if (reset) { page.value = 1; loading.value = true; }
  else loadingMore.value = true;
  try {
    const qs = new URLSearchParams({ page: String(page.value), size: String(size) });
    if (kind.value) qs.set("kind", kind.value);
    if (folder.value) qs.set("folder", folder.value);
    const data = await apiGet("/api/media/list?" + qs.toString());
    total.value = Number(data.total) || 0;
    items.value = reset ? (data.items || []) : items.value.concat(data.items || []);
  } catch (e) {
    if (reset) items.value = [];
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
}

async function fetchFolders() {
  try {
    folders.value = await apiGet("/api/media/folders");
  } catch (e) {
    folders.value = [];
  }
}

function setKind(v) { kind.value = v; fetchList(true); }
function setFolder(v) { folder.value = v; fetchList(true); }
function loadMore() { page.value += 1; fetchList(false); }

onMounted(() => {
  fetchFolders();
  fetchList(true);
});
</script>

<style scoped>
.gallery-sub { margin: -8px 0 20px; color: var(--text-muted, #9aa0a6); font-size: 14px; }
.gallery-bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 20px; }
.tabs { display: inline-flex; padding: 3px; border-radius: 12px; background: var(--surface-2, #f2f3f5); }
.tab { border: 0; background: transparent; padding: 6px 14px; border-radius: 10px;
  font-size: 14px; color: var(--text-muted, #5f6368); cursor: pointer; }
.tab.active { background: var(--surface, #fff); color: var(--text, #1c1c1e);
  box-shadow: 0 1px 3px rgba(0, 0, 0, .12); font-weight: 600; }
.folders { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { border: 1px solid var(--border, #e5e5ea); background: transparent; color: var(--text-muted, #5f6368);
  padding: 4px 12px; border-radius: 99px; font-size: 13px; cursor: pointer; }
.chip.active { border-color: var(--accent, #0a84ff); color: var(--accent, #0a84ff); background: transparent; }

.grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.card { margin: 0; border-radius: 16px; overflow: hidden; background: var(--surface, #fff);
  border: 1px solid var(--border, #ececec); transition: transform .18s ease, box-shadow .18s ease; }
.card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0, 0, 0, .08); }
.thumb { display: block; aspect-ratio: 4 / 3; background: #000; overflow: hidden; }
.thumb img, .thumb video { width: 100%; height: 100%; object-fit: cover; display: block; }
.thumb.embed iframe { width: 100%; height: 100%; border: 0; display: block; }
figcaption { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 4px; }
.title { font-size: 14px; color: var(--text, #1c1c1e); font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta { font-size: 12px; color: var(--text-muted, #9aa0a6); }

.gallery-empty { padding: 60px 0; text-align: center; color: var(--text-muted, #9aa0a6); }
.more { display: flex; justify-content: center; padding: 28px 0 8px; }
.btn { border: 1px solid var(--border, #e5e5ea); background: var(--surface, #fff);
  color: var(--text, #1c1c1e); padding: 8px 22px; border-radius: 99px; cursor: pointer; font-size: 14px; }
.btn:disabled { opacity: .5; cursor: default; }
</style>
