<template>
  <div class="container dev-page">
    <h1 class="page-title">📘 小游戏接入文档</h1>
    <p class="lead">欢迎为本站开发轻量、原创的 HTML5 解压小游戏。你的作品将进入「游戏厅」，
      以卡片展示、点击即玩，运行在安全沙箱内。本页是完整接入指南。</p>

    <h2>一、交付物：一个 zip 游戏包</h2>
    <p>把游戏打包成 <code>zip</code>，包内须含 <code>manifest.json</code>（根目录），
      其余为 HTML/CSS/JS/图片/音频等静态资源。</p>
    <pre class="codeblock">bubble-pop.zip
├── manifest.json      # 必填：元数据
├── index.html         # 入口（entry 指向它）
├── style.css
└── game.js</pre>

    <h3>manifest.json 字段</h3>
    <table class="doc-table">
      <thead><tr><th>字段</th><th>必填</th><th>说明</th></tr></thead>
      <tbody>
        <tr><td>name</td><td>是</td><td>游戏名（≤120 字符）</td></tr>
        <tr><td>entry</td><td>是</td><td>入口文件相对路径，如 index.html（仅允许 html）</td></tr>
        <tr><td>description</td><td>否</td><td>一句话介绍，展示在卡片上</td></tr>
        <tr><td>cover</td><td>否</td><td>封面图相对路径（建议 16:9；缺省用标题首字占位）</td></tr>
        <tr><td>author</td><td>否</td><td>作者署名</td></tr>
        <tr><td>version</td><td>否</td><td>版本号，如 1.0</td></tr>
      </tbody>
    </table>
    <pre class="codeblock">{
  "name": "泡泡减压",
  "entry": "index.html",
  "description": "戳泡泡，看涟漪，放松 30 秒。",
  "author": "llhhy",
  "version": "1.0"
}</pre>

    <h2>二、安全红线（上传前请自检）</h2>
    <ul class="rules">
      <li>✅ 允许：Canvas/DOM/CSS 动画、本地合成音效（WebAudio）、离线运行；纯原创素材。</li>
      <li>❌ 禁止读取/外传任何数据：不读 cookie/localStorage，不 <code>fetch</code> 外站，不开 WebSocket。</li>
      <li>❌ 禁止 <code>eval</code>/<code>new Function</code>/超长 base64 混淆等可疑写法（会被静态扫描标记）。</li>
      <li>❌ 禁止引用远程脚本/字体/图片（CSP 只放行本包资源）。</li>
      <li>❌ 禁止 <code>window.parent</code> / <code>top.</code> 访问父页面。</li>
      <li>⚠️ 平台会先跑静态扫描（11 条规则打分），配置大模型后可再执行一轮 LLM 代码审计；通过站长审核才上架。</li>
    </ul>

    <h2>三、运行沙箱（你无需写任何特殊代码）</h2>
    <p>游戏在 <code>&lt;iframe sandbox="allow-scripts"&gt;</code> 内播放，且每个资源都带
      <code>CSP: sandbox allow-scripts; connect-src 'none'; …</code> 响应头。因此你的游戏是「与世隔绝」的：
      拿不到本站任何凭据，也无法影响主站；请把游戏写成完全自包含。</p>

    <h2>四、给手机玩家的建议（强烈推荐）</h2>
    <ul class="rules">
      <li>竖屏优先：默认用 <code>touch</code>/<code>pointer</code> 事件，适配 <code>@media (pointer: coarse)</code>。</li>
      <li><code>&lt;meta name="viewport" content="width=device-width, initial-scale=1"&gt;</code> 并处理 <code>devicePixelRatio</code>。</li>
      <li>body 上加 <code>touch-action: none</code>，避免滑动触发浏览器手势。</li>
      <li>勿依赖键盘/悬停；时长控制在「碎片放松」级（30 秒～3 分钟一局更受欢迎）。</li>
    </ul>

    <h2>五、提交流程</h2>
    <ol class="rules">
      <li>本地自测：直接双击打开 <code>index.html</code> 也能跑（说明自包含 OK）。</li>
      <li>打包成 zip → 交给站长：站长在后台「游戏收录」上传。</li>
      <li>系统自动：安全解包 → manifest 校验 → 静态扫描打分。</li>
      <li>站长审核（可触发大模型代码审计）→ 上架 → 出现在「游戏厅」。</li>
    </ol>

    <h2>六、常见问题</h2>
    <p><strong>Q：能联网吗？</strong>不能。CSP <code>connect-src 'none'</code>，保证不产生任何外联。</p>
    <p><strong>Q：能保存最高分吗？</strong>当前沙箱禁止读本站存储。可以先做纯放松玩法；
      后续平台会提供 <code>postMessage</code> 成绩桥（届时另行开放，需过审）。</p>
    <p><strong>Q：会被抄袭/侵权吗？</strong>平台要求全部素材与玩法原创；如有抄袭经查实将下架。</p>
    <p><strong>Q：包大小限制？</strong>zip ≤ 20MB，解压 ≤ 60MB，文件 ≤ 200 个；类型仅允许常见 web 资源白名单。</p>
  </div>
</template>

<script setup></script>

<style scoped>
.dev-page { line-height: 1.75; padding-bottom: 40px; }
.lead { color: #666; }
.dev-page h2 { margin: 26px 0 10px; font-size: 20px; border-left: 4px solid var(--accent, #1a73e8); padding-left: 10px; }
.dev-page h3 { margin: 18px 0 6px; font-size: 16px; }
.codeblock {
  background: #1e1e1e; color: #dcdcdc; padding: 12px 14px; border-radius: 8px;
  overflow-x: auto; font-size: 13px; line-height: 1.6;
}
.doc-table { border-collapse: collapse; width: 100%; margin: 10px 0; }
.doc-table th, .doc-table td { border: 1px solid #ddd; padding: 7px 10px; font-size: 14px; text-align: left; }
.rules { padding-left: 20px; }
.rules li { margin: 5px 0; }
.dev-page code { background: rgba(127,127,127,.15); padding: 1px 6px; border-radius: 4px; font-size: 13px; }
</style>
