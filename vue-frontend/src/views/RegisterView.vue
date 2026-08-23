<template>
  <div class="container">
    <div class="auth-box">
      <h1 class="page-title">注册账号</h1>
      <p class="auth-tip">注册后可登录评论，昵称会显示在评论里。</p>
      <form class="comment-form" @submit.prevent="submit">
        <input type="text" v-model="username" placeholder="用户名（2-20 字符）" minlength="2" maxlength="20" required />
        <input type="email" v-model="email" placeholder="邮箱（可选）" />
        <input type="password" v-model="password" placeholder="密码（至少 8 位，含字母和数字）" minlength="8" required />
        <input type="password" v-model="confirm" placeholder="确认密码" minlength="8" required />
        <!-- v3.1.6 可选增强：注册验证码 -->
        <div v-if="captchaEnabled" class="captcha-row">
          <input type="text" v-model="captcha" placeholder="验证码（不区分大小写）" maxlength="4" required />
          <img :src="captchaUrl" alt="验证码" class="captcha-img" @click="refreshCaptcha" title="点击刷新" />
        </div>
        <div>
          <button type="submit">注册</button>
          <span class="comment-status" :class="statusClass" style="margin-left: 10px;">{{ status }}</span>
        </div>
      </form>
      <p class="auth-tip">已有账号？<router-link to="/login">去登录</router-link></p>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { register } from "../store.js";
import { apiGet } from "../lib/api.js";

const router = useRouter();
const username = ref("");
const email = ref("");
const password = ref("");
const confirm = ref("");
const captcha = ref("");
const captchaEnabled = ref(true);
const captchaUrl = ref("");
const status = ref("");
const statusClass = ref("");

// v3.1.6 可选增强：注册验证码（CAPTCHA_ENABLED；后端/PIL 不可用时会返回降级关闭）
async function refreshCaptcha() {
  try {
    captchaUrl.value = "/api/captcha?" + Date.now() + "&from=register";
  } catch (e) {}
}
async function initCaptcha() {
  // v3.2.0：读取后台验证码配置，按「注册」场景显隐（全局关闭 / 场景关闭 / Pillow 缺失均自动隐藏）
  try {
    const cfg = await apiGet("/api/captcha/config");
    const ok = cfg && cfg.enabled && cfg.available && cfg.scenes && cfg.scenes.register;
    if (ok) {
      captchaEnabled.value = true;
      refreshCaptcha();
    } else {
      captchaEnabled.value = false;
    }
  } catch (e) {
    captchaEnabled.value = false;
  }
}
initCaptcha();

async function submit() {
  if (password.value !== confirm.value) {
    status.value = "两次输入的密码不一致";
    statusClass.value = "error";
    return;
  }
  status.value = "注册中…";
  statusClass.value = "";
  try {
    await register(username.value.trim(), email.value.trim(), password.value, captcha.value);
    router.push("/");
  } catch (e) {
    status.value = e.message || "注册失败";
    statusClass.value = "error";
    if (captchaEnabled.value) refreshCaptcha();
  }
}
</script>
