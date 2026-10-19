<template>
  <!-- v4.6.1 根节点挂 .home-page：首屏要「破框」铺满整屏（整站外框 .site-frame 的
       限宽/边框/圆角会把壁纸套住），破框后下方区块靠 .home-page 重新限宽居中。 -->
  <div class="home-page">
    <!-- v4.5.0 首页首屏大图：启用壁纸时铺满整屏，站点标题与联系方式图标叠加其上，
         向下滚动即进入文章列表；未配置壁纸时退化为 v3.4.1 的渐变横幅（原观感不变）。
         ⚠️ 亮/暗两套壁纸通过 CSS 变量交给 `[data-theme]` 选择器切换 ——
         主题切换发生在 App.vue，把这件事留在 JS 里就得双向同步，漏一处就会
         出现「切了主题壁纸还是亮色」。 -->
    <section ref="coverRef" class="home-cover" :class="{ 'has-wall': !!wallpaperUrl }" :style="coverStyle">
      <div class="home-cover-inner">
        <h2 class="home-cover-title">{{ state.site.site_name || state.site.site_title || '我的博客' }}</h2>
        <p class="home-cover-sub">{{ state.site.site_description || '记录思考，分享知识' }}</p>
        <div v-if="socials.length" class="home-cover-social" aria-label="联系方式">
          <component
            :is="s.href ? 'a' : 'button'"
            v-for="s in socials.slice(0, 8)"
            :key="s.id"
            class="hcs-item"
            :href="s.href || null"
            :target="s.href ? '_blank' : null"
            :rel="s.href ? 'noopener' : null"
            :type="s.href ? null : 'button'"
            :title="s.meta.label + (s.handle ? '：' + s.handle : '')"
            @click="s.href ? null : onCopySocial(s)"
          >{{ s.meta.icon }}</component>
        </div>
      </div>
      <!-- v4.6.0：移到 .home-cover-inner 外 —— 贴视口底部绝对定位，不跟标题走 -->
      <div v-if="wallpaperUrl" class="home-cover-hint" aria-hidden="true">
        <span class="hch-arrow">↓</span><span>向下滚动</span>
      </div>
    </section>

    <!-- v4.7.0：原「站点概览 bento 六卡」与「找到我」社交墙已移入「运营驾驶舱」（/stats）。
         移走理由：满屏壁纸首屏之后立刻堆六张数据卡 + 一排社交入口，视觉噪声大于信息量；
         且首屏壁纸里已经有联系方式图标，与「找到我」一栏重复。
         数据本身没丢，只是不再占用首页黄金位。⚠️ `socials` 仍被首屏
         `.home-cover-social` 使用，**不可随之删除**。 -->

    <div class="layout">
      <div class="content">
        <h1 class="page-title">✨ 最新文章</h1>
        <!-- v3.17.0 骨架屏：首屏加载中显示占位，避免「还没有文章」闪现 -->
        <template v-if="loading">
          <div v-for="n in 3" :key="n" class="skel-card">
            <div class="skel-line skel-title"></div>
            <div class="skel-line"></div>
            <div class="skel-line skel-short"></div>
          </div>
        </template>
        <template v-else>
          <p v-if="!items.length" class="empty">还没有文章。</p>
          <PostCard v-for="p in items" :key="p.slug" :post="p" v-reveal />
        </template>

      <nav v-if="!loading && totalPages > 1" class="pagination">
          <router-link v-if="page > 1" :to="{ query: { page: page - 1 } }">← 上一页</router-link>
          <span v-else class="disabled">← 上一页</span>
          <template v-for="(p, i) in pages" :key="i">
            <span v-if="p === '…'" class="ellipsis">…</span>
            <span v-else-if="p === page" class="current">{{ p }}</span>
            <router-link v-else :to="{ query: { page: p } }">{{ p }}</router-link>
          </template>
          <router-link v-if="page < totalPages" :to="{ query: { page: page + 1 } }">下一页 →</router-link>
          <span v-else class="disabled">下一页 →</span>
        </nav>
      </div>
      <Sidebar />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../lib/api.js";
import { state } from "../store.js";
import PostCard from "../components/PostCard.vue";
import Sidebar from "../components/Sidebar.vue";
import { copyText } from "../lib/clipboard.js";
import { toastOk, toastErr } from "../lib/toast.js";
import { toSocialItem } from "../lib/social.js";

const route = useRoute();
const items = ref([]);
const loading = ref(true);   // v3.17.0 骨架屏
const page = ref(1);
// v4.7.0：`siteStats` / `fmtNum` 随 bento 一起移入 /stats，首页不再需要。
// （社交账号仍要用 —— 首屏 `.home-cover-social` 依赖它，下面三行保留。）

// v3.17.9：社交账号（独立页 /social；首页仅首屏图标展示）
const rawSocials = ref([]);
const socials = computed(() => (rawSocials.value || []).map(toSocialItem));
async function loadSocials() {
  try { rawSocials.value = (await apiGet("/api/social-accounts")) || []; } catch (e) { rawSocials.value = []; }
}
async function onCopySocial(s) {
  const ok = await copyText(s.url);
  if (ok) toastOk("已复制：" + s.url);
  else toastErr("已弹窗，请手动复制");
}
onMounted(loadSocials);

// ---------- v4.5.0 首页壁纸 ----------
// 后端 `/api/site` 下发 `wallpaper`（initSite 用 Object.assign，已自动进 state.site）。
// 这里只负责把「亮/暗两张 + 遮罩」转成 CSS 变量，具体按哪个主题取图交给 CSS：
// `[data-theme="dark"]` 换一张 url 即可，比在 JS 里监听主题切换再重算可靠。
const wallpaper = computed(() => state.site.wallpaper || null);
const wallpaperUrl = computed(() => {
  const wp = wallpaper.value;
  if (!wp || !wp.enabled) return "";
  return wp.light || wp.dark || "";
});
const coverStyle = computed(() => {
  const wp = wallpaper.value;
  if (!wp || !wp.enabled || !wallpaperUrl.value) return {};
  const o = veilOpacity.value;
  const veil = `linear-gradient(rgba(0,0,0,${o}), rgba(0,0,0,${o}))`;
  // 用 JSON.stringify 生成 url() 里的引号转义：壁纸 URL 来自 Setting，
  // 即便后端已限定本站 uploads，也不该在模板绑定里裸拼进 CSS 声明。
  const light = wp.light ? `url(${JSON.stringify(wp.light)})` : "none";
  const dark = wp.dark ? `url(${JSON.stringify(wp.dark)})` : light;
  return {
    "--wall-veil": veil,
    "--wall-light": light,
    "--wall-dark": dark,
  };
});

// v4.6.0：顶栏浮到壁纸上后，它不在 .home-cover 的 background-image 里，
// 拿不到那层遮罩 → 白字可能压在亮色壁纸上读不清。补一条顶部渐变，取遮罩的七成。
// 🔑 **这条变量必须挂 :root，不能放进 coverStyle**：.site-header 与 .home-cover
// 是兄弟节点，CSS 自定义属性只向下继承，写在 .home-cover 的 inline style 上
// 永远传不到 header —— 那样 header 只会拿到 fallback 常量，遮罩滑块就联动不了。
const veilOpacity = computed(() => {
  const wp = wallpaper.value;
  if (!wp || !wp.enabled || !wallpaperUrl.value) return 0;
  return Math.min(0.8, Math.max(0, Number(wp.overlay) || 0));
});
const veilTop = computed(() => {
  if (!veilOpacity.value) return "";
  // ⚠️ 有下限 0.28：顶栏白字压在**亮色**壁纸上时，只靠遮罩滑块会糊掉
  // （实测遮罩 0.15 时导航项几乎看不清）。顶栏可读性优先，不跟着滑块一路降到 0。
  const top = Math.max(0.28, veilOpacity.value * 0.7).toFixed(3);
  return `linear-gradient(rgba(0,0,0,${top}), rgba(0,0,0,0))`;
});
function _applyVeilTop(v) {
  const el = document.documentElement;
  if (!el) return;
  if (v) el.style.setProperty("--wall-veil-top", v);
  else el.style.removeProperty("--wall-veil-top");
}
watch(veilTop, _applyVeilTop, { immediate: true });

// ---------- v4.6.0 顶栏：浮在壁上 → 滚过首屏变实心固定条 ----------
// 顶栏的位置样式由 CSS `:root:has(.home-cover.has-wall)` 决定，JS 只负责一个
// 「滚过去了没」的开关。用 IntersectionObserver 而不是 scroll 事件 ——
// 后者每帧回调，而这个 100svh 元素整页生命周期里进出视口最多两次。
const coverRef = ref(null);
let _coverIO = null;
function _setHeaderSolid(on) {
  const hd = document.querySelector(".site-header");
  if (hd) hd.classList.toggle("is-solid", !!on);
}
onMounted(() => {
  _setHeaderSolid(false);
  if (!("IntersectionObserver" in window) || !coverRef.value) return;
  _coverIO = new IntersectionObserver((entries) => {
    _setHeaderSolid(!entries[0].isIntersecting);
  }, { threshold: 0 });
  _coverIO.observe(coverRef.value);
});
onBeforeUnmount(() => {
  if (_coverIO) { _coverIO.disconnect(); _coverIO = null; }
  _setHeaderSolid(false);
  _applyVeilTop("");   // 别把首页专用的渐变留在 :root 上污染其他页面
});
function fmtNum(n) {
  n = Number(n) || 0;
  if (n >= 10000) return (n / 10000).toFixed(1) + "w";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}
const totalPages = ref(1);
const PAGE_SIZE = 8;

const pages = computed(() => {
  const list = [];
  const total = totalPages.value;
  const cur = page.value;
  if (total <= 7) { for (let i = 1; i <= total; i++) list.push(i); }
  else {
    list.push(1);
    if (cur > 4) list.push("…");
    for (let i = Math.max(2, cur - 1); i <= Math.min(total - 1, cur + 1); i++) list.push(i);
    if (cur < total - 3) list.push("…");
    list.push(total);
  }
  return list;
});

async function load() {
  page.value = parseInt(route.query.page || "1", 10) || 1;
  loading.value = true;
  try {
    const data = await apiGet("/api/posts", { page: page.value, page_size: PAGE_SIZE, lang: state.contentLang });
    items.value = data.items || [];
    totalPages.value = data.total_pages || 1;
  } catch (e) { items.value = []; totalPages.value = 1; }
  finally { loading.value = false; }
}

onMounted(load);
watch(() => route.query.page, load);
watch(() => state.contentLang, load);   // v3.21.0 内容多语言：随内容语言刷新列表
</script>
