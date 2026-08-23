<template>
  <section class="comments" id="comments">
    <h2>评论 ({{ allCount }})</h2>
    <div v-if="!topComments.length" class="comment-empty">还没有评论，来沙发？</div>

    <!-- 顶层评论 + 其下回复 -->
    <div v-for="c in topComments" :key="c.id" class="comment-thread">
      <div class="comment">
        <p class="comment-meta">{{ c.author }} · {{ (c.created_at || "").slice(0, 16) }}</p>
        <p class="comment-meta" v-if="c.region || c.device">
          <span v-if="c.region">📍 {{ c.region }}</span>
          <span v-if="c.device">{{ c.region ? " · " : "" }}{{ c.device }}</span>
        </p>
        <p class="comment-content">{{ c.content }}</p>
        <button class="comment-reply-btn" type="button" @click="startReply(c)">回复</button>
      </div>

      <div v-if="repliesOf(c.id).length" class="comment-replies">
        <div v-for="r in repliesOf(c.id)" :key="r.id" class="comment reply">
          <p class="comment-meta">
            {{ r.author }}
            <span v-if="r.reply_to" class="reply-to">回复 @{{ r.reply_to }}</span>
            · {{ (r.created_at || "").slice(0, 16) }}
          </p>
          <p class="comment-meta" v-if="r.region || r.device">
            <span v-if="r.region">📍 {{ r.region }}</span>
            <span v-if="r.device">{{ r.region ? " · " : "" }}{{ r.device }}</span>
          </p>
          <p class="comment-content">{{ r.content }}</p>
          <button class="comment-reply-btn" type="button" @click="startReply(r)">回复</button>
        </div>
      </div>
    </div>

    <!-- 发表 / 回复表单 -->
    <form class="comment-form" autocomplete="off" @submit.prevent="submit">
      <p v-if="replyingTo" class="replying-tip">
        回复 @{{ replyingTo.author }}
        <button type="button" class="reply-cancel" @click="cancelReply">取消</button>
      </p>
      <input v-if="!state.user" type="text" v-model="author" placeholder="昵称（必填，2-20 字）" maxlength="20" required />
      <textarea v-model="content" placeholder="说点什么…（必填，2-500 字）" maxlength="500" required></textarea>
      <!-- v3.1.6 可选增强：评论验证码 -->
      <div v-if="captchaEnabled" class="captcha-row">
        <input type="text" v-model="captcha" placeholder="验证码（不区分大小写）" maxlength="4" required />
        <img :src="captchaUrl" alt="验证码" class="captcha-img" @click="refreshCaptcha" title="点击刷新" />
      </div>
      <div>
        <button type="submit">提交{{ replyingTo ? "回复" : "评论" }}</button>
        <span class="comment-status" :class="statusClass" style="margin-left: 10px;">{{ status }}</span>
      </div>
    </form>
  </section>
</template>

<script setup>
import { ref, computed } from "vue";
import { apiGet, apiPost } from "../lib/api.js";
import { state } from "../store.js";

const props = defineProps({ slug: String, comments: Array });
const author = ref("");
const content = ref("");
const status = ref("");
const statusClass = ref("");
const replyingTo = ref(null);
const captcha = ref("");
const captchaEnabled = ref(true);
const captchaUrl = ref("");

// v3.1.6 可选增强：评论验证码（CAPTCHA_ENABLED；后端/PIL 不可用时会返回降级关闭）
function refreshCaptcha() {
  captchaUrl.value = "/api/captcha?" + Date.now() + "&from=comment";
}
async function initCaptcha() {
  // v3.2.0：读取后台验证码配置，按「评论」场景显隐
  try {
    const cfg = await apiGet("/api/captcha/config");
    const ok = cfg && cfg.enabled && cfg.available && cfg.scenes && cfg.scenes.comment;
    if (ok) {
      captchaEnabled.value = true;
      refreshCaptcha();
    } else {
      captchaEnabled.value = false;
    }
  } catch (e) {
    captchaEnabled.value = false;
  }
}
initCaptcha();

const topComments = computed(() => (props.comments || []).filter((c) => !c.parent_id));
function repliesOf(id) {
  return (props.comments || []).filter((c) => c.parent_id === id);
}
const allCount = computed(() => (props.comments || []).length);

function startReply(c) {
  replyingTo.value = { id: c.id, author: c.author };
  content.value = "";
}
function cancelReply() {
  replyingTo.value = null;
  content.value = "";
}

async function submit() {
  if (!content.value.trim()) { status.value = "评论内容不能为空"; statusClass.value = "error"; return; }
  if (!state.user && !author.value.trim()) { status.value = "请填写昵称"; statusClass.value = "error"; return; }
  const body = { content: content.value.trim() };
  // 已登录（含超级管理员/管理员/普通用户）：昵称由后端从会话取，不需要前端传
  if (!state.user) body.author = author.value.trim();
  if (replyingTo.value) {
    body.parent_id = replyingTo.value.id;
    body.reply_to = replyingTo.value.author;
  }
  if (captchaEnabled.value) body.captcha = captcha.value.trim();
  status.value = "提交中…";
  statusClass.value = "";
  try {
    const d = await apiPost(`/api/post/${props.slug}/comment`, body);
    status.value = d.pending ? "评论已提交，待管理员审核后将显示" : "评论成功！";
    statusClass.value = "success";
    content.value = "";
    replyingTo.value = null;
    setTimeout(() => window.location.reload(), 600);
  } catch (e) {
    status.value = e.message || "网络错误";
    statusClass.value = "error";
    if (captchaEnabled.value) refreshCaptcha();
  }
}
</script>
