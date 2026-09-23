<template>
  <div class="container">
    <div class="auth-box">
      <h1 class="page-title">登录</h1>
      <!-- v3.21.0 2FA：第一步通过后切换为「输入动态码」，不再显示账号密码表单 -->
      <form v-if="twofaStep" class="comment-form" @submit.prevent="submit2fa">
        <p class="auth-tip">此账号已启用两步验证，请输入验证器 App 显示的 6 位动态码（或恢复码）。</p>
        <input type="text" v-model="twofaCode" placeholder="6 位动态码 / 恢复码"
               inputmode="numeric" autocomplete="one-time-code" maxlength="64" required autofocus />
        <div>
          <button type="submit">验证并登录</button>
          <button type="button" class="oauth-btn" style="margin-left:8px;width:auto;display:inline-block;"
                  @click="cancel2fa">取消</button>
          <span class="comment-status" :class="statusClass" style="margin-left: 10px;">{{ status }}</span>
        </div>
      </form>

      <form v-else class="comment-form" @submit.prevent="submit">
        <input type="text" v-model="username" placeholder="用户名" required autofocus />
        <input type="password" v-model="password" placeholder="密码" required />
        <div>
          <button type="submit">登录</button>
          <span class="comment-status" :class="statusClass" style="margin-left: 10px;">{{ status }}</span>
        </div>
      </form>
      <p v-if="state.user" class="auth-tip" style="color: var(--accent);">
        ✅ 已登录：{{ state.user.username }}（{{ state.user.role_label }}）
      </p>
      <p class="auth-tip">还没有账号？<router-link to="/register">注册一个</router-link></p>
      <p class="auth-tip" v-if="state.user">
        快捷入口：<a :href="state.user.is_admin ? '/admin' : '/admin/post/new'">进入写作后台 →</a>
      </p>

      <!-- v3.21.0 OAuth 第三方登录：仅当后端已配置对应 provider 才显示按钮 -->
      <div class="oauth-box" v-if="state.oauthProviders.length && !twofaStep">
        <div class="oauth-divider"><span>或</span></div>
        <button
          v-for="p in state.oauthProviders"
          :key="p"
          type="button"
          class="oauth-btn"
          :class="'oauth-' + p"
          :disabled="oauthBusy"
          @click="startOAuthLogin(p)"
        >{{ oauthLabel(p) }}</button>
        <span class="comment-status" v-if="oauthBusy">{{ t('oauth_being_redirected') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { login, verify2fa, state, t, initOAuthProviders, startOAuth } from "../store.js";

const route = useRoute();
const router = useRouter();
const username = ref("");
const password = ref("");
const status = ref("");
const statusClass = ref("");
const oauthBusy = ref(false);
// v3.21.0 2FA：第一步通过后进入第二步骤（输入动态码/恢复码）
const twofaStep = ref(false);
const twofaCode = ref("");

onMounted(() => { initOAuthProviders(); });

function goAfterLogin(user) {
  // 登录成功：按来源与角色分流
  // - 带了合法的 next（非后台首页）→ 优先跳过去（后端会再校验权限）
  // - 管理员 → 仪表盘
  // - 普通用户 → 写作区（写文章）
  const next = route.query.next || "";
  if (next && next.startsWith("/") && !next.startsWith("//") && !(next === "/admin" || next === "/admin/")) {
    router.push(next);
  } else if (user.is_admin) {
    router.push("/admin");
  } else {
    router.push("/admin/post/new");
  }
}

async function submit() {
  status.value = "登录中…";
  statusClass.value = "";
  try {
    const user = await login(username.value.trim(), password.value);
    if (user && user.twofa_required) {
      // 第一步通过但需二次验证：停留本页等待动态码
      twofaStep.value = true;
      status.value = "请输入验证器 App 的 6 位动态码";
      statusClass.value = "";
      return;
    }
    goAfterLogin(user);
  } catch (e) {
    status.value = e.message || "登录失败";
    statusClass.value = "error";
  }
}

async function submit2fa() {
  status.value = "验证中…";
  statusClass.value = "";
  try {
    const user = await verify2fa(twofaCode.value.trim());
    twofaStep.value = false;
    goAfterLogin(user);
  } catch (e) {
    status.value = e.message || "验证失败";
    statusClass.value = "error";
  }
}

function cancel2fa() {
  twofaStep.value = false;
  twofaCode.value = "";
  status.value = "";
  statusClass.value = "";
}

function oauthLabel(p) {
  if (p === "github") return t("login_github");
  if (p === "google") return t("login_google");
  return "Sign in with " + p;
}

async function startOAuthLogin(p) {
  oauthBusy.value = true;
  try {
    await startOAuth(p);  // 成功会整页跳转，此函数不返回
  } catch (e) {
    oauthBusy.value = false;
    status.value = e.message || "第三方登录启动失败";
    statusClass.value = "error";
  }
}
</script>

<style scoped>
.oauth-box { margin-top: 18px; padding-top: 14px; border-top: 1px dashed var(--border); }
.oauth-divider {
  position: relative; text-align: center; margin: 10px 0 12px;
}
.oauth-divider::before {
  content: ""; position: absolute; left: 0; right: 0; top: 50%;
  border-top: 1px solid var(--border);
}
.oauth-divider span {
  position: relative; background: var(--bg); padding: 0 10px;
  font-size: 12px; color: var(--text-muted);
}
.oauth-btn {
  display: block; width: 100%; margin-bottom: 8px;
  padding: 9px 14px; border-radius: var(--theme-radius, 12px);
  border: 1px solid var(--border-strong, var(--border));
  background: var(--surface); color: var(--text);
  font-size: 14px; cursor: pointer; transition: border-color .15s, opacity .15s;
}
.oauth-btn:hover:not(:disabled) { border-color: var(--accent); }
.oauth-btn:disabled { opacity: .6; cursor: not-allowed; }
.oauth-github { font-weight: 600; }
.oauth-google { font-weight: 600; }
</style>
