<template>
  <div class="reading-progress" id="reading-progress"></div>
  <!-- v2.6.0 mobile 抽屉式导航 -->
  <div class="drawer-mask" :class="{show: drawerOpen}" @click="drawerOpen = false"></div>
  <aside class="drawer" :class="{open: drawerOpen}" aria-label="导航菜单">
    <div class="drawer-head">
      <router-link class="drawer-logo" to="/" @click="drawerOpen = false">{{ state.site.site_name || state.site.site_title || '博客' }}</router-link>
      <button class="drawer-close" type="button" aria-label="关闭菜单" @click="drawerOpen = false">×</button>
    </div>
    <nav class="drawer-nav">
      <router-link to="/" @click="drawerOpen = false">{{ t('home') }}</router-link>
      <router-link to="/archive" @click="drawerOpen = false">{{ t('archive') }}</router-link>
      <router-link to="/stats" @click="drawerOpen = false">{{ t('stats') }}</router-link>
      <router-link to="/about" @click="drawerOpen = false">{{ t('about') }}</router-link>
      <router-link to="/links" @click="drawerOpen = false">{{ t('links') }}</router-link>
      <router-link to="/square" @click="drawerOpen = false">{{ t('square') }}</router-link>
      <router-link to="/series" @click="drawerOpen = false">{{ t('series') }}</router-link>
      <router-link to="/tags/hot" @click="drawerOpen = false">{{ t('hot_tags') }}</router-link>
      <router-link to="/docs" @click="drawerOpen = false">{{ t('docs') }}</router-link>
      <router-link to="/guestbook" @click="drawerOpen = false">{{ t('guestbook') }}</router-link>
    </nav>
    <div class="drawer-foot">
      <template v-if="state.user">
        <span class="drawer-user">👤 {{ state.user.username }}</span>
        <a v-if="state.user.is_admin" class="drawer-link" href="/admin" @click="drawerOpen = false">🛠️ 后台</a>
        <a v-else class="drawer-link" href="/admin/post/new" @click="drawerOpen = false">✏️ 写文章</a>
        <a class="drawer-link" href="#" @click.prevent="doLogout(); drawerOpen = false">退出登录</a>
      </template>
      <template v-else>
        <router-link class="drawer-link" to="/login" @click="drawerOpen = false">登录</router-link>
        <router-link class="drawer-link" to="/register" @click="drawerOpen = false">注册</router-link>
      </template>
      <button class="drawer-link drawer-theme" type="button" @click="toggleTheme(); drawerOpen = false">主题：{{ themeIcon }}</button>
      <button class="drawer-link drawer-lang" type="button" @click="toggleLang(); drawerOpen = false">{{ state.lang === 'en' ? '中文' : 'EN' }}</button>
    </div>
  </aside>

  <header class="site-header">
    <div class="container header-inner">
      <button class="hamburger" type="button" aria-label="打开菜单" @click="drawerOpen = true">☰</button>
      <router-link class="logo" to="/" @click="drawerOpen = false">{{ state.site.site_name || state.site.site_title }}</router-link>
      <nav>
        <router-link to="/">{{ t('home') }}</router-link>
        <router-link to="/archive">{{ t('archive') }}</router-link>
        <router-link to="/stats">{{ t('stats') }}</router-link>
        <router-link to="/about">{{ t('about') }}</router-link>
        <router-link to="/links">{{ t('links') }}</router-link>
        <router-link to="/square">{{ t('square') }}</router-link>
        <router-link to="/series">{{ t('series') }}</router-link>
        <router-link to="/tags/hot">{{ t('hot_tags') }}</router-link>
        <router-link to="/docs">{{ t('docs') }}</router-link>
        <router-link to="/guestbook">{{ t('guestbook') }}</router-link>
        <template v-if="state.user">
          <span class="nav-user">
            👤 {{ state.user.username }}
            <span v-if="state.user.is_admin"><a href="/admin">后台</a></span>
            <span v-else><a href="/admin/post/new">✏️ 写文章</a></span>
          </span>
          <div class="nav-bell" @click="toggleNotifPanel">
            🔔<span v-if="notifUnread" class="bell-badge">{{ notifUnread > 99 ? '99+' : notifUnread }}</span>
            <div v-if="showNotifPanel" class="notif-panel">
              <div class="notif-head">
                <span>通知（{{ notifUnread }} 未读）</span>
                <a v-if="notifUnread" href="#" @click.prevent="markAllNotifRead">全部已读</a>
              </div>
              <div v-if="notifList.length" class="notif-list">
                <a v-for="n in notifList" :key="n.id" class="notif-item" :class="{unread: !n.is_read}" :href="n.link || '#'" @click.prevent="openNotif(n)">
                  <span class="notif-time">{{ n.created_at }}</span>
                  <span class="notif-text">{{ n.content }}</span>
                </a>
              </div>
              <p v-else class="notif-empty">暂无通知</p>
            </div>
          </div>
          <a href="#" @click.prevent="doLogout">{{ t('logout') }}</a>
        </template>
        <template v-else>
          <router-link to="/login">{{ t('login') }}</router-link>
          <router-link to="/register">{{ t('register') }}</router-link>
        </template>
        <button class="lang-toggle" type="button" @click="toggleLang" :title="t('theme')">{{ state.lang === 'en' ? '中' : 'EN' }}</button>
        <button class="theme-toggle" type="button" aria-label="切换亮暗主题" @click="toggleTheme">{{ themeIcon }}</button>
      </nav>
    </div>
  </header>

  <!-- 站点公告（后台可配置，可关闭） -->
  <div v-if="announcements.length" class="ann-wrap">
    <div v-for="a in announcements" :key="a.id" class="ann-bar" :class="'ann-' + a.level">
      <span v-html="a.content"></span>
      <button v-if="a.dismissible" class="ann-close" type="button" aria-label="关闭" @click="dismissAnn(a.id)">✕</button>
    </div>
  </div>

  <!-- 浏览器便签：后台可编辑，点 × 关闭（本次会话不再显示） -->
  <div v-if="state.site.site_note && !noteClosed" class="site-note">
    <span class="site-note-text">{{ state.site.site_note }}</span>
    <button class="site-note-close" type="button" aria-label="关闭便签" @click="noteClosed = true">✕</button>
  </div>

  <!-- 大框架：统一框住公告/便签/正文/页脚（v3.1.0，视觉与后台 .section-box 一致） -->
  <!-- 文档页（/docs）内容极宽，用 site-frame--wide 打破 1100px 限宽并放开裁剪，否则三栏布局被压窄、右侧「本页目录」被媒体查询隐藏 -->
  <div class="site-frame" :class="{ 'site-frame--wide': $route.name === 'docs' }">
    <main class="site-frame-inner">
      <router-view v-slot="{ Component }">
        <component :is="Component" />
      </router-view>
    </main>

    <footer class="site-footer">
      <p>{{ state.site.footer_text }}</p>
      <p v-if="state.site.beian_code">
        <a href="https://beian.miit.gov.cn" target="_blank" rel="noopener">{{ state.site.beian_code }}</a>
      </p>
    </footer>
  </div>

  <button id="back-to-top" title="回到顶部" aria-label="回到顶部" @click="scrollTop">↑</button>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { state, initSite, logout, t, setLang } from "./store.js";
import { apiPost, apiGet } from "./lib/api.js";
const themeIcon = ref("🌙");
const noteClosed = ref(false);
const drawerOpen = ref(false);  // v2.6.0 mobile 抽屉开关
const announcements = ref([]);
const router = useRouter();
// 站内通知（A4）
const notifUnread = ref(0);
const notifList = ref([]);
const showNotifPanel = ref(false);

async function loadNotifs() {
  if (!state.user) { notifUnread.value = 0; notifList.value = []; return; }
  try {
    const d = await apiGet("/api/notifications");
    notifUnread.value = d.unread || 0;
    notifList.value = d.items || [];
  } catch (e) {}
}
function toggleNotifPanel() {
  showNotifPanel.value = !showNotifPanel.value;
  if (showNotifPanel.value) loadNotifs();
}
async function openNotif(n) {
  if (!n.is_read) {
    try { await apiPost(`/api/notification/${n.id}/read`, {}); n.is_read = true; notifUnread.value = Math.max(0, notifUnread.value - 1); } catch (e) {}
  }
  showNotifPanel.value = false;
  if (n.link) { location.href = n.link; }
}
async function markAllNotifRead() {
  try { await apiPost("/api/notifications/read-all", {}); notifList.value.forEach(n => n.is_read = true); notifUnread.value = 0; } catch (e) {}
}

function dismissAnn(id) {
  announcements.value = announcements.value.filter((a) => a.id !== id);
}

// 访问埋点：每次路由切换上报一次（后台页面跳过）
function trackVisit(to) {
  const path = to.path || window.location.pathname || "/";
  if (path.startsWith("/admin")) return;
  apiPost("/api/stats/visit", { path }).catch(() => {});
}
router.afterEach((to) => trackVisit(to));

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  themeIcon.value = t === "dark" ? "☀️" : "🌙";
  // 修复 v3.2.x：store.applyThemeVars 用内联 style 写死了 --nav-fg 等导航变量（浅色 #555555），
  // 内联优先级高于 [data-theme="dark"] 的 CSS 重定义 → 暗色下汉堡抽屉文字仍是深灰，看不清。
  // 这里在主题切换时同步刷新导航变量：暗色用暗色值，浅色恢复由后台设置决定的值。
  const el = document.documentElement;
  if (t === "dark") {
    el.style.setProperty("--nav-bg", "#1d2025");
    el.style.setProperty("--nav-fg", "#e6e8eb");
    el.style.setProperty("--nav-border", "#2a2e35");
  } else {
    // 浅色：按后台 nav_style 设置回写（与 store.applyThemeVars 一致）
    const darkNav = state.site.nav_style === "dark";
    el.style.setProperty("--nav-bg", darkNav ? "#1d2025" : "#ffffff");
    el.style.setProperty("--nav-fg", darkNav ? "#e6e8eb" : "#555555");
    el.style.setProperty("--nav-border", darkNav ? "#2a2e35" : "#ececec");
  }
}
function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  applyTheme(next);
  try { localStorage.setItem("theme", next); } catch (e) {}
}

// 读取用户手动选择的主题（localStorage），无则返回 null（交由系统/后台默认决定）
function savedTheme() {
  try { return localStorage.getItem("theme"); } catch (e) { return null; }
}

// 系统深色偏好变化监听（仅当用户未手动选择主题时跟随系统，v3.1.0 修复）
let _darkMq = null;
function watchSystemTheme() {
  if (!window.matchMedia) return;
  _darkMq = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => {
    // 用户手动选过主题则不再跟随系统，保持手动选择
    if (savedTheme()) return;
    applyTheme(_darkMq.matches ? "dark" : "light");
  };
  if (_darkMq.addEventListener) _darkMq.addEventListener("change", handler);
  else if (_darkMq.addListener) _darkMq.addListener(handler);
}

// v3.0.0 功能11：中英语言切换
function toggleLang() {
  setLang(state.lang === "en" ? "zh" : "en");
}

function scrollTop() { window.scrollTo({ top: 0, behavior: "smooth" }); }

async function doLogout() {
  await logout();
  router.push("/");
}

// 阅读进度条 + 回到顶部显示
function onScroll() {
  const h = document.documentElement;
  const scrolled = h.scrollTop || document.body.scrollTop;
  const total = (h.scrollHeight || document.body.scrollHeight) - h.clientHeight;
  const bar = document.getElementById("reading-progress");
  const top = document.getElementById("back-to-top");
  if (bar) bar.style.width = (total > 0 ? Math.min(100, (scrolled / total) * 100) : 0) + "%";
  if (top) top.style.display = scrolled > 320 ? "block" : "none";
}

onMounted(async () => {
  await initSite();
  // v3.1.0 修复：initSite 内部 applyDefaultTheme 仅在「用户未手动选过主题」时设置 data-theme；
  // 若用户曾手动切到 dark（localStorage 有值），需在此据 localStorage 修正并同步图标，
  // 否则页面会停在 light，导致手机端汉堡菜单等暗色样式不生效（不随主题切换）。
  const saved = savedTheme();
  if (saved === "dark" || saved === "light") {
    applyTheme(saved);
  } else {
    applyTheme(currentTheme());
  }
  watchSystemTheme();
  try {
    const an = await apiGet("/api/announcements");
    announcements.value = an.items || [];
  } catch (e) {}
  loadNotifs();  // 加载站内通知未读数
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  onScroll();
});
// 路由切换后刷新通知（评论被@后能及时看到）
router.afterEach(() => { loadNotifs(); });
</script>
