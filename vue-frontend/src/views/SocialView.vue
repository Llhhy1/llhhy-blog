<template>
  <div class="container">
    <h1 class="page-title">🔗 找到我</h1>
    <p class="page-sub">在这些地方都能找到我，欢迎来聊。</p>

    <p v-if="!items.length" class="empty">还没有添加社交账号，去后台「社交账号」里添加吧。</p>

    <div v-else class="social-grid">
      <component
        :is="it.href ? 'a' : 'button'"
        v-for="it in items"
        :key="it.id"
        class="social-card"
        :class="{ 'is-copy': it.mode === 'copy' }"
        :href="it.href || null"
        :target="it.href ? '_blank' : null"
        :rel="it.href ? 'noopener' : null"
        :type="it.href ? null : 'button'"
        @click="it.href ? null : onCopy(it)"
      >
        <span class="social-icon" :style="{ background: it.meta.color || 'var(--surface-2)' }">{{ it.meta.icon }}</span>
        <span class="social-body">
          <span class="social-name">{{ it.meta.label }}</span>
          <span class="social-handle">{{ it.handle || it.tip }}</span>
        </span>
        <span class="social-go">{{ it.href ? '前往 →' : '复制 →' }}</span>
      </component>
    </div>

    <p v-if="items.length" class="social-tip">微信 / QQ 填号码时点击自动复制；填图片地址则展示二维码。</p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../lib/api.js";
import { copyText } from "../lib/clipboard.js";
import { toastOk, toastErr } from "../lib/toast.js";
import { toSocialItem } from "../lib/social.js";

const accounts = ref([]);
const items = computed(() => (accounts.value || []).map(toSocialItem));

onMounted(async () => {
  try {
    accounts.value = await apiGet("/api/social-accounts");
  } catch (e) {
    accounts.value = [];
  }
});

async function onCopy(it) {
  const ok = await copyText(it.url);
  if (ok) toastOk("已复制：" + it.url);
  else toastErr("已弹窗，请手动复制");
}
</script>

<style scoped>
.page-sub { color: var(--text-muted); font-size: 14px; margin: -10px 0 18px; }
.social-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 12px;
}
.social-card {
  display: flex; align-items: center; gap: 12px; padding: 14px;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md, 12px);
  text-decoration: none; color: inherit; text-align: left; cursor: pointer; width: 100%;
  transition: transform 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}
.social-card:hover { transform: translateY(-2px); border-color: var(--accent); box-shadow: 0 4px 14px rgba(0, 0, 0, .06); }
.social-icon {
  flex: 0 0 38px; width: 38px; height: 38px; border-radius: 10px;
  display: grid; place-items: center; font-size: 19px; line-height: 1;
}
.social-body { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.social-name { font-size: 14px; font-weight: 600; }
.social-handle {
  font-size: 12px; color: var(--text-muted); margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.social-go { font-size: 12px; color: var(--accent); flex: 0 0 auto; }
.social-tip { margin-top: 16px; font-size: 12px; color: var(--text-faint); }
@media (max-width: 640px) {
  .social-grid { grid-template-columns: 1fr 1fr; gap: 10px; }
  .social-card { padding: 12px; gap: 10px; }
  .social-icon { flex-basis: 32px; width: 32px; height: 32px; font-size: 16px; }
  .social-go { display: none; }
}
</style>
