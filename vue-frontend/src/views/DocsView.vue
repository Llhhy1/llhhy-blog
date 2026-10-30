<template>
  <div class="docs-container">
    <aside class="docs-sidebar">
      <div class="sidebar-header">
        <span>API 文档</span>
        <span class="sidebar-ver" :title="'当前运行版本，取自 GET /api/health'">{{ appVersion || '—' }}</span>
      </div>

      <!-- 文档内搜索：既匹配章节名，也匹配该节正文（端点路径 / 字段名）。
           780 行文档 + 100 多个端点，纯靠翻侧栏找路径不现实。 -->
      <div class="doc-search">
        <input
          v-model="query"
          type="search"
          class="doc-search-input"
          placeholder="搜索端点 / 章节…"
          aria-label="搜索文档内容"
          @keydown.esc="query = ''"
        />
        <button v-if="query" type="button" class="doc-search-clear" aria-label="清空搜索" @click="query = ''">✕</button>
      </div>

      <nav class="sidebar-nav">
        <div v-for="sec in visibleSections" :key="sec.title" class="nav-section" :class="{ 'nav-section-active': activeId === sec.id }">
          <div class="nav-section-title">{{ sec.title }}</div>
          <a
            v-for="l in sec.links"
            :key="l.id"
            :href="'#' + l.id"
            class="nav-link"
            :class="{ active: activeId === l.id }"
            @click.prevent="scrollTo(l.id)"
          >{{ l.label }}</a>
        </div>
        <p v-if="query && !visibleSections.length" class="nav-empty">
          没找到「{{ query }}」<br />试试端点片段，比如 <code>mobile</code>、<code>slug</code>
        </p>
        <p v-else-if="query" class="nav-result">命中 {{ matchCount }} 节</p>
      </nav>
    </aside>

    <div class="docs-main">
      <!-- ============ 全站唯一接口文档 ============
           本页内容**全部**来自后端 `GET /api/docs`（渲染仓库里的 `myblog/API.md`），
           不再有手写的第二份清单 —— 以前那份改了 API.md 不会跟着变，
           出现过「文档明明重写了，页面却还是旧的」。 -->
      <div id="full-list" class="doc-section">
        <p class="doc-src-note">
          本页内容由后端 <code>GET /api/docs</code> 渲染仓库文件
          <code>myblog/API.md</code> 生成，与代码同源。
          运行版本 <strong>{{ appVersion || "—" }}</strong>
          <span class="p-note">（取自 <code>GET /api/health</code>）</span>。
        </p>

        <p v-if="fullState === 'loading'" class="doc-full-hint">正在加载接口文档…</p>
        <p v-else-if="fullState === 'error'" class="doc-full-hint">
          接口文档暂时无法加载（后端 <code>GET /api/docs</code> 未返回内容）。
          可直接查阅仓库中的 <code>myblog/API.md</code>。
        </p>
        <div
          v-show="fullState === 'ok'"
          class="doc-full-body"
          v-html="fullHtml"
        ></div>
      </div>
    </div>

    <!-- 右侧只放**当前章节的小节**，与左栏章节列表是互补关系，不再互相抄：
         左栏回答「去哪个章节」，右栏回答「这一章里跳到哪一小节」。
         改之前右栏把每节的 h1 也列了一遍，前几条和左栏完全重复 —— 那才是「两个目录」的由来。 -->
    <aside class="docs-toc">
      <div class="toc-title">{{ currentLabel || '本节内容' }}</div>
      <nav v-if="currentSubs.length" class="toc-nav">
        <a v-for="t in currentSubs" :key="t.id" :href="'#'+t.id"
           class="toc-link" :class="{ active: activeSub === t.id }"
           @click.prevent="scrollTo(t.id)">{{ t.text }}</a>
      </nav>
      <p v-else class="toc-empty">本节没有小节</p>
    </aside>

    <!-- 长文档回顶：本页 ~800 行，读到二次开发指南底部再滚回去很费劲 -->
    <Transition name="docs-top">
      <button v-if="showTop" type="button" class="docs-top" aria-label="回到顶部" title="回到顶部" @click="toTop">↑</button>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { copyText } from "../lib/clipboard.js";
// v3.17.10：highlight.js 改为本地打包——原 cdnjs 动态注入的 CSS/JS 被 CSP（style-src/script-src 'self'）
// 拦截，线上代码高亮从未真正生效。代码块仅用 bash/js/json/python 四种语言，主题沿用 github-dark。
import hljs from "highlight.js/lib/core";
import "highlight.js/styles/github-dark.css";
import lBash from "highlight.js/lib/languages/bash";
import lJson from "highlight.js/lib/languages/json";
import lPython from "highlight.js/lib/languages/python";
import lJs from "highlight.js/lib/languages/javascript";
import lPlain from "highlight.js/lib/languages/plaintext";
hljs.registerLanguage("bash", lBash);
hljs.registerLanguage("shell", lBash);
hljs.registerLanguage("json", lJson);
hljs.registerLanguage("python", lPython);
hljs.registerLanguage("js", lJs);
hljs.registerLanguage("javascript", lJs);
// 无语言标注的围栏（目录树等）显式标 plaintext，避免 highlight.js 退化成自动探测
// （会把目录树误判成 bash/python 乱上色）。text 作为 plaintext 的别名一并注册。
hljs.registerLanguage("plaintext", lPlain);
hljs.registerLanguage("text", lPlain);
// 既有 tryHl 轮询逻辑依赖 window.hljs，这里直接就绪（v5.3.2 起时机改由
// decorateCodeBlocks() 在内容注入 DOM 后统一处理，见下方说明）。
window.hljs = hljs;

// 章节树：[{ id, label, subs: [{id, text}] }]
// 原实现是平铺的 h1+h3 混合列表，导致右栏前几条 = 左栏（两个目录做同一件事）。
const tocSections = ref([]);
// activeId：当前**章节**（左栏高亮用）；activeSub：当前**小节**（右栏高亮用）
const activeId = ref("");
const activeSub = ref("");
// v3.20.0 曾在挂载时 new 一个 IntersectionObserver 做目录高亮、却从不 disconnect
// （路由组件反复进出会持续累积）。v4.12.0 改为 scroll 驱动后**根本不需要 observer**，
// 这类泄漏从结构上消失了；保留一个监听器句柄用于卸载时摘除。
let _topHandler = null;

// 运行版本：由 /api/health 提供。
// 原实现把版本号写死在模板里（v3.8.7），线上到 v4.11.0 时这页还写着三个大版本前的号
// —— 而投稿/评审恰好会点开 /docs 当「接口即文档」的证据。取运行时值就再也不会漂。
const appVersion = ref("");

/* ---------------------------------------------------------------- 完整接口清单 */
// v5.3.0：上面各章是手写的导读，改了 API.md 不会跟着变（出现过「文档重写了、
// 页面还是旧的」）。这一节直接消费 `GET /api/docs`（后端渲染仓库里的 API.md），
// 页面与仓库文档**同源**，不再有第二份手写清单。
const fullState = ref("idle");        // idle | loading | ok | error
const fullHtml = ref("");

async function loadFullList() {
  if (fullState.value !== "idle") return;
  fullState.value = "loading";
  try {
    const r = await fetch("/api/docs");
    // 🔴 后端框架层报错（500 / 413 / 鉴权跳转）返回的是 HTML，r.json() 会抛
    //    「Unexpected token '<'」。每个 fetch 都要有非 JSON 兜底。
    const ct = r.headers.get("content-type") || "";
    if (!ct.includes("application/json")) throw new Error("非 JSON 响应");
    const d = await r.json();
    if (!d || d.available === false || !d.html) {
      fullState.value = "error";
      return;
    }
    fullHtml.value = d.html;
    fullState.value = "ok";
    // 内容注入后 DOM 才完整 —— 必须重建 TOC，否则左栏/右栏不收录任何章节
    await new Promise((res) => requestAnimationFrame(() => res()));
    buildToc();
    // v5.3.2：内容已在 DOM，现在统一给代码块加语言标签栏 + 复制按钮 + 真高亮
    decorateCodeBlocks();
  } catch (e) {
    fullState.value = "error";
  }
}

// v5.3.0：原 `navSections` 是硬编码的章节清单，指向的是本页**已被删除的**手写章节
// （common / auth / posts …）。现在整页内容来自 API.md，章节由 buildToc() 从 DOM 生成，
// 硬编码清单遂彻底废弃 —— 侧栏直接用 tocSections（见下方 visibleSections）。

const query = ref("");
// 各节正文的小写快照：让搜索能命中「正文里的端点路径」，而不只是章节标题。
// 例如输入 mobile / shell-check / slug 都能定位到对应章节。
const sectionText = ref({});

const visibleSections = computed(() => {
  // v5.3.0：数据源改为 buildToc() 生成的 tocSections（按 API.md 渲染后的真实标题）。
  const q = query.value.trim().toLowerCase();
  if (!q) return tocSections.value;
  return tocSections.value
    .map((sec) => ({
      ...sec,
      links: sec.links.filter((l) => {
        if ((l.label + " " + l.id).toLowerCase().includes(q)) return true;
        const body = sectionText.value[l.id];
        return !!body && body.includes(q);
      }),
    }))
    .filter((sec) => sec.links.length);
});

const showTop = ref(false);

const currentSection = computed(() => tocSections.value.find((s) => s.id === activeId.value) || null);
const currentSubs = computed(() => (currentSection.value ? currentSection.value.subs : []));
const currentLabel = computed(() => (currentSection.value ? currentSection.value.label : ""));

const matchCount = computed(() =>
  visibleSections.value.reduce((n, sec) => n + sec.links.length, 0)
);

function scrollTo(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

// 注意：本组件的 scrollTo 遮蔽了 window.scrollTo，回顶必须显式用 window.*
function toTop() {
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// 当前章节 / 小节判定线：站点头 58px 再留一点余量
const ACTIVE_LINE = 96;

function syncActive() {
  // 当前模块 = 最靠上且已越过判定线的 h2（与 tocSections 的 node.id 对齐）。
  // v5.3.0 的 bug：这里把 activeId 设成了 `.doc-section` 容器（id=full-list），
  // 它永远不等于任何 h2 节点 → currentSection 找不到 → 右栏「本节内容」恒空、
  // 左栏也无高亮。改成跟踪 h2。
  const h2s = Array.from(document.querySelectorAll(".docs-main .doc-section h2"));
  if (!h2s.length) return;
  let cur = h2s[0];
  for (const h of h2s) {
    if (h.getBoundingClientRect().top <= ACTIVE_LINE) cur = h;
    else break;
  }
  activeId.value = cur.id;
  // 当前小节 = 当前模块下、已越过判定线的最后一个 h3
  const sec = tocSections.value.find((s) => s.id === cur.id);
  let sub = "";
  if (sec) {
    for (const s of sec.subs) {
      const el = document.getElementById(s.id);
      if (el && el.getBoundingClientRect().top <= ACTIVE_LINE) sub = s.id;
      else break;
    }
  }
  activeSub.value = sub;
}

function buildToc() {
  // 按「模块(h2) → 接口(h3)」建树：
  //   * links → 左栏导航 + 搜索（visibleSections 用）
  //   * subs  → 右栏「本节内容」（currentSection 用）
  // 两者指向同一组 h3，缺一不可。v5.3.0 的 bug 就是只填了 subs 没填 links，
  // 导致左栏没有可点的接口、搜索永远「没找到」、右栏也空。
  const sections = [];
  let n = 0;

  // 先算每个 h2 模块的整段正文（h2 到下一个 h2 之前），作为该模块下所有接口的搜索语料
  const h2Arr = Array.from(document.querySelectorAll(".docs-main .doc-section h2"));
  const modText = {};
  h2Arr.forEach((h2, i) => {
    if (!h2.id) h2.id = "doc-h2-" + n++;
    let txt = (h2.textContent || "") + " ";
    let el = h2.nextElementSibling;
    const stop = h2Arr[i + 1];
    while (el && el !== stop) {
      txt += (el.textContent || "") + " ";
      el = el.nextElementSibling;
    }
    modText[h2.id] = txt.toLowerCase();
  });

  document.querySelectorAll(".docs-main .doc-section").forEach((sec) => {
    const h1 = sec.querySelector("h1");
    if (!sec.id) sec.id = "doc-sec-" + sections.length;
    const h2s = sec.querySelectorAll("h2");
    if (h2s.length) {
      h2s.forEach((h2) => {
        if (!h2.id) h2.id = "doc-h2-" + n++;
        const node = {
          id: h2.id,
          label: h2.textContent.trim(),
          title: h2.textContent.trim(),
          subs: [],
          links: [],
        };
        // 收集该 h2 到下一个 h2 之间的 h3（接口条目）
        let el = h2.nextElementSibling;
        while (el && el.tagName !== "H2") {
          if (el.tagName === "H3") {
            if (!el.id) el.id = "doc-h-" + n++;
            const text = el.textContent.trim();
            node.subs.push({ id: el.id, text });
            node.links.push({ id: el.id, label: text });
          }
          el = el.nextElementSibling;
        }
        sections.push(node);
      });
      return;
    }
    // 没有 h2 的兜底（理论上 API.md 全篇都是 h2 模块，这里只是保险）
    const fallback = {
      id: sec.id,
      label: h1 ? h1.textContent.trim() : sec.id,
      title: h1 ? h1.textContent.trim() : sec.id,
      subs: [],
      links: [],
    };
    sections.push(fallback);
    sec.querySelectorAll("h3").forEach((h3) => {
      if (!h3.id) h3.id = "doc-h-" + n++;
      const text = h3.textContent.trim();
      fallback.subs.push({ id: h3.id, text });
      fallback.links.push({ id: h3.id, label: text });
    });
  });
  tocSections.value = sections;
  // 初始定位到第一节，否则首屏右栏是空的（观察器要等滚动才触发）
  if (sections.length && !activeId.value) activeId.value = sections[0].id;

  // 搜索语料：把模块正文挂到该模块下每个接口(link) id 上，
  // 这样输入正文里出现的端点路径 / 字段名也能命中（不止匹配标题）。
  // 关键：key 必须是 h3 的 link id —— visibleSections 里 `sectionText.value[l.id]`
  // 查的就是它；v5.3.0 原来 key 成 h2 id，和查询端的 h3 id 对不上，搜索正文永远不命中。
  const idx = {};
  h2Arr.forEach((h2) => {
    const sec = sections.find((s) => s.id === h2.id);
    if (!sec) return;
    for (const l of sec.links) idx[l.id] = modText[h2.id] || "";
  });
  sectionText.value = idx;
}

// v5.3.2：把 .doc-full-body 里的每个 <pre> 包装成「语言标签栏 + 复制按钮」的代码块，
// 并真正调用 highlight.js 高亮。必须在内容注入 DOM 之后调用（见 loadFullList 末尾）。
//
// 关键修复（原 /docs 代码块「无设计 + 不高亮」两个根因）：
//   ① 原 tryHl 在 onMounted 立即跑，此时 /api/docs 的异步内容还没到，装饰的是空容器；
//      内容到达后 v-html 重建出新的 <pre>，再也没人高亮 → 高亮形同虚设。
//   ② 无语言标注的围栏（目录树）若不显式标 plaintext，highlight.js 会退化成自动探测，
//      把目录树误判成 bash/python 乱上色。
//
// 语言名取自后端 markdown 渲染出的 class="language-xxx"（fenced_code 扩展产物）；
// 复制按钮是 createElement 生成的，拿不到 scoped 的 data-v，样式须用 :deep() 命中
// （同旧 .copy-btn 的坑：裸写 .code-block__copy 会编译成带 [data-v-xxx] 的选择器，永不命中）。
function decorateCodeBlocks() {
  const root = document.querySelector(".docs-main .doc-full-body");
  if (!root) return;
  root.querySelectorAll("pre").forEach((pre) => {
    if (pre.parentElement && pre.parentElement.classList.contains("code-block")) return; // 已包装，跳过

    const code = pre.querySelector("code");
    let lang = "text";
    const cls = (code && code.className) || "";
    const m = cls.match(/language-([\w-]+)/);
    if (m) lang = m[1];
    else if (code) code.classList.add("language-plaintext"); // 避免自动探测误上色

    // 高亮必须在包装前对 code 调：highlightElement 会改写 code 内部 DOM
    if (window.hljs && code) {
      try { window.hljs.highlightElement(code); } catch (e) { /* ignore */ }
    }

    // 包装结构：.code-block > (.code-block__bar + pre)
    const wrap = document.createElement("div");
    wrap.className = "code-block";
    const bar = document.createElement("div");
    bar.className = "code-block__bar";
    const langEl = document.createElement("span");
    langEl.className = "code-block__lang";
    langEl.textContent = lang; // 纯文本，无 XSS 风险
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "code-block__copy";
    btn.textContent = "复制";
    btn.addEventListener("click", () => {
      const text = (pre.querySelector("code") || pre).innerText;
      // v3.17.9：三层兜底复制（Clipboard API → execCommand → 手动弹窗提示）
      copyText(text).then((ok) => {
        btn.textContent = ok ? "已复制" : "已弹窗，请手动复制";
        setTimeout(() => { btn.textContent = "复制"; }, 1800);
      });
    });
    bar.appendChild(langEl);
    bar.appendChild(btn);
    // 先把 wrap 插到 pre 之前（此时 pre 还在原父节点），再把 pre 移进 wrap
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(bar);
    wrap.appendChild(pre);
  });
}

// v3.17.9：复制统一走 lib/clipboard.js 的三层兜底（原 fallbackCopy 已被其覆盖）

onMounted(() => {
  // v3.17.10：highlight.js 与主题样式已本地打包（见 script 顶部 import），不再依赖 CDN 与 CSP 放行

  buildToc();

  // v5.3.0：整页内容来自 GET /api/docs，挂载即加载（不再有「展开」这一步）。
  // 加载完成后 loadFullList 内部会重建 TOC，左栏/右栏才会出现章节。
  loadFullList();

  // 版本号：公开探活接口，只回 ok / version / db，不带任何敏感信息。
  // 取不到就保持空 → 模板渲染「—」，绝不回退成写死的旧版本号。
  fetch("/api/health", { headers: { Accept: "application/json" }, credentials: "same-origin" })
    .then((r) => r.json())
    .then((d) => {
      const v = (d && d.version) || "";
      if (v) appVersion.value = v.startsWith("v") ? v : "v" + v;
    })
    .catch(() => { /* 探活失败不影响文档阅读 */ });

  // 回顶按钮 + 目录高亮：同一个 scroll 监听里处理，避免挂两个监听
  _topHandler = () => {
    showTop.value = window.scrollY > 600;
    syncActive();
  };
  window.addEventListener("scroll", _topHandler, { passive: true });
  _topHandler();

  // 代码块的高亮 + 语言标签栏 + 复制按钮，改由 loadFullList() 在内容注入 DOM 后
  // 统一调用 decorateCodeBlocks() 完成（v5.3.2 修复：原 tryHl 在挂载时跑、此时
  // /api/docs 的异步内容还没到，装饰的是空容器，真正的代码块永远没被高亮）。

  // 右侧「本节内容」随滚动高亮：改为在 scroll 里按位置算当前章节 + 当前小节。
  // 不用 IntersectionObserver 是因为它的回调只给出「谁进入了窄带」，而这里需要的
  // 是「当前处在哪一节/哪一小节」，按 rect.top 顺序判定更直接，也不会漏。
  syncActive();
});

// v3.20.0 修复**真实泄漏**：原实现在 onMounted 里 new 了 IntersectionObserver 却从不
// disconnect。DocsView 是**路由组件**，每次进入 /docs 都会新建一个 observer，
// 而它仍持有上一次挂载的 DOM 节点引用 → 反复进出会持续累积。
// （对比：App.vue 的 scroll/resize 未清理只是「理论问题」，因为根组件不会卸载；
//   这里才是真正会累积的那个。）
onBeforeUnmount(() => {
  // 同一类问题的另一半：新增的 scroll 监听也必须摘，否则每次进 /docs 多挂一个。
  if (_topHandler) { window.removeEventListener("scroll", _topHandler); _topHandler = null; }
});
</script>

<style scoped>
/* ════════════════════════════════════════════════════════════════════════
   /docs 样式重做（v4.12.0）

   原实现是一整套**硬编码色**（#3b82f6 / #e5e7eb / #f8fafc / #4b5563…），
   与全站 tokens.css 是两套体系，导致两个后果：
     ① 后台改主题色（accent_color）后，这页仍然是蓝的 —— 与全站脱节；
     ② 深色模式靠 20 多条 [data-theme="dark"] 逐条覆盖，漏一条就糊成一片。
   现在全部走 token：换主题色跟着变，深色模式几乎不用单独写。

   另修三处真实缺陷（不是审美问题）：
     1. scroll-margin-top 原为 20px，而站点头是 sticky 58px ——
        点目录/锚点后标题被顶栏盖住，等于链接点了个寂寞；
     2. 复制按钮绝对定位在 pre 右上角，padding 只有 16px ——
        长代码的**首行会被按钮压住**；
     3. .params-table 桌面用 table-layout: fixed，两列表格被强行 50/50，
        说明列和张量列一样宽，浪费一半宽度。
   ════════════════════════════════════════════════════════════════════════ */

.docs-container {
  display: flex;
  align-items: flex-start;
  gap: var(--space-5);
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--space-5) var(--space-4) var(--space-8);
  min-height: calc(100vh - 100px);
}

/* ── 左：章节导航 ─────────────────────────────────────────────── */
.docs-sidebar {
  width: 262px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  padding-right: var(--space-4);
  position: sticky;
  /* 站点头 sticky 高 58px（global.css .header-inner），留 16px 呼吸 */
  top: 74px;
  height: fit-content;
  max-height: calc(100vh - 96px);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.sidebar-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 2px solid var(--accent);
}

.sidebar-ver {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-faint);
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

/* 搜索框 */
.doc-search { position: relative; margin-bottom: var(--space-3); }

.doc-search-input {
  width: 100%;
  box-sizing: border-box;
  padding: 7px 30px 7px 11px;
  font-size: 13px;
  font-family: inherit;
  color: var(--text);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  outline: none;
  transition: border-color var(--transition), background var(--transition), box-shadow var(--transition);
  -webkit-appearance: none;
  appearance: none;
}
.doc-search-input::-webkit-search-cancel-button { display: none; }
.doc-search-input::placeholder { color: var(--text-faint); }
.doc-search-input:focus {
  border-color: var(--accent);
  background: var(--surface);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.doc-search-clear {
  position: absolute;
  right: 5px;
  top: 50%;
  transform: translateY(-50%);
  border: 0;
  background: transparent;
  color: var(--text-faint);
  cursor: pointer;
  font-size: 11px;
  line-height: 1;
  padding: 5px 6px;
  border-radius: var(--radius-xs);
}
.doc-search-clear:hover { color: var(--text); background: var(--surface-3); }

/* ── 完整接口清单（v5.3.0）─────────────────────────────────────────────
   `v-html` 进来的内容是**后端渲染好的 markdown**（已过 bleach 清洗），
   它不带本组件的 scoped 属性，所以必须用 :deep() 才能命中。
   样式只做「让 markdown 可读」这一件事，不另起一套配色体系。 */
.doc-src-note {
  font-size: 13px;
  color: var(--text-muted, #888);
  padding: 8px 12px;
  margin: 0 0 12px;
  border-left: 3px solid var(--accent, #4c6ef5);
  background: var(--surface-2, rgba(127, 127, 127, .08));
  border-radius: 0 var(--ui-radius-group, 8px) var(--ui-radius-group, 8px) 0;
}
.doc-full-hint {
  font-size: 13px;
  color: var(--text-muted, #888);
  margin: 6px 0;
}
.doc-full-body {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid var(--border, rgba(127, 127, 127, .22));
  font-size: 14px;
  line-height: 1.75;
  overflow-wrap: break-word;
}
/* 清单里的标题降一级视觉权重：它是「附录」，不该抢上面人工导读的层级 */
.doc-full-body :deep(h1) { font-size: 19px; margin: 18px 0 8px; }
.doc-full-body :deep(h2) { font-size: 17px; margin: 20px 0 8px; }
.doc-full-body :deep(h3) { font-size: 15px; margin: 16px 0 6px; }
.doc-full-body :deep(h4) { font-size: 14px; margin: 12px 0 4px; }
.doc-full-body :deep(p) { margin: 6px 0; }
.doc-full-body :deep(ul),
.doc-full-body :deep(ol) { margin: 6px 0 6px 20px; }
.doc-full-body :deep(li) { margin: 3px 0; }
.doc-full-body :deep(code) {
  font-size: .88em;
  padding: 1px 5px;
  border-radius: 5px;
  background: var(--surface-3, rgba(127, 127, 127, .16));
}
/* 兜底：decorateCodeBlocks 把 pre 包进 .code-block 之前，pre 短暂以深底呈现，
   避免内容刚注入那一刻闪一下浅底。包好后由 .code-block pre 接管样式。 */
.doc-full-body :deep(pre) {
  background: #1f2937;
  color: #f3f4f6;
  overflow-x: auto;
  border-radius: var(--ui-radius-group, 12px);
}
.doc-full-body :deep(pre code) { background: none; padding: 0; }
.doc-full-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}
.doc-full-body :deep(th),
.doc-full-body :deep(td) {
  border: 1px solid var(--border, rgba(127, 127, 127, .25));
  padding: 5px 8px;
  text-align: left;
  vertical-align: top;
}
.doc-full-body :deep(blockquote) {
  margin: 10px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--border, rgba(127, 127, 127, .35));
  color: var(--text-muted, #888);
}
.doc-full-body :deep(a) { color: var(--accent, #4c6ef5); }

.nav-section { margin-bottom: var(--space-4); }
/* 当前所在模块：左栏高亮当前章节标题（activeId 现在指向 h2 模块 id） */
.nav-section-active .nav-section-title { color: var(--accent); }

.nav-section-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .04em;
  color: var(--text-faint);
  margin-bottom: var(--space-2);
  text-transform: uppercase;
}

.nav-link {
  display: block;
  padding: 6px 10px;
  color: var(--text-muted);
  text-decoration: none;
  border-radius: var(--radius-xs);
  border-left: 2px solid transparent;
  transition: background var(--transition), color var(--transition), border-color var(--transition);
  font-size: 13.5px;
  line-height: 1.5;
}
.nav-link:hover { background: var(--surface-2); color: var(--accent); }
/* 当前所在章节：原来只有右侧 TOC 会跟着滚，左侧没有任何反馈 */
.nav-link.active {
  color: var(--accent);
  background: var(--accent-soft);
  border-left-color: var(--accent);
  font-weight: 600;
}

.nav-result, .nav-empty {
  font-size: 12px;
  color: var(--text-faint);
  line-height: 1.7;
  margin: var(--space-2) 0 0;
  padding: 0 10px;
}
.nav-empty code { font-size: 11.5px; }

/* ── 中：正文 ─────────────────────────────────────────────────── */
.docs-main { flex: 1; min-width: 0; }

.doc-section {
  margin-bottom: var(--space-8);
  /* 74px = 顶栏 58px + 16px。原值 20px 会让锚点落点在顶栏下方被遮住。 */
  scroll-margin-top: 74px;
  overflow-wrap: break-word;
}

.doc-section h1 {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--text);
  margin: 0 0 var(--space-4);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
}
.doc-section h3 {
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  margin: var(--space-6) 0 var(--space-3);
  scroll-margin-top: 82px;
}
.doc-section h4 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  margin: var(--space-5) 0 var(--space-2);
}
.doc-section p { line-height: 1.85; color: var(--text-muted); margin: var(--space-3) 0; }
.doc-section ul, .doc-section ol { line-height: 1.85; color: var(--text-muted); padding-left: 22px; }
.doc-section li { margin-bottom: 3px; }
.doc-section a { color: var(--accent); text-decoration: none; }
.doc-section a:hover { text-decoration: underline; }

.p-note { color: var(--text-faint); font-size: 12.5px; }

/* 「本文档覆盖范围」提示块：把「全部接口」这种不成立的承诺讲清楚 */
.coverage {
  background: var(--surface-2);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-xs);
  padding: 10px 14px;
  font-size: 13.5px;
}

/* ── 端点行 ───────────────────────────────────────────────────── */
.endpoint {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: var(--space-4) 0;
  padding: 10px 14px;
  background: var(--surface-2);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--accent);
  flex-wrap: wrap;
}

.method {
  padding: 3px 10px;
  border-radius: var(--radius-xs);
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: .03em;
  text-transform: uppercase;
  /* 深浅两模式都成立：亮色下 --on-accent 是白字，暗色下是近黑 —— 而暗色的
     success / warning / danger / accent 都被提亮过（见 tokens.css），
     所以「深底白字」与「亮底黑字」恰好各自可读。 */
  color: var(--on-accent);
}
.method.get { background: var(--success); }
.method.post { background: var(--accent); }
.method.put, .method.patch { background: var(--warning); }
.method.delete { background: var(--danger); }

.path {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text);
  word-break: break-all;
  overflow-wrap: anywhere;
}

.auth {
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 600;
  margin-left: auto;
  white-space: nowrap;
}
.auth-public { background: var(--surface-3); color: var(--text-muted); }
.auth-login { background: var(--accent-soft); color: var(--accent); }
/* 危险级别用描边而非实底：实底红在暗色下会把白字压崩（--danger 提亮过） */
.auth-admin { color: var(--danger); box-shadow: inset 0 0 0 1px var(--danger); }

/* ── 表格 ─────────────────────────────────────────────────────── */
.params-table {
  width: 100%;
  border-collapse: collapse;
  margin: var(--space-4) 0;
  font-size: 13.5px;
  /* 桌面让浏览器按内容分配：原固定布局把「路径 / 说明」两列拉成 50/50 */
  table-layout: auto;
}
.params-table th,
.params-table td {
  padding: 9px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.7;
}
.params-table th {
  background: var(--surface-2);
  color: var(--text);
  font-weight: 700;
  font-size: 12.5px;
  white-space: nowrap;
}
.params-table td { color: var(--text-muted); }
.params-table tbody tr:hover td { background: var(--surface-2); }

/* ── 代码块（v5.3.2 重做：语言标签栏 + 复制按钮 + 真高亮）──────────────
   代码块刻意保持深底 —— highlight.js 的 github-dark 主题要求深底，且「文档代码块」
   统一深底观感比跟随明暗模式更不容易出错（github-dark 落在浅底上几乎不可读）。
   结构：.code-block（圆角容器）→ .code-block__bar（语言标签 + 复制）+ pre。
   标签栏 / 复制按钮由 decorateCodeBlocks() 在内容注入后用 createElement 生成，
   **拿不到 scoped 的 data-v**，故全用 :deep() 命中（同旧 .copy-btn 的坑）。 */
.doc-full-body :deep(.code-block) {
  margin: var(--space-4) 0;
  border: 1px solid #0b1220;
  border-radius: var(--ui-radius-group, 12px);
  overflow: hidden;
  background: #1f2937;
  box-shadow: var(--ui-shadow-card);
}
.doc-full-body :deep(.code-block__bar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 7px 12px;
  background: #111827;
  border-bottom: 1px solid #0b1220;
}
.doc-full-body :deep(.code-block__lang) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: #8b98a9;
}
.doc-full-body :deep(.code-block__copy) {
  flex: 0 0 auto;
  font-size: 11px;
  line-height: 1.5;
  padding: 2px 10px;
  color: #cbd5e1;
  background: rgba(255, 255, 255, .06);
  border: 1px solid rgba(255, 255, 255, .12);
  border-radius: var(--radius-xs);
  cursor: pointer;
  opacity: .6;
  transition: opacity var(--transition), background var(--transition);
}
.doc-full-body :deep(.code-block__copy:hover),
.doc-full-body :deep(.code-block__copy:focus-visible) {
  opacity: 1;
  background: rgba(255, 255, 255, .16);
}
.doc-full-body :deep(.code-block pre) {
  margin: 0;
  padding: 14px 16px;
  background: #1f2937;
  overflow-x: auto;
  line-height: 1.7;
}
.doc-full-body :deep(.code-block pre code) {
  display: block;
  padding: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.8px;
  background: none;
}

code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.8px; }

.doc-section :not(pre) > code {
  background: var(--surface-2);
  color: var(--danger);
  padding: 1px 5px;
  border-radius: var(--radius-xs);
  font-size: 12.5px;
  border: 1px solid var(--border);
}

/* ── 右：本页目录 ─────────────────────────────────────────────── */
.docs-toc {
  width: 196px;
  flex-shrink: 0;
  position: sticky;
  top: 74px;
  height: fit-content;
  max-height: calc(100vh - 96px);
  overflow-y: auto;
  padding-left: var(--space-4);
  border-left: 1px solid var(--border);
  overscroll-behavior: contain;
}
.toc-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .04em;
  color: var(--text-faint);
  text-transform: uppercase;
  margin-bottom: var(--space-3);
  /* 标题现在显示「当前章节名」，过长时省略而不是换行撑高 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.toc-empty { font-size: 12px; color: var(--text-faint); margin: 0; padding: 0 9px; }
.toc-nav { display: flex; flex-direction: column; gap: 1px; }
.toc-link {
  display: block;
  padding: 4px 9px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-faint);
  text-decoration: none;
  border-radius: var(--radius-xs);
  border-left: 2px solid transparent;
  transition: color var(--transition), background var(--transition), border-color var(--transition);
}
.toc-link:hover { color: var(--accent); background: var(--surface-2); }
.toc-link.active { color: var(--accent); border-left-color: var(--accent); font-weight: 600; background: var(--accent-soft); }

/* ── 回顶按钮 ─────────────────────────────────────────────────── */
.docs-top {
  position: fixed;
  right: 26px;
  bottom: 30px;
  z-index: 30;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 16px;
  cursor: pointer;
  box-shadow: var(--shadow-md);
  transition: color var(--transition), border-color var(--transition), transform var(--transition);
}
.docs-top:hover { color: var(--accent); border-color: var(--accent); transform: translateY(-2px); }

.docs-top-enter-active, .docs-top-leave-active { transition: opacity var(--transition), transform var(--transition); }
.docs-top-enter-from, .docs-top-leave-to { opacity: 0; transform: translateY(8px); }

/* ── 响应式 ───────────────────────────────────────────────────── */
/* 中屏隐藏右侧 TOC（本页内容宽，三栏会把正文压到 500px 以下） */
@media (max-width: 1180px) {
  .docs-toc { display: none; }
}

@media (max-width: 900px) {
  /* ⚠️ flex-direction 改成 column 后，桌面的 align-items: flex-start 必须显式复位成
     stretch —— 纵向容器里 flex-start 是「对齐到起始边并按内容宽度收缩」，
     而正文里有大量长代码行，fit-content 会把整页横向撑到 1245px（实测），
     移动端就变成整页横向溢出、文字被切掉。 */
  .docs-container {
    flex-direction: column;
    align-items: stretch;
    padding: var(--space-4) var(--space-3) var(--space-6);
    gap: var(--space-3);
  }

  /* 移动端侧栏：原实现是 max-height:200px 的纵向滚动块 —— 占掉半屏还看不全
     十个入口。改为横向滑动 chip，一划到底。display:contents 让每个 <a> 直接
     成为 flex 项，省掉一层嵌套改模板。 */
  .docs-sidebar {
    position: static;
    width: 100%;
    min-width: 0;
    max-height: none;
    overflow: visible;
    border-right: 0;
    border-bottom: 1px solid var(--border);
    padding-right: 0;
    padding-bottom: var(--space-3);
  }
  .sidebar-nav {
    display: flex;
    gap: var(--space-2);
    max-width: 100%;
    overflow-x: auto;
    padding-bottom: 2px;
    scrollbar-width: none;
  }
  .sidebar-nav::-webkit-scrollbar { display: none; }
  .nav-section { display: contents; }
  .nav-section-title { display: none; }
  .nav-link {
    flex: 0 0 auto;
    white-space: nowrap;
    padding: 5px 12px;
    font-size: 13px;
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
  }
  .nav-link.active { border-color: var(--accent); }
  .nav-result, .nav-empty { flex: 0 0 auto; margin: 0; padding: 0 6px; align-self: center; white-space: nowrap; }

  .docs-main { padding-top: var(--space-2); width: 100%; min-width: 0; max-width: 100%; }
  .doc-section { scroll-margin-top: 68px; }
  .doc-section h1 { font-size: 23px; }
  .doc-section h3 { font-size: 16px; scroll-margin-top: 68px; }

  .endpoint { gap: var(--space-2); padding: 9px 11px; }
  .path { font-size: 12.5px; }
  .auth { margin-left: 0; }

  /* 窄屏才用固定布局 + 强制换行，避免长 code 撑破视口 */
  .params-table { table-layout: fixed; font-size: 12.5px; }
  .params-table th, .params-table td { padding: 7px 8px; }
  .params-table th { white-space: normal; }

  .docs-top { right: 16px; bottom: 18px; }
}
</style>
