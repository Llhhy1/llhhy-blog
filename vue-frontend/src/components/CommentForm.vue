<template>
  <section class="comments" id="comments">
    <h2>评论 ({{ comments.length }})</h2>
    <div v-if="!comments.length" class="comment-empty">还没有评论，来沙发？</div>
    <div v-for="c in comments" :key="c.id" class="comment">
      <p class="comment-meta">{{ c.author }} · {{ (c.created_at || "").slice(0, 16) }}</p>
      <p class="comment-meta" v-if="c.region || c.device">
        <span v-if="c.region">📍 {{ c.region }}</span>
        <span v-if="c.device">{{ c.region ? " · " : "" }}{{ c.device }}</span>
      </p>
      <p class="comment-content">{{ c.content }}</p>
    </div>

    <form class="comment-form" autocomplete="off" @submit.prevent="submit">
      <input v-if="!state.user" type="text" v-model="author" placeholder="昵称（必填，2-20 字）" maxlength="20" required />
      <textarea v-model="content" placeholder="说点什么…（必填，2-500 字）" maxlength="500" required></textarea>
      <div>
        <button type="submit">提交评论</button>
        <span class="comment-status" :class="statusClass" style="margin-left: 10px;">{{ status }}</span>
      </div>
    </form>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { apiPost } from "../lib/api.js";
import { state } from "../store.js";

const props = defineProps({ slug: String, comments: Array });
const author = ref("");
const content = ref("");
const status = ref("");
const statusClass = ref("");

async function submit() {
  if (!content.value.trim()) { status.value = "评论内容不能为空"; statusClass.value = "error"; return; }
  if (!state.user && !author.value.trim()) { status.value = "请填写昵称"; statusClass.value = "error"; return; }
  const body = { content: content.value.trim() };
  // 已登录（含超级管理员/管理员/普通用户）：昵称由后端从会话取，不需要前端传
  if (!state.user) body.author = author.value.trim();
  status.value = "提交中…";
  statusClass.value = "";
  try {
    await apiPost(`/api/post/${props.slug}/comment`, body);
    status.value = "评论成功！";
    statusClass.value = "success";
    content.value = "";
    setTimeout(() => window.location.reload(), 600);
  } catch (e) {
    status.value = e.message || "网络错误";
    statusClass.value = "error";
  }
}
</script>
