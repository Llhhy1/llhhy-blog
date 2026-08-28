/*
 * 文章目录（TOC）侧栏 · 远程预构建组件（v3.9.0 · 首个真实插件）。
 *
 * 安全约束（同 M3 远程组件）：
 * - 仅允许同源 /static/plugins/article_toc/ 下的预构建 JS（后端 /api/plugins 白名单校验前缀）。
 * - 本文件随发版走，等同插件代码信任级别（只装自写/审计过的插件）。
 *
 * 行为：
 * - 扫描文章正文 .post-body 的 h2/h3/h4，自动生成带锚点的目录。
 * - 以 sticky 形态注入文章页右侧 .sidebar 顶部：桌面常驻、随滚动跟随。
 * - 滚动高亮当前章节（scroll-spy）；点击平滑滚动到对应标题（带 scroll-margin-top 防被固定头部遮挡）。
 * - 监听 SPA 路由切换 / 异步加载（MutationObserver），自动重建；非文章页自动隐藏。
 * - 窄屏（<=820px）隐藏，由核心内联 TOC 兜底。
 *
 * 实现为自包含原生 JS（非 Vue 组件）：需把节点注入到 .sidebar 流内，原生 DOM 控制最直接，
 * 且无需改动核心 App.vue / PostView / Sidebar。
 */
(function () {
  "use strict";

  var STYLE_ID = "article-toc-style";
  var NAV_CLASS = "article-toc-sidebar";
  var THRESHOLD = 110; // 距视口顶部多少像素算「当前章节」

  var tocEl = null;       // <nav> 目录容器
  var headingEls = [];    // 缓存的标题 DOM
  var ticking = false;
  var observer = null;
  var retryTimers = [];
  var scrollHandler = null;

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css = [
      ".article-toc-sidebar{",
      "  position: sticky; top: 96px;",
      "  margin-bottom: 22px; padding: 14px 14px 12px;",
      "  background: var(--card-bg, #fff);",
      "  border: 1px solid var(--border-color, #ececec);",
      "  border-radius: 12px; font-size: 13px; line-height: 1.5;",
      "  box-shadow: 0 2px 12px rgba(0,0,0,.05);",
      "}",
      ".article-toc-title{ margin: 0 0 8px; font-size: 12px; font-weight: 600;",
      "  letter-spacing: .04em; color: var(--muted, #888); }",
      ".article-toc-list{ list-style: none; margin: 0; padding: 0; }",
      ".article-toc-item{ margin: 0; }",
      ".article-toc-link{ display: block; padding: 3px 8px; color: var(--text-soft, #555);",
      "  text-decoration: none; border-left: 2px solid transparent;",
      "  border-radius: 0 6px 6px 0; transition: color .15s, background .15s, border-color .15s; }",
      ".article-toc-link:hover{ color: var(--link, #1a73e8); background: rgba(0,0,0,.03); }",
      ".article-toc-item.active > .article-toc-link{ color: var(--accent, #1a73e8);",
      "  font-weight: 600; border-left-color: var(--accent, #1a73e8); background: rgba(26,115,232,.06); }",
      ".article-toc-l3 .article-toc-link{ padding-left: 20px; font-size: 12px; }",
      ".article-toc-l4 .article-toc-link{ padding-left: 32px; font-size: 12px; color: var(--muted, #999); }",
      /* 点击跳转不被固定头部遮挡 */
      ".post-body h2, .post-body h3, .post-body h4{ scroll-margin-top: 90px; }",
      /* 窄屏：右侧栏堆叠到正文下方，目录侧栏隐藏，由核心内联 TOC 兜底 */
      "@media (max-width: 820px){ .article-toc-sidebar{ display: none !important; } }",
      "[data-theme=\"dark\"] .article-toc-sidebar{ box-shadow: 0 2px 12px rgba(0,0,0,.3); }"
    ].join("\n");
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);
  }

  function ensureTocEl() {
    if (tocEl) return tocEl;
    tocEl = document.createElement("nav");
    tocEl.className = NAV_CLASS;
    tocEl.setAttribute("aria-label", "文章目录");
    tocEl.style.display = "none";
    return tocEl;
  }

  function setActive(id) {
    if (!tocEl) return;
    var items = tocEl.querySelectorAll(".article-toc-item");
    for (var i = 0; i < items.length; i++) {
      var link = items[i].querySelector(".article-toc-link");
      var hid = link ? link.getAttribute("href").slice(1) : "";
      if (hid === id) items[i].classList.add("active");
      else items[i].classList.remove("active");
    }
  }

  function updateActive() {
    if (!headingEls.length) return;
    var cur = headingEls[0].id;
    for (var i = 0; i < headingEls.length; i++) {
      if (headingEls[i].getBoundingClientRect().top - THRESHOLD <= 0) cur = headingEls[i].id;
      else break;
    }
    setActive(cur);
  }

  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () { updateActive(); ticking = false; });
  }

  function onClick(e) {
    var href = this.getAttribute("href") || "";
    if (href.charAt(0) !== "#") return;
    e.preventDefault();
    var el = document.getElementById(href.slice(1));
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function build() {
    var body = document.querySelector(".post-body");
    if (!body) {
      // 非文章页：隐藏并移出 DOM（避免残留）
      if (tocEl && tocEl.parentNode) tocEl.parentNode.removeChild(tocEl);
      headingEls = [];
      return;
    }
    var hs = body.querySelectorAll("h2, h3, h4");
    var frag = document.createDocumentFragment();
    var ul = document.createElement("ul");
    ul.className = "article-toc-list";
    headingEls = [];
    var count = 0;
    Array.prototype.forEach.call(hs, function (el, i) {
      if (!el.id) el.id = "atoc-" + i;
      var level = el.tagName === "H2" ? 2 : (el.tagName === "H3" ? 3 : 4);
      var text = (el.textContent || "").trim();
      if (!text) return;
      var li = document.createElement("li");
      li.className = "article-toc-item article-toc-l" + level;
      var a = document.createElement("a");
      a.className = "article-toc-link";
      a.href = "#" + el.id;
      a.textContent = text;
      a.addEventListener("click", onClick);
      li.appendChild(a);
      ul.appendChild(li);
      headingEls.push(el);
      count++;
    });

    var nav = ensureTocEl();
    nav.innerHTML = "";
    var title = document.createElement("p");
    title.className = "article-toc-title";
    title.textContent = "目录";
    nav.appendChild(title);
    nav.appendChild(ul);

    if (count === 0) {
      if (nav.parentNode) nav.parentNode.removeChild(nav);
      return;
    }
    // 注入到文章页右侧 .sidebar 顶部（桌面常驻；窄屏由 CSS 隐藏）
    var sidebar = document.querySelector(".sidebar");
    if (sidebar && nav.parentNode !== sidebar) {
      sidebar.insertBefore(nav, sidebar.firstChild);
    } else if (!sidebar && !nav.parentNode) {
      // 没有 .sidebar 时挂载到 body（兜底，通常不会走到）
      document.body.appendChild(nav);
    }
    nav.style.display = "";
    updateActive();
  }

  function scheduleBuild() {
    build();
  }

  function init() {
    injectStyle();
    ensureTocEl();
    // 初次构建（直接落在文章页时内容可能已渲染）
    build();
    // 内容异步加载 / SPA 路由切换：监听文章正文容器变化
    var host = document.querySelector("main.site-frame-inner");
    if (host && "MutationObserver" in window) {
      observer = new MutationObserver(function () { scheduleBuild(); });
      observer.observe(host, { childList: true, subtree: true });
    }
    // 多延迟重试，覆盖接口返回后 innerHTML 写入的时机
    retryTimers.push(setTimeout(build, 300));
    retryTimers.push(setTimeout(build, 900));
    scrollHandler = onScroll;
    window.addEventListener("scroll", scrollHandler, { passive: true });
    window.addEventListener("resize", scrollHandler);
  }

  function destroy() {
    if (observer) { observer.disconnect(); observer = null; }
    if (scrollHandler) {
      window.removeEventListener("scroll", scrollHandler);
      window.removeEventListener("resize", scrollHandler);
      scrollHandler = null;
    }
    retryTimers.forEach(clearTimeout);
    retryTimers = [];
    if (tocEl && tocEl.parentNode) tocEl.parentNode.removeChild(tocEl);
    tocEl = null;
    headingEls = [];
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // 暴露清理函数（供未来需要卸载时调用；当前脚本随页面加载一次，无需主动卸载）
  window.__articleTocDestroy = destroy;
})();
