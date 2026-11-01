<template>
  <div class="tp-wrap" :class="{ 'tp-full': full }" ref="wrap">
    <button :class="full ? 'drawer-link tp-row' : 'theme-toggle'" type="button"
            :aria-label="t('theme_picker')"
            aria-haspopup="true" :aria-expanded="open ? 'true' : 'false'" @click="toggle">
      <span class="tp-ico" aria-hidden="true">🎨</span>
      <span v-if="full">{{ t('theme_picker') }}：{{ currentLabel }}</span>
    </button>

    <transition name="tp-pop">
      <div v-if="open" class="tp-panel" role="dialog" :aria-label="t('theme_picker')">
        <p class="tp-tip">{{ t('theme_picker_tip') }}</p>
        <div v-if="packs.length" class="tp-grid">
          <button type="button" class="tp-item" :class="{ on: !picked }"
                  :aria-pressed="!picked ? 'true' : 'false'" @click="pick('')">
            <span class="tp-dots" aria-hidden="true">
              <i :style="{ background: 'var(--accent)' }"></i>
              <i :style="{ background: 'var(--surface-2)' }"></i>
              <i :style="{ background: 'var(--text)' }"></i>
            </span>
            <span class="tp-name">{{ t('theme_follow_site') }}</span>
          </button>
          <button v-for="p in packs" :key="p.id" type="button" class="tp-item"
                  :class="{ on: picked === p.id }" :aria-pressed="picked === p.id ? 'true' : 'false'"
                  :title="p.desc" @click="pick(p.id)">
            <span class="tp-dots" aria-hidden="true">
              <i :style="{ background: p.light.accent }"></i>
              <i :style="{ background: p.light.bg }"></i>
              <i :style="{ background: p.light.text }"></i>
            </span>
            <span class="tp-name">{{ state.lang === 'en' ? p.en : p.name }}</span>
          </button>
        </div>
        <p v-else class="tp-tip">{{ t('loading') }}</p>
      </div>
    </transition>
  </div>
</template>

<script setup>
// 档 1「访客自选主题」（v5.4.x）：站主在主题中心开放后才挂载（见 App.vue 的 v-if）。
// 清单来自服务端 GET /api/theme 的预设包，值本身不经过任何用户输入；选择只写
// localStorage，不改站主设定。token 全部用 --surface/--text 等已定义变量，
// 面板自身也要跟着所选主题走。
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { state, loadThemePacks, setVisitorTheme, t } from "../store.js";

// full=true：手机抽屉里的整行形态（触发器占满一行、面板向下展开）。
// 桌面顶栏用的是 .theme-toggle 胶囊，抽屉里放胶囊会跟 .drawer-link 那排按钮格格不入。
defineProps({ full: { type: Boolean, default: false } });

const open = ref(false);
const wrap = ref(null);
const packs = computed(() => state.themePacks);
const picked = computed(() => state.visitorPack);
const currentLabel = computed(() => {
  const p = packs.value.find(function (x) { return x.id === picked.value; });
  if (!p) return t("theme_follow_site");
  return state.lang === "en" ? p.en : p.name;
});

function toggle() {
  open.value = !open.value;
  if (open.value) loadThemePacks();
}

function pick(id) {
  setVisitorTheme(id);
  open.value = false;
}

// 用捕获阶段：点面板外先关面板，点按钮本身则由 wrap.contains 放行、交给 toggle
function onDocClick(e) {
  if (open.value && wrap.value && !wrap.value.contains(e.target)) open.value = false;
}
function onKey(e) { if (e.key === "Escape") open.value = false; }

onMounted(() => {
  document.addEventListener("click", onDocClick, true);
  document.addEventListener("keydown", onKey);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onDocClick, true);
  document.removeEventListener("keydown", onKey);
});
</script>

<style scoped>
.tp-wrap { position: relative; display: inline-flex; }
.tp-ico { display: inline-block; width: 20px; text-align: center; font-size: 16px; line-height: 1; }
.tp-row { display: flex; align-items: center; gap: 10px; width: 100%; }
.tp-wrap.tp-full { display: block; width: 100%; }
.tp-wrap.tp-full .tp-panel {
  position: static; width: 100%; max-height: none; margin-top: 8px; box-shadow: none;
}
.tp-panel {
  position: absolute; z-index: 70; top: calc(100% + 10px); right: 0;
  width: min(360px, calc(100vw - 24px)); max-height: 70vh; overflow: auto;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); padding: 12px;
}
.tp-tip { margin: 0 0 10px; font-size: var(--type-xs); color: var(--text-muted); }
.tp-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.tp-item {
  display: flex; flex-direction: column; align-items: flex-start; gap: 6px;
  padding: 8px 10px; text-align: left; cursor: pointer;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-2); color: var(--text);
  font-size: var(--type-sm); font-family: inherit;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.tp-item:hover { border-color: var(--accent); }
.tp-item.on { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.tp-dots { display: flex; gap: 4px; }
.tp-dots i {
  width: 14px; height: 14px; border-radius: 50%;
  border: 1px solid var(--border-strong);
}
.tp-pop-enter-active, .tp-pop-leave-active { transition: opacity var(--transition), transform var(--transition); }
.tp-pop-enter-from, .tp-pop-leave-to { opacity: 0; transform: translateY(-6px); }
</style>
