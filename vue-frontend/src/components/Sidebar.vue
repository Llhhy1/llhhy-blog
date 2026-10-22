<template>
  <aside class="sidebar">
    <div class="widget">
      <h3>{{ t('site_search') }}</h3>
      <form class="search-box" @submit.prevent="doSearch">
        <input type="text" v-model="q" :placeholder="t('search_placeholder')" />
        <button type="submit">{{ t('search_go') }}</button>
      </form>
    </div>

    <div class="widget">
      <h3>{{ t('email_subscribe') }}</h3>
      <p class="sub-tip">{{ t('sub_tip') }}</p>
      <form class="sub-box" @submit.prevent="doSubscribe">
        <input type="email" v-model="subEmail" :placeholder="t('email_placeholder')" autocomplete="email" :disabled="subDone" />
        <button type="submit" :disabled="subBusy || subDone">{{ subBtnText }}</button>
      </form>
      <p v-if="subMsg" class="sub-msg" :class="subOk ? 'ok' : 'err'">{{ subMsg }}</p>
    </div>

    <WeatherWidget />

    <div class="widget">
      <h3>{{ t('categories') }}</h3>
      <ul class="list-clean">
        <li v-for="c in cats" :key="c.slug">
          <router-link :to="`/category/${c.slug}`">{{ c.name }}</router-link>
        </li>
        <li v-if="!cats.length">{{ t('no_categories') }}</li>
      </ul>
    </div>

    <div class="widget">
      <h3>{{ t('tags') }}</h3>
      <div class="tag-cloud">
        <router-link v-for="t in tags" :key="t.slug" class="tag" :to="`/tag/${t.slug}`">{{ t.name }}</router-link>
        <span v-if="!tags.length">{{ t('no_tags') }}</span>
      </div>
    </div>

    <div class="widget">
      <h3>{{ t('recent_posts') }}</h3>
      <ul class="list-clean">
        <li v-for="p in recent" :key="p.slug">
          <router-link :to="`/post/${p.slug}`">{{ p.title }}</router-link>
        </li>
        <li v-if="!recent.length">{{ t('no_posts') }}</li>
      </ul>
    </div>

    <div class="widget">
      <h3>{{ t('hot_posts') }}</h3>
      <ul class="list-clean">
        <li v-for="p in hotPosts" :key="p.slug">
          <router-link :to="`/post/${p.slug}`">{{ p.title }}</router-link>
          <span style="font-size: 11px; color: #aaa; margin-left: 6px;">{{ p.reads }} {{ t('reads') }}</span>
        </li>
        <li v-if="!hotPosts.length">{{ t('no_data') }}</li>
      </ul>
    </div>

    <div class="widget">
      <h3>{{ t('site_stats') }}</h3>
      <p style="font-size: 13px; color: #666;">{{ t('stats_line', { p: totalPosts, c: totalComments }) }}</p>
    </div>

    <div v-if="links.length" class="widget">
      <h3>{{ t('friend_links') }}</h3>
      <ul class="list-clean">
        <li v-for="l in links.slice(0, 6)" :key="l.url">
          <a :href="l.url" target="_blank" rel="noopener">{{ l.name }}</a>
        </li>
      </ul>
    </div>
  </aside>
</template>

<script setup>
import { onMounted, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { apiGet, apiPost } from "../lib/api.js";
import { t } from "../store.js";
import WeatherWidget from "./WeatherWidget.vue";

const router = useRouter();
const q = ref("");
const cats = ref([]);
const tags = ref([]);
const links = ref([]);
const recent = ref([]);
const totalPosts = ref(0);
const totalComments = ref(0);
const hotPosts = ref([]);

// 邮件订阅
const subEmail = ref("");
const subBusy = ref(false);
const subDone = ref(false);
const subMsg = ref("");
const subOk = ref(false);
const subBtnText = computed(() =>
  (subBusy.value ? t("sub_busy") : subDone.value ? t("sub_done") : t("subscribe")));

async function doSubscribe() {
  const email = subEmail.value.trim();
  if (!email) {
    subMsg.value = t("email_required");
    subOk.value = false;
    return;
  }
  subBusy.value = true;
  subMsg.value = "";
  try {
    const d = await apiPost("/api/subscribe", { email });
    subOk.value = true;
    subDone.value = true;
    subMsg.value = d.message || t("subscribe_ok");
  } catch (e) {
    subOk.value = false;
    subMsg.value = e.message || t("subscribe_fail");
  } finally {
    subBusy.value = false;
  }
}

function doSearch() {
  if (q.value.trim()) router.push({ path: "/search", query: { q: q.value.trim() } });
}

onMounted(async () => {
  try {
    const [c, t, l, r] = await Promise.all([
      apiGet("/api/categories").catch(() => []),
      apiGet("/api/tags").catch(() => []),
      apiGet("/api/links").catch(() => []),
      apiGet("/api/posts", { page_size: 5 }).catch(() => ({ items: [] })),
    ]);
    cats.value = c;
    tags.value = t;
    links.value = l;
    recent.value = r.items || [];
    totalPosts.value = r.total || recent.value.length;
  } catch (e) {}
  try {
    const st = await apiGet("/api/site");
    totalComments.value = st.total_comments || 0;
  } catch (e) {}
  try {
    const sum = await apiGet("/api/stats/summary");
    hotPosts.value = (sum.hot_posts || []).slice(0, 5);
  } catch (e) {}
});
</script>
