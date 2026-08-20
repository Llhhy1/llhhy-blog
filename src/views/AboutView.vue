<template>
  <div class="container">
    <h1 class="page-title">关于</h1>
    <div class="about-content" v-html="html"></div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";

const html = ref("<p>暂无简介。</p>");
onMounted(async () => {
  try {
    const s = await apiGet("/api/site");
    html.value = s.about_content || html.value;
  } catch (e) {}
});
</script>
