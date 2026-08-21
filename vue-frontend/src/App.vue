<template>
  <div class="reading-progress" id="reading-progress"></div>
  <header class="site-header">
    <div class="container header-inner">
      <router-link class="logo" to="/">{{ state.site.site_name || state.site.site_title }}</router-link>
      <nav>
        <router-link to="/">首页</router-link>
        <router-link to="/archive">归档</router-link>
        <router-link to="/stats">统计</router-link>
        <router-link to="/about">关于</router-link>
        <router-link to="/links">友链</router-link>
        <router-link to="/square">广场</router-link>
        <template v-if="state.user">
          <span class="nav-user">
            👤 {{ state.user.username }}
            <span v-if="state.user.is_admin"><a href="/admin">后台</a></span>
            <span v-else><a href="/admin/post/new">✏️ 写文章</a></span>
          </span>
          <a href="#" @click.prevent="doLogout">退出</a>
        </template>
        <template v-else>
          <router-link to="/login">登录</router-link>
          <router-link to="/register">注册</router-link>
        </template>
        <button class="theme-toggle" type="button" aria-label="切换亮暗主题" @click="toggleTheme">{{ themeIcon }}</button>
      </nav>
    </div>
  </header>

  <!-- 浏览器便签：后台可编辑，点 × 关闭（本次会话不再显示） -->
  <div v-if="state.site.site_note && !noteClosed" class="site-note">
    <span class="site-note-text">{{ state.site.site_note }}</span>
    <button class="site-note-close" type="button" aria-label="关闭便签" @click="noteClosed = true">✕</button>
  </div>

  <main class="container">
    <router-view v-slot="{ Component }">
      <component :is="Component" />
    </router-view>
  </main>

  <footer class="site-footer">
    <div class="container">
      <p>{{ state.site.footer_text }}</p>
      <p v-if="state.site.beian_code">
        <a href="https://beian.miit.gov.cn" target="_blank" rel="noopener">{{ state.site.beian_code }}</a>
      </p>
    </div>
  </footer>

  <button id="back-to-top" title="回到顶部" aria-label="回到顶部" @click="scrollTop">↑</button>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { state, initSite, logout } from "./store.js";
import { apiPost } from "./lib/api.js";
const themeIcon = ref("🌙");
const noteClosed = ref(false);
const router = useRouter();

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
}
function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  applyTheme(next);
  try { localStorage.setItem("theme", next); } catch (e) {}
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
  applyTheme(currentTheme());
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  onScroll();
});
</script>
