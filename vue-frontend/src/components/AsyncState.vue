<template>
  <!-- 统一的异步状态占位容器。role="status" + aria-live="polite" 让四态切换被读屏播报；
       容器常驻、只换内部内容，避免「live region 与文本同帧出现」不播报的经典陷阱。 -->
  <div class="async-state" role="status" aria-live="polite">
    <template v-if="state === 'loading'">
      <!-- 骨架条只挂 global.css 的现成类名 .skel-card / .skel-line / .skel-title / .skel-short，
           动画名 skel-shimmer（常被口头误称为 ".skel-shimmer 类"）由 @keyframes 提供，
           这里不重复实现动画、也不写死任何颜色。 -->
      <div class="skel-card" aria-hidden="true">
        <div class="skel-line skel-title"></div>
        <div class="skel-line"></div>
        <div class="skel-line skel-short"></div>
      </div>
    </template>

    <p v-else-if="state === 'empty'" class="async-msg">{{ message || "暂无数据" }}</p>

    <div v-else-if="state === 'error'" class="async-error">
      <p class="async-msg">{{ message || "加载失败，请稍后重试" }}</p>
      <button v-if="retry" type="button" class="async-retry" @click="retry">重试</button>
    </div>

    <template v-else-if="state === 'ready'"><slot></slot></template>
  </div>
</template>

<script setup>
// 与仓库现有组件风格一致：<script setup> + defineProps，默认导出 SFC，
// 可被 `import AsyncState from "./AsyncState.vue"` 直接引入。
defineProps({
  // 'loading' | 'empty' | 'error' | 'ready'
  state: { type: String, default: "loading" },
  message: { type: String, default: "" },
  retry: { type: Function, default: null },
});
</script>

<style scoped>
/* 颜色一律走设计系统变量（tokens.css），明暗主题自适应，不新增裸 hex。 */
.async-state { color: var(--text); }
.async-msg {
  margin: 0;
  padding: var(--space-4) var(--space-5);
  color: var(--text-muted);
  font-size: var(--type-meta);
  text-align: center;
}
.async-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-5);
}
.async-retry {
  padding: var(--space-2) var(--space-5);
  background: var(--accent);
  color: var(--on-accent);
  border: 1px solid var(--border);
  border-radius: var(--ui-radius-card);
  box-shadow: var(--ui-shadow-card);
  font-size: var(--type-meta);
  font-family: inherit;
  cursor: pointer;
}
.async-retry:hover { background: var(--accent-hover); }
</style>
