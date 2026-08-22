<template>
  <article class="post-card">
    <router-link v-if="post.cover" :to="`/post/${post.slug}`" class="cover-wrap">
      <img :src="post.cover" :alt="post.title" loading="lazy" />
    </router-link>
    <h2>
      <span v-if="post.is_pinned" class="pin-badge" title="置顶文章">📌</span>
      <router-link :to="`/post/${post.slug}`">{{ post.title }}</router-link>
    </h2>
    <p class="post-meta">
      <span>{{ (post.created_at || "").slice(0, 10) }}</span>
      <span v-if="post.author"> · ✍️ {{ post.author }}</span>
      <span v-if="post.category"> · <router-link :to="`/category/${post.category.slug}`">{{ post.category.name }}</router-link></span>
      <span> · {{ post.views || 0 }} 阅读</span>
    </p>
    <p v-if="post.summary" class="post-summary">{{ post.summary }}</p>
    <router-link class="read-more" :to="`/post/${post.slug}`">阅读全文 →</router-link>
  </article>
</template>

<script setup>
defineProps({ post: Object });
</script>
