<template>
  <div class="container rss-wrap">
    <h1 class="rss-title">📡 {{ t('rss_title') }}</h1>
    <p class="rss-intro">{{ t('rss_intro') }}</p>

    <!-- 两个源：RSS 2.0 与 Atom（后端 routes.py 各有一条路由，内容同一份查询）。
         都列出来是因为「阅读器挑食」是真实存在的：有的只认其中一种，
         只给一个地址会让一部分人订阅失败后默默放弃，不会回来告诉你。 -->
    <div class="rss-sources">
      <div v-for="f in feeds" :key="f.path" class="rss-card">
        <div class="rss-card-head">
          <strong class="rss-fmt">{{ f.label }}</strong>
          <code class="rss-url">{{ f.url }}</code>
        </div>
        <div class="rss-card-actions">
          <button type="button" class="btn small" @click="copy(f.url)">
            {{ copied === f.url ? t('rss_copied') : t('rss_copy') }}
          </button>
          <a class="btn ghost small" :href="f.path" target="_blank" rel="noopener">{{ t('rss_open') }}</a>
        </div>
      </div>
    </div>
    <p class="rss-pick">{{ t('rss_pick') }}</p>

    <h2 class="rss-h2">{{ t('rss_how') }}</h2>
    <ol class="rss-steps">
      <li>{{ t('rss_s1') }}</li>
      <li>{{ t('rss_s2') }}</li>
      <li>{{ t('rss_s3') }}</li>
    </ol>

    <!-- 「源里有最近这几篇」比任何说明都更能让人确认这个源是活的 -->
    <h2 class="rss-h2">{{ t('rss_latest') }}</h2>
    <ul v-if="latest.length" class="rss-latest">
      <li v-for="p in latest" :key="p.slug">
        <router-link :to="'/post/' + p.slug">{{ p.title }}</router-link>
        <span class="rss-date">{{ p.created_at }}</span>
      </li>
    </ul>
    <p v-else class="rss-empty">{{ t('rss_empty') }}</p>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";
import { t } from "../store.js";
import copyText from "../lib/clipboard.js";
import { toastOk, toastErr } from "../lib/toast.js";

// 站点的源地址是**同源**的，所以直接拼 origin —— 不读站点设置里的 SITE_URL：
// 那个值是后台手填的，可能与当前访问域名不一致（换域名/多域名时尤其常见），
// 用访问者的 origin 才能保证「复制到的地址点开一定就是本站」。
const origin = typeof window !== "undefined" ? window.location.origin : "";

const feeds = [
  { path: "/feed.xml", label: "RSS 2.0", url: origin + "/feed.xml" },
  { path: "/feed.atom", label: "Atom", url: origin + "/feed.atom" },
];

const copied = ref("");
const latest = ref([]);

async function copy(url) {
  const ok = await copyText(url);
  if (!ok) {
    toastErr(t('rss_copy_fail'));
    return;
  }
  copied.value = url;
  toastOk(t('rss_copied'));
  setTimeout(() => {
    if (copied.value === url) copied.value = "";
  }, 2500);
}

onMounted(async () => {
  try {
    const d = await apiGet("/api/posts");
    // per_page 由服务端固定（不接受客户端传参），所以这里前端截 5 条
    latest.value = ((d && d.items) || []).slice(0, 5);
  } catch (e) {
    latest.value = [];   // 列表只是佐证，取不到就整块不显示，不报错
  }
});
</script>

<style scoped>
.rss-wrap {
  max-width: 720px;
  padding: 8px 0 60px;
}
.rss-title {
  font-size: clamp(22px, 3vw, 28px);
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 4px 0 10px;
}
.rss-intro {
  color: var(--text-muted, #6a717f);
  font-size: 14px;
  line-height: 1.8;
  margin: 0 0 20px;
}
.rss-sources {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}
.rss-card {
  padding: 14px 16px;
  border-radius: var(--ui-radius-card, 22px);
  border: 1px solid var(--ui-hairline, rgba(60, 60, 67, 0.12));
  background: var(--surface-2, #f4f6f8);
}
.rss-card-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rss-fmt { font-size: 14px; }
.rss-url {
  /* 地址要能整行读完、还能被选中 —— 不截断、允许换行 */
  display: block;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted, #6a717f);
  word-break: break-all;
  user-select: all;
}
.rss-card-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.rss-pick {
  font-size: 13px;
  color: var(--text-faint, #7d838f);
  margin: 12px 0 0;
}
.rss-h2 {
  font-size: 17px;
  font-weight: 600;
  margin: 28px 0 10px;
}
.rss-steps {
  margin: 0;
  padding-left: 22px;
  font-size: 14px;
  line-height: 1.9;
  color: var(--text, #2c2c2c);
}
.rss-latest {
  list-style: none;
  margin: 0;
  padding: 0;
}
.rss-latest li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--ui-hairline, rgba(60, 60, 67, 0.12));
  font-size: 14px;
}
.rss-latest a {
  color: var(--text, #2c2c2c);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rss-latest a:hover { color: var(--accent, #196ddd); }
.rss-date {
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--text-faint, #7d838f);
}
.rss-empty {
  font-size: 13px;
  color: var(--text-faint, #7d838f);
}
</style>
