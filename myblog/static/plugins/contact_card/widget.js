/*
 * 联系卡片 · 远程预构建组件（v3.9.0 M3 demo）。
 *
 * 安全约束（详见 PLUGIN_SYSTEM.md M3）：
 * - 仅允许同源 /static/plugins/<slug>/ 下的预构建 JS（由后端 /api/plugins 白名单校验前缀）。
 * - 不使用字符串 template（运行时仅 runtime-only Vue，无编译器），统一用 h() 渲染函数。
 * - 本文件由插件自带、随发版走，等同插件代码信任级别（只装自写/审计过的插件）。
 *
 * 加载机制：前端注入 <script src=本文件> 后，调用 window.__pluginRegister(name, def)
 * 把组件定义交给 Vue 全局注册（定义在 App.vue）。
 */
(function () {
  var h = window.__vueH;
  var register = window.__pluginRegister;
  if (typeof h !== "function" || typeof register !== "function") {
    console.warn("[contact_card_widget] Vue 运行时不就绪，跳过注册");
    return;
  }
  register("contact_card_widget", {
    name: "ContactCardWidget",
    props: {
      href: { type: String, default: "/plugin/contact_card" }
    },
    render: function () {
      return h(
        "a",
        {
          class: "plugin-remote-badge",
          href: this.href,
          target: "_blank",
          rel: "noopener"
        },
        "📮 联系"
      );
    }
  });
})();
