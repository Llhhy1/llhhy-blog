<template>
  <button class="like-btn" :class="{ liked: liked }" type="button" :disabled="liked" @click="like">
    <span>👍</span> 点赞 <span class="like-count">{{ count }}</span>
  </button>
</template>

<script setup>
import { ref } from "vue";

const props = defineProps({ slug: String, count: Number });
const liked = ref(false);
const count = ref(props.count || 0);
const KEY = "liked." + props.slug;

try { liked.value = localStorage.getItem(KEY) === "1"; } catch (e) {}

async function like() {
  if (liked.value) return;
  try {
    const resp = await fetch("/api/post/" + encodeURIComponent(props.slug) + "/like", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      body: "{}",
    });
    const data = await resp.json();
    if (data && typeof data.likes === "number") count.value = data.likes;
    liked.value = true;
    try { localStorage.setItem(KEY, "1"); } catch (e) {}
  } catch (e) {
    count.value = (count.value || 0) + 1;
    liked.value = true;
  }
}
</script>
