<template>
  <div class="layout">
    <main class="content">
      <h1 class="page-title">广场 · 社交聚合</h1>

      <!-- 标签切换 -->
      <div class="sq-tabs">
        <button :class="['sq-tab', { active: tab === 'all' }]" @click="tab = 'all'">全部</button>
        <button :class="['sq-tab', { active: tab === 'moments' }]" @click="tab = 'moments'">我的动态</button>
        <button :class="['sq-tab', { active: tab === 'circle' }]" @click="tab = 'circle'">博客圈</button>
        <button :class="['sq-tab', { active: tab === 'follow' }]" @click="tab = 'follow'">关注</button>
      </div>

      <!-- 发布动态（仅登录用户，在「全部/我的动态」下显示） -->
      <div v-if="state.user && (tab === 'all' || tab === 'moments')" class="sq-composer post-card">
        <div class="sq-composer-head">
          <div class="avatar">{{ (state.user.username[0] || '我') }}</div>
          <textarea v-model="draft" maxlength="500" placeholder="分享一条动态、随手记或心情…（最多 500 字）"></textarea>
        </div>
        <div class="sq-composer-foot">
          <span class="sq-count">{{ draft.length }}/500</span>
          <button type="button" :disabled="posting || !draft.trim()" @click="postMoment">发布</button>
        </div>
      </div>

      <!-- 全部 / 我的动态：微动态流 -->
      <template v-if="tab === 'all' || tab === 'moments'">
        <p v-if="!moments.length && !loadingM" class="empty">还没有动态，来发第一条吧。</p>
        <article v-for="m in moments" :key="'m' + m.id" class="post-card sq-moment">
          <div class="sq-moment-head">
            <div class="avatar sm">{{ (m.author[0] || '?') }}</div>
            <div>
              <div class="sq-moment-author">{{ m.author }}</div>
              <div class="post-meta">{{ (m.created_at || '').slice(0, 16) }}</div>
            </div>
          </div>
          <p class="sq-moment-content">{{ m.content }}</p>
          <div class="sq-moment-actions">
            <button type="button" class="sq-like" @click="likeMoment(m)">赞 {{ m.likes }}</button>
            <button type="button" class="sq-like" @click="toggleComments(m)">评论 {{ m.comments.length }}</button>
          </div>
          <div v-if="m._showComments" class="sq-comments">
            <div v-for="c in m.comments" :key="c.id" class="sq-comment">
              <span class="sq-comment-author">{{ c.author }}</span>
              <span class="sq-comment-text">{{ c.content }}</span>
              <span class="post-meta">{{ (c.created_at || '').slice(0, 16) }}</span>
            </div>
            <form class="sq-comment-form" @submit.prevent="addComment(m)">
              <input v-if="!state.user" v-model="m._author" placeholder="昵称" maxlength="20" required />
              <input v-model="m._text" placeholder="说点什么…" maxlength="300" required />
              <button type="submit">发送</button>
            </form>
          </div>
        </article>
      </template>

      <!-- 博客圈：友链 RSS 聚合 -->
      <template v-if="tab === 'all' || tab === 'circle'">
        <div v-if="tab === 'circle'" class="sq-circle-head">
          <button type="button" class="sq-refresh" :disabled="loadingC" @click="loadCircle(true)">↻ 刷新聚合</button>
        </div>
        <p v-if="tab === 'circle' && !circle.length && !loadingC" class="empty">还没有可聚合的友链 RSS，去后台给友链填上 RSS 地址吧。</p>
        <article v-for="(it, i) in circle" :key="'c' + i" class="post-card sq-circle">
          <div class="sq-circle-badge">博客圈 · 来自 <a :href="it.source_url" target="_blank" rel="noopener">{{ it.source }}</a></div>
          <a class="sq-circle-title" :href="it.url" target="_blank" rel="noopener">{{ it.title }}</a>
          <p v-if="it.summary" class="sq-circle-summary" v-html="it.summary"></p>
          <div class="post-meta">{{ (it.published_at || '').slice(0, 16) }}</div>
        </article>
      </template>

      <!-- 关注：社交账号墙 -->
      <template v-if="tab === 'follow'">
        <p v-if="!accounts.length" class="empty">还没有添加社交账号，去后台「社交账号」里添加吧。</p>
        <div class="sq-accounts">
          <a v-for="a in accounts" :key="a.id" class="sq-account post-card" :href="a.url" target="_blank" rel="noopener">
            <div class="sq-account-platform">{{ a.platform }}</div>
            <div class="sq-account-handle">{{ a.handle || a.url }}</div>
            <span class="sq-account-go">前往 →</span>
          </a>
        </div>
      </template>
    </main>

    <Sidebar />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { apiGet, apiPost } from "../lib/api.js";
import { state } from "../store.js";
import Sidebar from "../components/Sidebar.vue";

const tab = ref("all");
const moments = ref([]);
const circle = ref([]);
const accounts = ref([]);
const draft = ref("");
const posting = ref(false);
const loadingM = ref(false);
const loadingC = ref(false);

async function loadMoments() {
  loadingM.value = true;
  try {
    const d = await apiGet("/api/moments");
    moments.value = (d.items || []).map((m) => ({ ...m, _showComments: false, _author: "", _text: "" }));
  } catch (e) { moments.value = []; }
  loadingM.value = false;
}

async function loadCircle(force) {
  loadingC.value = true;
  try {
    const d = await apiGet("/api/feed/circle" + (force ? "?refresh=1" : ""));
    circle.value = d.items || [];
  } catch (e) { circle.value = []; }
  loadingC.value = false;
}

async function loadAccounts() {
  try {
    accounts.value = await apiGet("/api/social-accounts");
  } catch (e) { accounts.value = []; }
}

async function postMoment() {
  if (!draft.value.trim() || posting.value) return;
  posting.value = true;
  try {
    await apiPost("/api/moment", { content: draft.value.trim() });
    draft.value = "";
    await loadMoments();
  } catch (e) { alert(e.message || "发布失败"); }
  posting.value = false;
}

async function likeMoment(m) {
  try {
    const d = await apiPost(`/api/moment/${m.id}/like`, {});
    m.likes = d.likes;
  } catch (e) {}
}

function toggleComments(m) { m._showComments = !m._showComments; }

async function addComment(m) {
  const text = (m._text || "").trim();
  if (!text) return;
  const body = { content: text };
  if (!state.user) {
    if (!m._author || !m._author.trim()) { alert("请填写昵称"); return; }
    body.author = m._author.trim();
  }
  try {
    const d = await apiPost(`/api/moment/${m.id}/comment`, body);
    m.comments.push(d.comment);
    m._text = "";
  } catch (e) { alert(e.message || "评论失败"); }
}

// 切换标签时按需加载（避免无谓请求）
watch(tab, (t) => {
  if ((t === "all" || t === "moments") && !moments.value.length) loadMoments();
  if ((t === "all" || t === "circle") && !circle.value.length) loadCircle();
  if (t === "follow" && !accounts.value.length) loadAccounts();
});

onMounted(() => {
  loadMoments();
  loadCircle();
  loadAccounts();
});
</script>

<style scoped>
.sq-tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.sq-tab { padding: 6px 16px; border: 1px solid #ddd; background: #fff; border-radius: 999px; cursor: pointer; font-size: 14px; color: #555; }
.sq-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.sq-composer { margin-bottom: 16px; }
.sq-composer-head { display: flex; gap: 12px; align-items: flex-start; }
.sq-composer-head textarea { flex: 1; min-height: 64px; }
.sq-composer-foot { display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin-top: 10px; }
.sq-count { font-size: 12px; color: #999; }
.avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--accent); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 500; flex-shrink: 0; }
.avatar.sm { width: 34px; height: 34px; font-size: 14px; }
.sq-moment-head { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
.sq-moment-author { font-size: 14px; font-weight: 500; }
.sq-moment-content { font-size: 15px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.sq-moment-actions { display: flex; gap: 16px; margin-top: 10px; }
.sq-like { background: none; border: none; color: #888; cursor: pointer; font-size: 13px; padding: 0; }
.sq-like:hover { color: var(--accent); }
.sq-comments { margin-top: 12px; border-top: 1px solid #f0f0f0; padding-top: 12px; }
.sq-comment { font-size: 13px; padding: 5px 0; color: #444; }
.sq-comment-author { color: var(--accent); margin-right: 6px; font-weight: 500; }
.sq-comment-text { margin-right: 6px; }
.sq-comment-form { display: flex; gap: 8px; margin-top: 10px; }
.sq-comment-form input { flex: 1; }
.sq-circle-badge { font-size: 12px; color: #999; margin-bottom: 6px; }
.sq-circle-badge a { color: var(--accent); text-decoration: none; }
.sq-circle-title { display: block; font-size: 17px; font-weight: 600; color: #1f1f1f; text-decoration: none; }
.sq-circle-title:hover { color: var(--accent); }
.sq-circle-summary { font-size: 14px; color: #666; margin: 6px 0; }
.sq-circle-summary :deep(img) { max-width: 100%; height: auto; }
.sq-accounts { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 14px; }
.sq-account { text-decoration: none; color: inherit; display: flex; flex-direction: column; gap: 4px; }
.sq-account-platform { font-size: 15px; font-weight: 600; color: var(--accent); }
.sq-account-handle { font-size: 13px; color: #666; word-break: break-all; }
.sq-account-go { font-size: 13px; color: #999; margin-top: 4px; }
.sq-circle-head { margin-bottom: 12px; }
.sq-refresh { padding: 6px 14px; border: 1px solid var(--accent); background: #fff; color: var(--accent); border-radius: 6px; cursor: pointer; font-size: 13px; }
.sq-refresh:hover { background: var(--accent); color: #fff; }
.sq-refresh:disabled { opacity: .6; cursor: default; }
[data-theme="dark"] .sq-refresh { background: #1d2025; border-color: #2a2e35; }
[data-theme="dark"] .sq-tab { background: #1d2025; border-color: #2a2e35; color: #c7ccd1; }
[data-theme="dark"] .sq-moment-content, [data-theme="dark"] .sq-comment { color: #d7d9dc; }
[data-theme="dark"] .sq-comments { border-color: #2a2e35; }
</style>
