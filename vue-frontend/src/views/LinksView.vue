<template>
  <div class="container">
    <h1 class="page-title">友情链接</h1>
    <p v-if="!links.length" class="empty">还没有友链。</p>
    <ul v-else class="friend-links">
      <li v-for="l in links" :key="l.url">
        <a :href="l.url" target="_blank" rel="noopener">{{ l.name }}</a>
        <div v-if="l.description" class="desc">{{ l.description }}</div>
      </li>
    </ul>

    <!-- 自助申请友链（v3.0.0 功能6） -->
    <div class="link-apply-box">
      <h3>🔗 申请交换友链</h3>
      <p class="sub-tip">填写你的站点信息，管理员审核通过后会展示在上方。请勿提交违规或垃圾站点。</p>
      <form class="link-apply-form" @submit.prevent="submitApply">
        <input type="text" v-model="form.name" placeholder="你的站点名称 *" required />
        <input type="url" v-model="form.url" placeholder="站点链接（http/https）*" required />
        <input type="text" v-model="form.description" placeholder="一句话描述（可选）" />
        <input type="email" v-model="form.email" placeholder="联系邮箱（可选）" />
        <button type="submit" :disabled="applyBusy">{{ applyBusy ? "提交中…" : "提交申请" }}</button>
      </form>
      <p v-if="applyMsg" class="apply-msg" :class="applyOk ? 'ok' : 'err'">{{ applyMsg }}</p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet, apiPost } from "../lib/api.js";

const links = ref([]);
const form = ref({ name: "", url: "", description: "", email: "" });
const applyBusy = ref(false);
const applyMsg = ref("");
const applyOk = ref(false);

onMounted(async () => {
  try { links.value = await apiGet("/api/links"); } catch (e) { links.value = []; }
});

async function submitApply() {
  if (!form.value.name.trim() || !form.value.url.trim()) {
    applyMsg.value = "请填写站点名称和链接"; applyOk.value = false; return;
  }
  applyBusy.value = true; applyMsg.value = "";
  try {
    const d = await apiPost("/api/link-apply", { ...form.value });
    applyOk.value = true;
    applyMsg.value = d.message || "申请已提交";
    form.value = { name: "", url: "", description: "", email: "" };
  } catch (e) {
    applyOk.value = false;
    applyMsg.value = e.message || "提交失败，请稍后再试";
  } finally {
    applyBusy.value = false;
  }
}
</script>
