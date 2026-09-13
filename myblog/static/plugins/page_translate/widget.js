/* page_translate —— 全站翻译远程组件（v3.18.0）
 *
 * 契约：宿主 App.vue 暴露 window.__vueH（Vue 的 h）与 window.__pluginRegister(name, def)；
 *       本文件由 /api/plugins 的 remote_components 声明、宿主动态注入 <script> 后执行。
 * 形态：自包含原生 JS（无构建依赖、不引第三方库），注册一个用 h() 渲染的 Vue 组件。
 *
 * 能力：
 *  - 浮层「翻译整页 / 显示原文」按钮（fixed，随主题 token 自适应深浅色）；
 *  - 整页翻译：遍历正文/导航/页脚等全部可译文本节点（跳过 code/pre/脚本/输入框/data-no-translate）；
 *  - 双引擎：优先浏览器内置 Translator API（免费离线），不可用/失败自动回退
 *    POST /api/plugin/page_translate/translate（站点大模型，带 X-CSRF-Token）；
 *  - 译文 localStorage 缓存（按目标语言分桶，二次访问零成本）+ WeakMap 存原文可一键还原；
 *  - SPA 适配：MutationObserver 监听内容变化，翻译态下新增节点自动续译；
 *  - 状态持久化：上次开着的话，下次进入自动翻译。
 */
(function () {
  "use strict";
  var h = window.__vueH;
  if (!h || !window.__pluginRegister) return;

  var API = "/api/plugin/page_translate";
  var LS_ON = "page_translate_on";
  var LS_CACHE_PREFIX = "page_translate_cache:";

  // ---------------- 工具 ----------------
  function readJSON(k, def) {
    try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : def; } catch (e) { return def; }
  }
  function writeJSON(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {}
  }
  function getFlag(k) { try { return localStorage.getItem(k) === "1"; } catch (e) { return false; } }
  function setFlag(k, on) { try { localStorage.setItem(k, on ? "1" : "0"); } catch (e) {} }

  // 浏览器内置 Translator API 用 BCP-47 语言码（zh → zh-Hans / zh-Hant）
  function bcp47(l) {
    l = String(l || "").toLowerCase();
    if (l.indexOf("zh") === 0) {
      return (l.indexOf("tw") >= 0 || l.indexOf("hant") >= 0) ? "zh-Hant" : "zh-Hans";
    }
    return l.split("-")[0] || "en";
  }

  // ---------------- 状态 ----------------
  var state = { on: false, busy: false, error: "", source: "zh", target: "en", llmOn: false, translator: null };
  var renderHook = null;
  function sync() { if (renderHook) try { renderHook(); } catch (e) {} }
  var _applied = 0;        // 累计成功写入的译文条数（用于判断「是否真的有翻成功」）
  var _lastError = "";     // 最近一次翻译错误

  // ---------------- 跳过规则 ----------------
  var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, CODE: 1, PRE: 1, KBD: 1, SAMP: 1,
                    TEXTAREA: 1, INPUT: 1, SELECT: 1, OPTION: 1, SVG: 1, CANVAS: 1, IFRAME: 1, MATH: 1 };
  function shouldSkip(el) {
    if (!el) return true;
    if (SKIP_TAGS[(el.tagName || "").toUpperCase()]) return true;
    if (el.isContentEditable) return true;
    if (el.getAttribute && el.getAttribute("translate") === "no") return true;
    if (el.closest && el.closest("[data-no-translate],.ptr-btn,.plugin-remote")) return true;
    return false;
  }
  function isTranslatable(str) {
    if (!str) return false;
    var t = str.trim();
    if (t.length < 2) return false;
    // 至少含一个中日韩或拉丁字母，否则（纯数字/标点/符号）跳过
    return /[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7afA-Za-z]/.test(t);
  }
  function collectTextNodes(root) {
    var out = [];
    if (!root) return out;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var p = node.parentElement;
        if (!p || shouldSkip(p)) return NodeFilter.FILTER_REJECT;
        if (!isTranslatable(node.nodeValue)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var n;
    while ((n = walker.nextNode())) out.push(n);
    return out;
  }

  // ---------------- 译文缓存（按目标语言分桶） ----------------
  var cacheMap = null, cacheDirty = false, _flushT = null;
  function loadCache() { cacheMap = readJSON(LS_CACHE_PREFIX + state.target, {}) || {}; cacheDirty = false; }
  function getCached(s) { return cacheMap ? cacheMap[s] : undefined; }
  function setCached(s, v) {
    if (!cacheMap || cacheMap[s] === v) return;
    cacheMap[s] = v; cacheDirty = true;
  }
  function flushCacheSoon() {
    if (_flushT) return;
    _flushT = setTimeout(function () {
      _flushT = null;
      if (!cacheDirty || !cacheMap) return;
      var keys = Object.keys(cacheMap);
      // 容量护栏：条目过多时保留最近的一半，避免 localStorage 膨胀
      if (keys.length > 4000) {
        var keep = {};
        for (var i = Math.floor(keys.length / 2); i < keys.length; i++) keep[keys[i]] = cacheMap[keys[i]];
        cacheMap = keep;
      }
      writeJSON(LS_CACHE_PREFIX + state.target, cacheMap);
      cacheDirty = false;
    }, 800);
  }

  // ---------------- 原文备份（还原用） ----------------
  var originals = new WeakMap();

  // ---------------- 引擎 A：浏览器内置 Translator ----------------
  function browserEngine() {
    if (typeof self === "undefined") return null;
    return self.Translator || (self.ai && self.ai.translator) || null;
  }
  async function ensureBrowserTranslator() {
    if (state.translator) return state.translator;
    var T = browserEngine();
    if (!T) return null;
    try {
      var src = bcp47(state.source), tgt = bcp47(state.target);
      if (T.availability) {
        var avail = await T.availability({ sourceLanguage: src, targetLanguage: tgt });
        if (avail === "no" || avail === "unavailable") return null;
      }
      state.translator = await T.create({ sourceLanguage: src, targetLanguage: tgt });
      return state.translator;
    } catch (e) {
      console.warn("[翻译] 浏览器内置翻译器不可用，回退站点大模型：", e);
      return null;
    }
  }
  async function translateBatchBrowser(batch) {
    var tr = await ensureBrowserTranslator();
    if (!tr || typeof tr.translate !== "function") return null;
    var out = [];
    for (var i = 0; i < batch.length; i++) out.push(String(await tr.translate(batch[i])));
    return out;
  }

  // ---------------- 引擎 B：站点大模型（后端兜底） ----------------
  async function getCsrf() {
    try {
      var r = await fetch("/api/csrf", { credentials: "same-origin" });
      var d = await r.json();
      return d.csrf_token || "";
    } catch (e) { return ""; }
  }
  async function translateBatchLLM(batch) {
    var tok = await getCsrf();
    var r = await fetch(API + "/translate", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": tok },
      body: JSON.stringify({ target: state.target, texts: batch })
    });
    if (!r.ok) {
      var msg = "翻译服务暂不可用（" + r.status + "）";
      try { var j = await r.json(); if (j && j.error) msg = j.error; } catch (e) {}
      throw new Error(msg);
    }
    var d = await r.json();
    return Array.isArray(d.translations) ? d.translations : null;
  }

  async function translateBatch(batch) {
    if (browserEngine()) {
      try {
        var b = await translateBatchBrowser(batch);
        if (b && b.length === batch.length) return b;
      } catch (e) { /* 浏览器引擎失败 → 回退 */ }
    }
    return await translateBatchLLM(batch);
  }

  // ---------------- 应用 / 还原 ----------------
  function applyOne(node, translated, src) {
    if (originals.has(node)) return;
    originals.set(node, src);
    node.nodeValue = translated;
    _applied++;
  }
  function restoreAll() {
    var nodes = collectTextNodes(document.body);
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (originals.has(node)) node.nodeValue = originals.get(node);
    }
    originals = new WeakMap();
  }

  // ---------------- 核心：整树增量翻译 ----------------
  var _running = false;
  async function translateTree(root) {
    if (!state.on || _running) return;
    _running = true;
    pauseObserver();
    try {
      var nodes = collectTextNodes(root || document.body);
      var pending = [];
      for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        if (originals.has(node)) continue;
        pending.push({ node: node, key: node.nodeValue.trim() });
      }
      if (!pending.length) return;

      // 先套缓存
      var miss = [], missSeen = Object.create(null);
      for (var k = 0; k < pending.length; k++) {
        var p = pending[k];
        var cv = getCached(p.key);
        if (cv !== undefined) applyOne(p.node, cv, p.node.nodeValue);
        else if (!missSeen[p.key]) { missSeen[p.key] = true; miss.push(p.key); }
      }
      if (!miss.length) { flushCacheSoon(); return; }

      var BATCH = 20;
      for (var s = 0; s < miss.length; s += BATCH) {
        var chunk = miss.slice(s, s + BATCH);
        var res;
        try {
          res = await translateBatch(chunk);
          _lastError = "";
        } catch (e) {
          _lastError = (e && e.message) ? e.message : "翻译失败";
          console.warn("[翻译]", _lastError);
          break;
        }
        if (!res) { _lastError = _lastError || "翻译服务返回空"; break; }
        for (var q = 0; q < chunk.length; q++) {
          if (res[q] !== undefined && res[q] !== null) setCached(chunk[q], String(res[q]));
        }
        // 应用本批
        for (var m = 0; m < pending.length; m++) {
          var pp = pending[m];
          if (originals.has(pp.node)) continue;
          var got = getCached(pp.key);
          if (got !== undefined) applyOne(pp.node, got, pp.node.nodeValue);
        }
      }
      flushCacheSoon();
    } finally {
      _running = false;
      resumeObserver();
    }
  }

  // ---------------- 切换 ----------------
  async function toggle() {
    if (state.busy) return;
    state.busy = true; state.error = ""; _lastError = ""; sync();
    try {
      if (state.on) {
        restoreAll();
        state.on = false; setFlag(LS_ON, false);
      } else {
        if (!browserEngine() && !state.llmOn) {
          state.error = "未配置翻译引擎";
          setTimeout(function () { state.error = ""; sync(); }, 4000);
          return;
        }
        loadCache();
        state.on = true; setFlag(LS_ON, true);
        var before = _applied;
        await translateTree(document.body);
        if (_lastError && _applied === before) {
          // 完全没翻成功 → 回退开关，避免按钮「假装已翻译」
          restoreAll();
          state.on = false; setFlag(LS_ON, false);
          state.error = _lastError;
          setTimeout(function () { state.error = ""; sync(); }, 5000);
        }
      }
    } finally {
      state.busy = false; sync();
    }
  }

  // ---------------- 启动 ----------------
  async function bootstrap() {
    try {
      var r = await fetch(API + "/config", { credentials: "same-origin" });
      var cfg = await r.json();
      state.source = cfg.source || "zh";
      state.target = cfg.target || "en";
      state.llmOn = !!cfg.llm_on;
    } catch (e) {
      state.source = (document.documentElement.getAttribute("lang") || "zh").slice(0, 2) || "zh";
      state.target = state.source === "zh" ? "en" : "zh";
    }
    if (getFlag(LS_ON)) {
      loadCache();
      state.on = true; sync();
      await translateTree(document.body);
    }
  }

  // ---------------- SPA 观察器 ----------------
  var observer = null, _obsT = null;
  function startObserver() {
    if (observer || !state.on) return;
    observer = new MutationObserver(function () {
      if (!state.on) return;
      if (_obsT) clearTimeout(_obsT);
      _obsT = setTimeout(function () { translateTree(document.body); }, 350);
    });
    try { observer.observe(document.body, { childList: true, subtree: true, characterData: true }); } catch (e) {}
  }
  function pauseObserver() { if (observer) { try { observer.disconnect(); } catch (e) {} } }
  function resumeObserver() { if (observer && state.on) { try { observer.observe(document.body, { childList: true, subtree: true, characterData: true }); } catch (e) {} } }

  // ---------------- 样式 ----------------
  function injectStyle() {
    if (document.getElementById("ptr-style")) return;
    var st = document.createElement("style");
    st.id = "ptr-style";
    st.textContent =
      ".ptr-btn{position:fixed;left:16px;bottom:16px;z-index:60;display:inline-flex;align-items:center;gap:6px;" +
      "padding:8px 12px;border-radius:999px;border:1px solid var(--border-color,#e5e5e5);" +
      "background:var(--card-bg,#fff);color:var(--fg,#333);font-size:13px;line-height:1;cursor:pointer;" +
      "box-shadow:0 4px 14px rgba(0,0,0,.12);transition:transform .15s ease,opacity .15s ease;opacity:.92}" +
      ".ptr-btn:hover{opacity:1;transform:translateY(-1px);border-color:var(--accent,#1a73e8)}" +
      ".ptr-btn.is-on{background:var(--accent,#1a73e8);color:#fff;border-color:var(--accent,#1a73e8)}" +
      ".ptr-btn.is-busy{cursor:progress;opacity:.7}" +
      ".ptr-btn.is-err{border-color:#d9534f;color:#d9534f}" +
      "@media(max-width:520px){.ptr-btn{left:10px;bottom:10px;padding:7px 10px;font-size:12px}}";
    document.head.appendChild(st);
  }

  // ---------------- Vue 组件（h 渲染函数，不依赖模板编译器） ----------------
  var Comp = {
    data: function () { return { on: false, busy: false, label: "翻译整页", err: false }; },
    methods: {
      refresh: function () {
        this.on = state.on;
        this.busy = state.busy;
        this.err = !!state.error;
        this.label = state.busy ? "翻译中…" : (state.error ? state.error : (state.on ? "显示原文" : "翻译整页"));
      },
      click: function () { var s = this; toggle().then(function () { s.refresh(); }, function () { s.refresh(); }); }
    },
    render: function () {
      return h("button", {
        class: ["ptr-btn", this.on ? "is-on" : "", this.busy ? "is-busy" : "", this.err ? "is-err" : ""],
        type: "button",
        title: this.on ? "显示原文" : "把整页翻译成另一种语言",
        "data-no-translate": "1",
        onClick: this.click
      }, this.label);
    },
    mounted: function () {
      var self = this;
      renderHook = function () { self.refresh(); };
      self.refresh();
      injectStyle();
      startObserver();
      bootstrap().then(function () { self.refresh(); startObserver(); },
                       function () { self.refresh(); });
    },
    unmounted: function () {
      renderHook = null;
      pauseObserver();
      observer = null;
    }
  };

  window.__pluginRegister("page_translate_widget", Comp);
})();
