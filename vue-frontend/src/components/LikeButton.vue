<template>
  <button class="like-btn" :class="{ liked: liked }" type="button" :disabled="liked" @click="like">
    <span>👍</span> 点赞 <span class="like-count">{{ count }}</span>
  </button>
</template>

<script setup>
import { ref } from "vue";
import { apiPost } from "../lib/api.js";

const props = defineProps({ slug: String, count: Number });
const liked = ref(false);
const count = ref(props.count || 0);
const KEY = "liked." + props.slug;

try { liked.value = localStorage.getItem(KEY) === "1"; } catch (e) {}

async function like() {
  if (liked.value) return;
  try {
    // v3.8.4 修复：改用 apiPost（自动携带 CSRF Token）。
    // 原先裸 fetch 无 token，被后端 CSRF 校验 403 拦截，服务端计数从未 +1。
    const data = await apiPost("/api/post/" + encodeURIComponent(props.slug) + "/like", {});
    if (data && typeof data.likes === "number") count.value = data.likes;
    liked.value = true;
    try { localStorage.setItem(KEY, "1"); } catch (e) {}
  } catch (e) {
    // 失败不再假加一 / 假置已赞（v3.8.4：原 catch 分支本地 +1 误导用户，服务端实际未计入）
    alert(e && e.message ? e.message : "点赞失败，请重试");
  }
}
</script>
