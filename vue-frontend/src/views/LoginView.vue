<template>
  <div class="container">
    <div class="auth-box">
      <h1 class="page-title">登录</h1>
      <form class="comment-form" @submit.prevent="submit">
        <input type="text" v-model="username" placeholder="用户名" required autofocus />
        <input type="password" v-model="password" placeholder="密码" required />
        <div>
          <button type="submit">登录</button>
          <span class="comment-status" :class="statusClass" style="margin-left: 10px;">{{ status }}</span>
        </div>
      </form>
      <p v-if="state.user" class="auth-tip" style="color: var(--accent);">
        ✅ 已登录：{{ state.user.username }}（{{ state.user.role_label }}）
      </p>
      <p class="auth-tip">还没有账号？<router-link to="/register">注册一个</router-link></p>
      <p class="auth-tip" v-if="state.user">
        快捷入口：<a :href="state.user.is_admin ? '/admin' : '/admin/post/new'">进入写作后台 →</a>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { login } from "../store.js";
import { state } from "../store.js";

const route = useRoute();
const router = useRouter();
const username = ref("");
const password = ref("");
const status = ref("");
const statusClass = ref("");

async function submit() {
  status.value = "登录中…";
  statusClass.value = "";
  try {
    const user = await login(username.value.trim(), password.value);
    // 登录成功：按来源与角色分流
    // - 带了合法的 next（非后台首页）→ 优先跳过去（后端会再校验权限）
    // - 管理员 → 仪表盘
    // - 普通用户 → 写作区（写文章）
    const next = route.query.next || "";
    if (next && next.startsWith("/") && !next.startsWith("//") && !(next === "/admin" || next === "/admin/")) {
      router.push(next);
    } else if (user.is_admin) {
      router.push("/admin");
    } else {
      router.push("/admin/post/new");
    }
  } catch (e) {
    status.value = e.message || "登录失败";
    statusClass.value = "error";
  }
}
</script>
