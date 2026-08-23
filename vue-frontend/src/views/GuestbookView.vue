<template>
  <div class="layout">
    <main class="content">
      <h1 class="page-title">留言墙</h1>
      <p class="empty" v-if="!state.user">登录后也可以在这里留言哦～</p>

      <form class="guestbook-form" @submit.prevent="submit" v-if="state.user">
        <textarea v-model="content" placeholder="写点什么留给站长…（必填，500 字内）" maxlength="500" rows="4" required></textarea>
        <!-- v3.1.6 可选增强：留言验证码 -->
        <div v-if="captchaEnabled" class="captcha-row">
          <input type="text" v-model="captcha" placeholder="验证码（不区分大小写）" maxlength="4" required />
          <img :src="captchaUrl" alt="验证码" class="captcha-img" @click="refreshCaptcha" title="点击刷新" />
        </div>
        <div>
          <button type="submit">发送留言</button>
          <span :class="'comment-status ' + statusClass" style="margin-left:10px;">{{ status }}</span>
        </div>
      </form>
      <p v-else class="hint">前往 <router-link to="/login">登录</router-link> 后留言。</p>

      <div class="guestbook-list">
        <div v-for="g in items" :key="g.id" class="guestbook-item">
          <p class="gb-meta">{{ g.author }} · {{ (g.created_at || "").slice(0, 16) }} <span v-if="g.region">· 📍 {{ g.region }}</span></p>
          <p class="gb-content">{{ g.content }}</p>
          <button class="gb-like-btn" type="button" @click="like(g)">👍 {{ g.likes }}</button>
        </div>
      </div>
      <p v-if="!items.length" class="empty">还没有留言，来当第一个吧！</p>
    </main>
    <Sidebar />
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { apiGet, apiPost } from "../lib/api.js";
import { state } from "../store.js";
import Sidebar from "../components/Sidebar.vue";

const items = ref([]);
const content = ref("");
const status = ref("");
const statusClass = ref("");
const captcha = ref("");
const captchaEnabled = ref(true);
const captchaUrl = ref("");

// v3.1.6 可选增强：留言验证码（CAPTCHA_ENABLED；后端/PIL 不可用时会返回降级关闭）
function refreshCaptcha() {
  captchaUrl.value = "/api/captcha?" + Date.now() + "&from=guestbook";
}
async function initCaptcha() {
  try {
    const r = await fetch("/api/captcha?" + Date.now(), { credentials: "same-origin" });
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("image")) {
      captchaEnabled.value = true;
      captchaUrl.value = r.url;
    } else {
      captchaEnabled.value = false;
    }
  } catch (e) {
    captchaEnabled.value = false;
  }
}
initCaptcha();

async function load() {
  try { const d = await apiGet("/api/guestbook"); items.value = d.items || []; }
  catch (e) { items.value = []; }
}
async function submit() {
  if (!content.value.trim()) { status.value = "留言不能为空"; statusClass.value = "error"; return; }
  const body = { content: content.value.trim() };
  if (captchaEnabled.value) body.captcha = captcha.value.trim();
  status.value = "发送中…"; statusClass.value = "";
  try {
    await apiPost("/api/guestbook", body);
    status.value = "留言成功！"; statusClass.value = "success"; content.value = "";
    if (captchaEnabled.value) refreshCaptcha();
    load();
  } catch (e) { status.value = e.message || "网络错误"; statusClass.value = "error"; if (captchaEnabled.value) refreshCaptcha(); }
}
async function like(g) {
  try { const r = await apiPost(`/api/guestbook/${g.id}/like`); g.likes = r.likes; }
  catch (e) {}
}
onMounted(load);
</script>
