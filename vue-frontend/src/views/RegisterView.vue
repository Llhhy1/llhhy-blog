<template>
  <div class="container">
    <div class="auth-box">
      <h1 class="page-title">注册账号</h1>
      <p class="auth-tip">注册后可登录评论，昵称会显示在评论里。</p>
      <form class="comment-form" @submit.prevent="submit">
        <input type="text" v-model="username" placeholder="用户名（2-20 字符）" minlength="2" maxlength="20" required />
        <input type="email" v-model="email" placeholder="邮箱（可选）" />
        <input type="password" v-model="password" placeholder="密码（至少 8 位）" minlength="8" required />
        <input type="password" v-model="confirm" placeholder="确认密码" minlength="8" required />
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

const router = useRouter();
const username = ref("");
const email = ref("");
const password = ref("");
const confirm = ref("");
const status = ref("");
const statusClass = ref("");

async function submit() {
  if (password.value !== confirm.value) {
    status.value = "两次输入的密码不一致";
    statusClass.value = "error";
    return;
  }
  status.value = "注册中…";
  statusClass.value = "";
  try {
    await register(username.value.trim(), email.value.trim(), password.value);
    router.push("/");
  } catch (e) {
    status.value = e.message || "注册失败";
    statusClass.value = "error";
  }
}
</script>
