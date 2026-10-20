<template>
  <div class="container">
    <h1 class="page-title">友情链接</h1>
    <p v-if="!links.length" class="empty">还没有友链。</p>
    <ul v-else class="friend-links">
      <li v-for="l in links" :key="l.url">
        <a :href="l.url" target="_blank" rel="noopener">{{ l.name }}</a>
        <div v-if="l.description" class="desc">{{ l.description }}</div>
      </li>
    </ul>

    <!-- v4.8.0 谁在用 llhhy-blog：只展示「使用者自己登记 + 管理员审核」的站点。
         刻意不写成「在线实例数」：开源部署跑在各自服务器上，本端拿不到，也不做主动上报。
         类名复用 .link-apply-box / .friend-links（本页无 scoped 样式，靠 global.css）。 -->
    <div class="link-apply-box adopters-box">
      <h3>🛠 谁在用 llhhy-blog</h3>
      <p class="sub-tip">
        以下站点由使用者<b>自行登记</b>、管理员审核后展示，是「已知公开实例」的样本，<b>不是</b>全部使用者。
        本站不统计也无法统计有多少人部署了它（开源部署对服务端不可见，程序里也没有内置上报）。
        如果你也在用，在下方申请友链时勾选「我也在用 llhhy-blog」即可。
      </p>
      <ul v-if="adopters.sites.length" class="friend-links">
        <li v-for="a in adopters.sites" :key="a.url">
          <a :href="a.url" target="_blank" rel="noopener">{{ a.name }}</a>
          <div v-if="a.description" class="desc">{{ a.description }}</div>
        </li>
      </ul>
      <p v-else class="sub-tip">还没有人登记。</p>
      <p v-if="adopters.repo" class="repo-line">
        仓库客观数据（截至 {{ adopters.repo.refreshed_at }}）：★ {{ adopters.repo.stars }} ·
        fork {{ adopters.repo.forks }} · Release 下载 {{ adopters.repo.release_downloads }}
        <span class="desc">—— 这三项量的是「被拿走」的多少，与「部署上线了多少站」不是一回事。</span>
      </p>
    </div>

    <!-- 自助申请友链（v3.0.0 功能6） -->
    <div class="link-apply-box">
      <h3>🔗 申请交换友链</h3>
      <p class="sub-tip">填写你的站点信息，管理员审核通过后会展示在上方。请勿提交违规或垃圾站点。</p>
      <form class="link-apply-form" @submit.prevent="submitApply">
        <input type="text" v-model="form.name" placeholder="你的站点名称 *" required />
        <input type="url" v-model="form.url" placeholder="站点链接（http/https）*" required />
        <input type="text" v-model="form.description" placeholder="一句话描述（可选）" />
        <input type="email" v-model="form.email" placeholder="联系邮箱（可选）" />
        <label class="repo-line"><input type="checkbox" v-model="form.uses_llhhy" /> 我也在用 llhhy-blog（登记进上方列表）</label>
        <button type="submit" :disabled="applyBusy">{{ applyBusy ? "提交中…" : "提交申请" }}</button>
      </form>
      <p v-if="applyMsg" class="apply-msg" :class="applyOk ? 'ok' : 'err'">{{ applyMsg }}</p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet, apiPost } from "../lib/api.js";

const links = ref([]);
const adopters = ref({ sites: [], repo: null });
const form = ref({ name: "", url: "", description: "", email: "", uses_llhhy: false });
const applyBusy = ref(false);
const applyMsg = ref("");
const applyOk = ref(false);

onMounted(async () => {
  try { links.value = await apiGet("/api/links"); } catch (e) { links.value = []; }
  // 登记列表与仓库指标都来自 /api/adopters（后者只是缓存，接口本身不出网）。
  // 拉不到就留空数组：这块区域没有「假数字」可显示，宁缺毋假。
  try {
    const d = await apiGet("/api/adopters");
    adopters.value = { sites: (d && d.sites) || [], repo: (d && d.repo) || null };
  } catch (e) { adopters.value = { sites: [], repo: null }; }
});

async function submitApply() {
  if (!form.value.name.trim() || !form.value.url.trim()) {
    applyMsg.value = "请填写站点名称和链接"; applyOk.value = false; return;
  }
  applyBusy.value = true; applyMsg.value = "";
  try {
    const d = await apiPost("/api/link-apply", { ...form.value });
    applyOk.value = true;
    applyMsg.value = d.message || "申请已提交";
    form.value = { name: "", url: "", description: "", email: "", uses_llhhy: false };
  } catch (e) {
    applyOk.value = false;
    applyMsg.value = e.message || "提交失败，请稍后再试";
  } finally {
    applyBusy.value = false;
  }
}
</script>
