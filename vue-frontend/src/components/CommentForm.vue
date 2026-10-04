<template>
  <section class="comments" id="comments">
    <h2>评论 ({{ allCount }})</h2>
    <div v-if="!loaded.length" class="comment-empty">还没有评论，来沙发？</div>

    <!-- v3.25.2：排序切换。评论排序是读者诉求（想看最新讨论 vs 想看热门），
         旧版只有「正序」一种，且不可切换。 -->
    <div v-if="loaded.length" class="comment-sortbar">
      <span class="comment-sortbar-label">排序</span>
      <button v-for="s in SORTS" :key="s.key" type="button" class="comment-sort-btn"
              :class="{ active: sort === s.key }" @click="switchSort(s.key)">{{ s.label }}</button>
    </div>

    <!-- v3.25.2：扁平渲染 + depth 缩进（后端返回深度优先顺序，天然正确）。
         旧版是「顶层 + repliesOf(id)」两层硬编码，渲染不了三层及更深 ——
         而后端此前也只返回两层，于是「回复的回复」从来就没显示过。 -->
    <div v-for="c in visibleItems" :key="c.id" class="comment"
         :class="c.depth ? 'reply' : ''" :style="{ marginLeft: indentOf(c.depth) + 'px' }">
      <p class="comment-meta">
        <img v-if="c.avatar" :src="c.avatar" class="comment-avatar" alt="" />{{ c.author }}
        <span v-if="c.reply_to" class="reply-to">回复 @{{ c.reply_to }}</span>
        · {{ (c.created_at || "").slice(0, 16) }}
      </p>
      <p class="comment-meta" v-if="c.region || c.device">
        <span v-if="c.region">📍 {{ c.region }}</span>
        <span v-if="c.device">{{ c.region ? " · " : "" }}{{ c.device }}</span>
      </p>
      <p class="comment-content">{{ c.content }}</p>
      <div class="comment-foot">
        <button class="comment-reply-btn" type="button" @click="startReply(c)">回复</button>
        <div class="comment-react">
          <button v-for="e in reactAllowed" :key="e" type="button" class="react-btn"
                  :class="{ active: isMine(c.id, e) }" :title="'回应 ' + e"
                  @click="react(c, e)">{{ e }}<em v-if="countOf(c.id, e)">{{ countOf(c.id, e) }}</em></button>
        </div>
      </div>
    </div>

    <!-- 深度封顶：折叠而非丢弃。数据一直在（后端全量返回），只是默认不展开。 -->
    <button v-if="hiddenCount && !showAllDepth" type="button" class="load-more"
            @click="showAllDepth = true">展开剩余 {{ hiddenCount }} 条深层讨论 ↓</button>
    <button v-else-if="showAllDepth && hiddenCount" type="button" class="load-more"
            @click="showAllDepth = false">收起深层讨论 ↑</button>

    <!-- 评论分页（UI清单 10.1）：加载更多 -->
    <p v-if="slug && loadingMore" class="comment-loading">评论加载中…</p>
    <button v-else-if="slug && hasMore" type="button" class="load-more" @click="loadMore">加载更多评论 ↓</button>
    <p v-if="slug && moreError" class="comment-error">{{ moreError }}</p>

    <!-- 发表 / 回复表单 -->
    <form class="comment-form" autocomplete="off" @submit.prevent="submit">
      <p v-if="replyingTo" class="replying-tip">
        回复 @{{ replyingTo.author }}
        <button type="button" class="reply-cancel" @click="cancelReply">取消</button>
      </p>
      <input v-if="!state.user" type="text" v-model="author" placeholder="昵称（必填，2-20 字）" maxlength="20" required />
      <input type="email" v-model="email" placeholder="邮箱（仅用于头像，不会公开）" maxlength="120" :required="emailRequired" />
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
import { ref, computed, onMounted } from "vue";
import { apiGet, apiPost } from "../lib/api.js";
import { toastErr } from "../lib/toast.js";
import { state } from "../store.js";

const props = defineProps({ slug: String, comments: { type: Array, default: () => [] } });
const author = ref("");
const email = ref("");
const emailRequired = ref(false);
const content = ref("");
const status = ref("");
const statusClass = ref("");
const replyingTo = ref(null);
const captcha = ref("");
const captchaEnabled = ref(true);
const captchaUrl = ref("");
// 评论分页（UI清单 10.1）：slug 存在时自取首屏 + 「加载更多」；否则沿用传入的 comments
const loaded = ref(props.comments ? [...props.comments] : []);
const total = ref((props.comments || []).length);
const page = ref(1);
const perPage = 20;
const hasMore = ref(false);
const loadingMore = ref(false);
const moreError = ref("");

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

// v3.15.3 功能1：读取评论配置（邮箱是否必填）
async function initCommentConfig() {
  try {
    const cfg = await apiGet("/api/comment/config");
    emailRequired.value = !!cfg.email_required;
  } catch (e) {
    emailRequired.value = false;
  }
}
initCommentConfig();

// v3.25.2：`topComments` / `repliesOf` 两层结构已退役（见下方注释），
// 「还没有评论」的空态判断改用 `loaded`。
const allCount = computed(() => total.value || loaded.value.length);

// ===== v3.25.2：排序切换 + 深度封顶 =====
// 后端从 v3.25.2 起返回**任意层**嵌套（此前只两层，回复的回复被静默丢弃），
// 且 items 已是「深度优先」顺序。旧的 `topComments / repliesOf` 两层结构
// 渲染不了三层及更深 —— 于是这里改用**扁平列表 + depth 缩进**：
// 顺序天然正确（后端就是深度优先给的），任意层都能渲染，代码也更短。
//
// `maxDepth` 只控制**显示到第几层**，绝不丢弃数据：更深的内容折叠在
// 「展开剩余 N 条讨论」按钮里。把裁剪做在后端等于把「丢评论」从三层挪到四层。

const SORTS = [
  { key: "old", label: "正序" },
  { key: "new", label: "倒序" },
  { key: "hot", label: "最热" },
];
const MAX_DEPTH = 4;          // 展示层数；更深的折叠
const showAllDepth = ref(false);
const sort = ref("old");

const maxDepth = computed(() => showAllDepth.value ? 99 : MAX_DEPTH);
// 缩进：超过 3 层后不再继续加 padding，否则窄屏会被挤成一条线
function indentOf(d) {
  return Math.min(d || 0, 3) * 18;
}
const visibleItems = computed(() =>
  (loaded.value || []).filter((c) => (c.depth || 0) <= maxDepth.value)
);
const hiddenCount = computed(() =>
  (loaded.value || []).filter((c) => (c.depth || 0) > maxDepth.value).length
);

function switchSort(k) {
  if (k === sort.value) return;
  sort.value = k;
  showAllDepth.value = false;
  reloadFromFirstPage();
}

async function loadPage(p) {
  if (!props.slug) return;
  loadingMore.value = true;
  moreError.value = "";
  try {
    const d = await apiGet(
      `/api/post/${encodeURIComponent(props.slug)}/comments` +
      `?page=${p}&per_page=${perPage}&sort=${encodeURIComponent(sort.value)}`
    );
    if (p === 1) loaded.value = [];          // 换排序 = 换一批数据，旧数据必须清
    loaded.value.push(...(d.items || []));
    total.value = d.total || loaded.value.length;
    hasMore.value = !!d.has_more;
    page.value = p;
    loadReacts();
  } catch (e) {
    moreError.value = "评论加载失败";
  } finally {
    loadingMore.value = false;
  }
}
function reloadFromFirstPage() { page.value = 1; loadPage(1); }
function loadMore() { loadPage(page.value + 1); }
onMounted(() => {
  if (props.slug) { loaded.value = []; total.value = 0; page.value = 1; loadPage(1); }
});

// v3.17.3：评论表情回应（👍❤️😂🎉🤔👏；计数存后端 Setting KV，本机选择存 localStorage）
const reactAllowed = ref(["👍", "❤️", "😂", "🎉", "🤔", "👏"]);
const reacts = ref({});   // { cid: { emoji: n } }
const mine = ref({});     // { cid: [emoji] } 本机已点过的（仅前端去重，非强校验）
function mineKey() { return "reacts_" + (props.slug || ""); }
function loadMine() {
  try {
    const raw = localStorage.getItem(mineKey());
    mine.value = raw ? (JSON.parse(raw) || {}) : {};
  } catch (e) { mine.value = {}; }
}
function saveMine() {
  try { localStorage.setItem(mineKey(), JSON.stringify(mine.value)); } catch (e) {}
}
function countOf(cid, e) {
  const m = reacts.value[cid] || reacts.value[String(cid)] || {};
  return m[e] || 0;
}
function isMine(cid, e) {
  const arr = mine.value[cid] || mine.value[String(cid)] || [];
  return arr.indexOf(e) >= 0;
}
async function loadReacts() {
  const ids = loaded.value.map((c) => c.id).filter(Boolean);
  if (!ids.length) return;
  try {
    const d = await apiGet("/api/comments/reactions?ids=" + ids.join(","));
    if (d && d.allowed && d.allowed.length) reactAllowed.value = d.allowed;
    if (d && d.items) {
      const merged = { ...reacts.value };
      Object.keys(d.items).forEach((k) => { merged[k] = d.items[k]; });
      reacts.value = merged;
    }
  } catch (e) {}
}
async function react(c, e) {
  const cid = c.id;
  const on = isMine(cid, e);
  const action = on ? "remove" : "add";
  // 乐观更新
  const cur = { ...(reacts.value[cid] || {}) };
  const n = Math.max(0, (cur[e] || 0) + (on ? -1 : 1));
  if (n) cur[e] = n; else delete cur[e];
  reacts.value = { ...reacts.value, [cid]: cur };
  const arr = (mine.value[cid] || []).slice();
  if (on) { const i = arr.indexOf(e); if (i >= 0) arr.splice(i, 1); } else arr.push(e);
  mine.value = { ...mine.value, [cid]: arr };
  saveMine();
  try {
    const d = await apiPost(`/api/comments/${cid}/reactions`, { emoji: e, action });
    if (d && d.counts) reacts.value = { ...reacts.value, [cid]: d.counts };
  } catch (err) {
    // 失败回滚本地计数
    const back = { ...(reacts.value[cid] || {}) };
    const b = Math.max(0, (back[e] || 0) + (on ? 1 : -1));
    if (b) back[e] = b; else delete back[e];
    reacts.value = { ...reacts.value, [cid]: back };
    toastErr(err.message || "操作失败");
  }
}
loadMine();

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
  if (email.value.trim()) body.email = email.value.trim();
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

<style scoped>
.comment-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  vertical-align: middle;
  margin-right: 8px;
  object-fit: cover;
}

/* v3.17.3 表情回应条 */
.comment-foot { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.comment-react { display: flex; gap: 4px; flex-wrap: wrap; }
.react-btn {
  border: 1px solid var(--border, #e3e6ea); background: var(--surface, #fff);
  border-radius: 999px; padding: 2px 8px; font-size: 13px; line-height: 1.6;
  cursor: pointer; color: inherit;
  transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
}
.react-btn em { font-style: normal; font-size: 11px; color: var(--text-muted, #6b7280); margin-left: 3px; }
.react-btn:hover { transform: translateY(-1px); border-color: var(--accent, #1a73e8); }
.react-btn.active { border-color: var(--accent, #1a73e8); background: var(--accent-soft, rgba(26, 115, 232, .1)); }

/* ===== v3.25.2：排序切换条 ===== */
/* 颜色全部走 token —— 上一轮刚治理完深色模式对比度，这里**不能再写死颜色**，
   否则深色下又会重演「容器停在亮色、文字翻浅」那类缺陷。
   v3.25.1 的新守卫（test_dark_mode_no_light_text_on_light_background 等）也
   会扫 global.css；本段是 scoped，不在其射程内，故更要自己守规矩。 */
.comment-sortbar {
  display: flex; align-items: center; gap: 8px;
  margin: 4px 0 14px; font-size: 13px;
}
.comment-sortbar-label { color: var(--text-muted, #6b7280); }
.comment-sort-btn {
  padding: 3px 12px; font-size: 13px; cursor: pointer;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 999px;
  background: var(--surface, #fff);
  color: var(--text-muted, #6b7280);
  transition: border-color 120ms ease, color 120ms ease, background 120ms ease;
}
.comment-sort-btn:hover { border-color: var(--accent, #1a73e8); color: var(--accent, #1a73e8); }
.comment-sort-btn.active {
  border-color: var(--accent, #1a73e8);
  background: var(--accent-soft, rgba(26, 115, 232, .1));
  color: var(--accent, #1a73e8); font-weight: 500;
}
</style>
