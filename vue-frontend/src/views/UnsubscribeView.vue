<template>
  <div class="container unsub-wrap">
    <div class="unsub-card">
      <h2>邮件退订</h2>
      <template v-if="status === 'loading'">
        <p class="unsub-tip">正在查询订阅状态…</p>
      </template>
      <template v-else-if="status === 'error'">
        <p class="unsub-tip err">{{ errorMsg }}</p>
        <router-link to="/" class="btn">返回首页</router-link>
      </template>
      <template v-else-if="status === 'done'">
        <p class="unsub-tip ok">✅ {{ email }} 已成功退订，不再发送新文章邮件。</p>
        <router-link to="/" class="btn">返回首页</router-link>
      </template>
      <template v-else>
        <p class="unsub-tip">确认要退订 <strong>{{ email }}</strong> 的新文章邮件通知吗？</p>
        <button class="btn" :disabled="submitting" @click="confirmUnsub">{{ submitting ? '处理中…' : '确认退订' }}</button>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import { apiGet, apiPost } from "../lib/api.js";

const route = useRoute();
const status = ref("loading");
const email = ref("");
const errorMsg = ref("");
const submitting = ref(false);

onMounted(async () => {
  email.value = (route.query.email || "").toString().trim();
  const token = (route.query.token || "").toString().trim();
  if (!email.value || !token) {
    status.value = "error";
    errorMsg.value = "退订链接不完整（缺少 email 或 token）";
    return;
  }
  try {
    const d = await apiGet("/api/unsubscribe", { email: email.value, token });
    if (!d.ok) throw new Error(d.error || "查询失败");
    status.value = "confirm";
  } catch (e) {
    status.value = "error";
    errorMsg.value = e.message || "退订链接已失效";
  }
});

async function confirmUnsub() {
  const token = (route.query.token || "").toString().trim();
  submitting.value = true;
  try {
    await apiPost("/api/unsubscribe", { email: email.value, token });
    status.value = "done";
  } catch (e) {
    status.value = "error";
    errorMsg.value = e.message || "退订失败，请稍后再试";
  } finally {
    submitting.value = false;
  }
}
</script>
