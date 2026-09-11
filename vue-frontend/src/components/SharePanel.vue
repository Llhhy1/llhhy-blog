<template>
  <div class="share-wrap">
    <button class="share-btn" type="button" @click="toggle" aria-haspopup="dialog">
      <svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg>
      分享到…
    </button>

    <transition name="share-pop">
      <div v-if="open" class="share-panel" role="dialog" aria-label="分享文章">
        <!-- 分享卡预览：直接预览服务端动态生成的 OG 图，所见即所得 -->
        <div v-if="ogCardUrl" class="share-card-preview">
          <img :src="ogCardUrl" alt="分享卡预览" loading="lazy" @error="ogCardUrl=''" />
          <span class="share-card-tag">分享卡片预览</span>
        </div>

        <p class="share-panel-title">分享「{{ shortTitle }}」</p>

        <div class="share-grid">
          <button class="share-item" type="button" @click="copyLink">
            <span class="share-ico" style="--b:#5b6470"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M10 13a5 5 0 007.5.5l3-3a5 5 0 00-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 00-7.5-.5l-3 3a5 5 0 007 7l1.7-1.7"/></svg></span>
            复制链接
          </button>
          <a v-if="canNativeShare" class="share-item" type="button" href="javascript:void(0)" @click.prevent="nativeShare">
            <span class="share-ico" style="--b:#188038"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-7"/><path d="M16 6l-4-4-4 4"/><path d="M12 2v13"/></svg></span>
            系统分享
          </a>
          <a class="share-item" :href="shareUrl('weibo')" target="_blank" rel="noopener">
            <span class="share-ico" style="--b:#e6162d">微</span>微博
          </a>
          <a class="share-item" :href="shareUrl('qq')" target="_blank" rel="noopener">
            <span class="share-ico" style="--b:#12b7f5">QQ</span>QQ
          </a>
          <button class="share-item" type="button" @click="showQr">
            <span class="share-ico" style="--b:#07c160">微</span>微信扫码
          </button>
          <a class="share-item" :href="shareUrl('x')" target="_blank" rel="noopener">
            <span class="share-ico" style="--b:#0f1419">𝕏</span>Twitter/X
          </a>
          <a class="share-item" :href="shareUrl('telegram')" target="_blank" rel="noopener">
            <span class="share-ico" style="--b:#229ed9">TG</span>Telegram
          </a>
          <a class="share-item" :href="shareUrl('facebook')" target="_blank" rel="noopener">
            <span class="share-ico" style="--b:#1877f2">f</span>Facebook
          </a>
          <a class="share-item" :href="shareUrl('linkedin')" target="_blank" rel="noopener">
            <span class="share-ico" style="--b:#0a66c2">in</span>LinkedIn
          </a>
        </div>

        <transition name="share-pop">
          <div v-if="qrOpen" class="share-qr">
            <img v-if="qrUrl" :src="qrUrl" alt="微信扫码分享" width="132" height="132" />
            <p>微信扫码，手机打开后右上角分享</p>
          </div>
        </transition>

        <p class="share-hint">卡片图按文章实时生成；微博/QQ/X/TG/FB/LinkedIn 自动抓取标题与摘要。</p>
      </div>
    </transition>

    <span v-if="tip" class="share-tip">{{ tip }}</span>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { copyText } from "../lib/clipboard.js";

const props = defineProps({
  title: { type: String, default: "" },
  slug: { type: String, default: "" },
});

const open = ref(false);
const tip = ref("");
const qrOpen = ref(false);
const qrUrl = ref("");
const canNativeShare = ref(false);
onMounted(() => { canNativeShare.value = typeof navigator !== "undefined" && !!navigator.share; });

const shortTitle = computed(() => (props.title || "").slice(0, 30));
const postUrl = computed(() => props.slug ? new URL(`/post/${props.slug}`, location.origin).href : location.href);
// 服务端动态生成的分享卡（与 og:image 同源，所见即所得）
const ogCardUrl = ref(props.slug ? `/api/og/post/${props.slug}.png` : "");

function toggle() {
  open.value = !open.value;
  tip.value = "";
  if (!open.value) qrOpen.value = false;
}

function shareUrl(kind) {
  const u = encodeURIComponent(postUrl.value);
  const t = encodeURIComponent(props.title || "");
  const map = {
    weibo: `https://service.weibo.com/share/share.php?url=${u}&title=${t}`,
    qq: `https://connect.qq.com/widget/shareqq/index.html?url=${u}&title=${t}&summary=`,
    x: `https://twitter.com/intent/tweet?url=${u}&text=${t}`,
    telegram: `https://t.me/share/url?url=${u}&text=${t}`,
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${u}`,
    linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${u}`,
  };
  return map[kind] || "#";
}

function flash(msg) {
  tip.value = msg;
  setTimeout(() => { tip.value = ""; }, 2000);
}

async function copyLink() {
  // v3.17.9：统一走三层兜底复制（Clipboard API → execCommand → 手动提示）
  const ok = await copyText(postUrl.value);
  flash(ok ? "链接已复制，去分享吧！" : "已弹窗，请手动复制链接");
}

function showQr() {
  qrOpen.value = !qrOpen.value;
  if (qrOpen.value && !qrUrl.value) {
    qrUrl.value = `/api/qr?url=${encodeURIComponent(postUrl.value)}`;
  }
}

async function nativeShare() {
  try {
    await navigator.share({ title: props.title || "", url: postUrl.value });
  } catch (e) { /* 用户取消 */ }
}

function onKey(e) { if (e.key === "Escape") { open.value = false; qrOpen.value = false; } }
onMounted(() => document.addEventListener("keydown", onKey));
onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
</script>

<style scoped>
.share-wrap { position: relative; display: inline-block; }
.share-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: var(--radius-pill);
  border: 1px solid var(--border-strong); background: var(--surface);
  color: var(--text); cursor: pointer; font-size: 14px;
  transition: border-color var(--transition), box-shadow var(--transition), transform var(--transition);
}
.share-btn:hover { border-color: var(--accent); box-shadow: var(--shadow-md); transform: translateY(-1px); }
.share-btn .ic { width: 16px; height: 16px; color: var(--accent); }

.share-panel {
  position: absolute; z-index: 60; top: calc(100% + 10px); left: 0;
  width: min(340px, calc(100vw - 32px));
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-lg);
  padding: 16px;
}
.share-card-preview { position: relative; margin-bottom: 12px; border-radius: var(--radius-md); overflow: hidden; border: 1px solid var(--border); }
.share-card-preview img { display: block; width: 100%; aspect-ratio: 1200/630; object-fit: cover; }
.share-card-tag {
  position: absolute; left: 8px; top: 8px; font-size: 11px;
  padding: 2px 8px; border-radius: var(--radius-pill);
  background: rgba(0,0,0,.45); color: #fff; backdrop-filter: blur(4px);
}
.share-panel-title { margin: 0 0 10px; font-size: 13px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.share-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.share-item {
  display: flex; flex-direction: column; align-items: center; gap: 5px;
  padding: 8px 2px; border: 0; background: transparent; border-radius: var(--radius-md);
  color: var(--text); font-size: 12px; text-decoration: none; cursor: pointer;
  transition: background var(--transition), transform var(--transition);
}
.share-item:hover { background: var(--surface-2); transform: translateY(-1px); }
.share-ico {
  width: 34px; height: 34px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--b, var(--accent)); color: #fff; font-size: 13px; font-weight: 600;
}
.share-ico svg { width: 16px; height: 16px; }

.share-qr { margin-top: 12px; text-align: center; }
.share-qr img { background: #fff; border-radius: var(--radius-md); border: 1px solid var(--border); }
.share-qr p { margin: 6px 0 0; font-size: 12px; color: var(--text-muted); }
.share-hint { margin: 12px 0 0; font-size: 12px; color: var(--text-faint); line-height: 1.6; }

.share-tip {
  position: fixed; left: 50%; bottom: 48px; transform: translateX(-50%);
  z-index: 200; padding: 9px 18px; border-radius: var(--radius-pill);
  background: var(--text); color: var(--bg); font-size: 13px; box-shadow: var(--shadow-lg);
}

.share-pop-enter-active, .share-pop-leave-active { transition: opacity .18s ease, transform .18s ease; }
.share-pop-enter-from, .share-pop-leave-to { opacity: 0; transform: translateY(6px) scale(.98); }
</style>
