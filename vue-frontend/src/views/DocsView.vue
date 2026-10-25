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
        <div v-for="sec in visibleSections" :key="sec.title" class="nav-section">
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
      <!-- ============ 通用约定 ============ -->
      <div id="common" class="doc-section">
        <h1>通用约定</h1>
        <p>
          本文档覆盖 llhhy-blog 的<strong>前台接口</strong>（数据读取、互动、订阅、认证、系统）与 SSR 页面，
          当前版本 <strong>{{ appVersion || '—' }}</strong>
          <span class="p-note">（取自 <code>GET /api/health</code>，随运行中的后端实时变化，不写死）</span>。
          前端（<code>vue-frontend/src/lib/api.js</code>）与站内页面共用这些接口；你可以用它们自定义客户端、App 或第三方集成。
        </p>
        <p class="coverage">
          另有<strong>管理类接口</strong>（<code>/api/mobile/*</code>，74 条）与<strong>分享卡 / 壳页</strong>（<code>/api/og/*</code>）
          不在下面逐条展开，概览见 <a href="#more" @click.prevent="scrollTo('more')">其他接口</a>
          —— 完整清单以仓库 <code>myblog/API.md</code> 为准。
        </p>

        <h3>基地址与返回格式</h3>
        <ul>
          <li>所有 JSON 接口前缀为 <code>/api</code>，例如 <code>POST /api/auth/login</code>。</li>
          <li>成功返回 <code>200</code>（创建类常返回 <code>201</code>），响应体为 JSON。</li>
          <li>列表类统一用 <code>items</code> 字段承载数组，并附带 <code>page / pages / total / per_page</code>。</li>
          <li>错误统一返回 JSON：<code>{"error": "原因"}</code>，状态码见各端点与末尾错误码表。</li>
        </ul>
        <pre><code class="json">// 成功（列表类）
{ "items": [ ... ], "page": 1, "pages": 3, "total": 20, "per_page": 8 }
// 成功（操作类）
{ "ok": true, "likes": 12 }
// 失败
{ "error": "CSRF 校验失败，请刷新页面后重试" }</code></pre>

        <h3>鉴权级别</h3>
        <table class="params-table">
          <thead><tr><th>级别</th><th>说明</th><th>未满足时的返回</th></tr></thead>
          <tbody>
            <tr><td><span class="auth auth-public">公开</span></td><td>无需登录即可访问</td><td>—</td></tr>
            <tr><td><span class="auth auth-login">登录</span></td><td>需登录（会话 Cookie）</td><td><code>401 {"error":"请先登录"}</code></td></tr>
            <tr><td><span class="auth auth-admin">超管</span></td><td>仅超级管理员</td><td><code>403</code></td></tr>
          </tbody>
        </table>

        <h3>CSRF 防护</h3>
        <ul>
          <li>仅对<strong>写操作</strong>（POST / PUT / DELETE / PATCH）生效，GET 豁免。</li>
          <li>流程：先 <code>GET /api/csrf</code> 取 token，再在写请求头带 <code>X-CSRF-Token: &lt;token&gt;</code>。</li>
          <li>前端 <code>apiPost()</code> 已自动处理，无需手写。</li>
          <li>豁免白名单（写操作无需 token）：<code>/api/webhook/deploy</code>、<code>/api/captcha</code>、<code>/api/captcha/verify</code>、<code>/api/stats/read</code>、<code>/api/stats/visit</code>、<code>/api/stats/search</code>。</li>
          <li>缺失/错误 token 返回 <code>403 {"error":"CSRF 校验失败，请刷新页面后重试"}</code>。</li>
        </ul>
        <pre><code class="bash"># 1) 取 token
curl http://your-domain.com/api/csrf
# {"csrf_token":"xxxx"}

# 2) 带 token 写操作
curl -X POST http://your-domain.com/api/post/my-post/like \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: xxxx" \
  -b cookies.txt \
  -d '{}'</code></pre>

        <h3>分页</h3>
        <p>列表类接口统一支持 <code>?page=&lt;页码&gt;</code>（从 1 开始）与 <code>?per_page=&lt;每页条数&gt;</code>（默认 8，最大 100）。</p>

        <h3>限流</h3>
        <p>部分写接口有限流（<code>utils.rate_limit</code>），超限返回 <code>429</code>。常见阈值：登录 5 次/分、动态发布 5 次/分、评论 10 条/分、点赞 20 次/分（单篇）、搜索记录 120 次/时、阅读记录 60 次/分。</p>
      </div>

      <!-- ============ 认证 ============ -->
      <div id="auth" class="doc-section">
        <h1>认证 Auth</h1>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/auth/register</span><span class="auth auth-public">公开</span></div>
        <p>注册。站点未开启注册时返回 <code>403</code>。</p>
        <table class="params-table"><thead><tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr></thead><tbody>
          <tr><td>username</td><td>string</td><td>是</td><td>用户名</td></tr>
          <tr><td>password</td><td>string</td><td>是</td><td>密码</td></tr>
        </tbody></table>
        <pre><code class="bash">curl -X POST http://your-domain.com/api/auth/register \
  -H "Content-Type: application/json" -d '{"username":"alice","password":"secret"}'</code></pre>
        <p>成功 <code>201 {"ok":true,"message":"注册成功，请登录"}</code>；失败 <code>400 {"error":"..."}</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/auth/login</span><span class="auth auth-public">公开</span></div>
        <p>登录（失败统一延迟 1s 防枚举）。成功后返回 <code>csrf_token</code>，前端立即更新缓存。</p>
        <pre><code class="bash">curl -X POST http://your-domain.com/api/auth/login \
  -H "Content-Type: application/json" -c cookies.txt \
  -d '{"username":"admin","password":"your-password"}'</code></pre>
        <p>成功 <code>200 {"ok":true,"user":{...},"csrf_token":"..."}</code>；失败 <code>401 {"error":"用户名或密码错误"}</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/auth/logout</span><span class="auth auth-public">公开</span></div>
        <p>登出（已登录则清除会话）。成功 <code>200 {"ok":true}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/auth/me</span><span class="auth auth-login">登录</span></div>
        <p>当前用户。成功 <code>200 {"user":{...}}</code>；未登录 <code>200 {"user":null}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/csrf</span><span class="auth auth-public">公开</span></div>
        <p>取 CSRF Token。成功 <code>200 {"csrf_token":"..."}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/captcha/config</span><span class="auth auth-public">公开</span></div>
        <p>验证码配置快照。<code>200 {"global_enabled":true,"pil_available":true,"scenes":{"register":true,"comment":true,"guestbook":true}}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/captcha</span><span class="auth auth-public">公开</span></div>
        <p>图形验证码（CSRF 豁免）。已启用返回 PNG；未启用/不可用返回 <code>404</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/captcha/verify</span><span class="auth auth-public">公开</span></div>
        <p>提交验证码。请求体 <code>{"captcha":"文本"}</code>。成功 <code>200 {"ok":true}</code>（一次性票据，后续注册/评论/留言免再验证）；失败 <code>400 {"error":"验证码错误"}</code>。</p>
      </div>

      <!-- ============ 站点 ============ -->
      <div id="site" class="doc-section">
        <h1>站点 Site</h1>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/site</span><span class="auth auth-public">公开</span></div>
        <p>站点全局配置。成功 <code>200 {"site_name":"...","about_content":"...","allow_register":true,"announcements":[...]}</code> 等。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/links</span><span class="auth auth-public">公开</span></div>
        <p>友情链接列表。<code>200 [{"name":"...","url":"...","description":"..."}, ...]</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/link-apply</span><span class="auth auth-public">公开</span></div>
        <p>友链自助申请。请求体 <code>{"name","url","description"}</code>。成功 <code>200 {"ok":true}</code>；失败 <code>400</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/announcements</span><span class="auth auth-public">公开</span></div>
        <p>公告列表。<code>200 [{"id":1,"content":"...","created_at":"YYYY-MM-DD HH:MM"}, ...]</code>。</p>
      </div>

      <!-- ============ 文章 ============ -->
      <div id="posts" class="doc-section">
        <h1>文章 Posts</h1>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/posts</span><span class="auth auth-public">公开</span></div>
        <p>文章列表（分页 + 筛选）。查询参数 <code>page</code>、<code>per_page</code>、<code>category=&lt;slug&gt;</code>、<code>tag=&lt;slug&gt;</code>、<code>q=&lt;关键词&gt;</code>。</p>
        <pre><code class="bash">curl "http://your-domain.com/api/posts?page=1&amp;per_page=10"</code></pre>
        <pre><code class="json">{
  "items": [
    { "slug":"test-post", "title":"测试文章", "summary":"摘要",
      "created_at":"2026-08-27 12:00", "category":{"name":"技术","slug":"tech"},
      "tags":[{"name":"Vue","slug":"vue"}], "views":100, "likes":5,
      "word_count":1200, "reading_minutes":5, "reward_enabled":false, "is_private":false }
  ],
  "page":1, "pages":3, "total":20, "per_page":8
}</code></pre>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/post/:slug</span><span class="auth auth-public">公开</span></div>
        <p>文章详情。<strong>评论内嵌在此接口</strong>（字段 <code>comments</code>），无独立「评论列表」接口。未发布/定时未到/私密文章：未登录 <code>404</code>，登录且超管可见。</p>
        <pre><code class="json">{
  "slug":"test-post", "title":"测试文章",
  "html":"&lt;p&gt;正文 HTML...&lt;/p&gt;",
  "word_count":1200, "reading_minutes":5, "reward_enabled":false, "is_private":false,
  "series": null,
  "comments": [ { "id":1, "author":"张三", "content":"不错", "created_at":"2026-08-27 13:00", "region":"", "device":"", "parent_id":0, "reply_to":"", "likes":0 } ]
}</code></pre>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/categories</span><span class="auth auth-public">公开</span></div>
        <p><code>200 [{"name":"技术","slug":"tech","count":5}, ...]</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/tags</span><span class="auth auth-public">公开</span></div>
        <p><code>200 [{"name":"Vue","slug":"vue","count":3}, ...]</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/hot-tags</span><span class="auth auth-public">公开</span></div>
        <p>热门标签。查询参数 <code>limit</code>（默认 20，最大 50）。<code>200 [{"name":"...","slug":"...","count":N,"views":N}, ...]</code>（按文章数排序取前 N）。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/category/:slug</span><span class="auth auth-public">公开</span></div>
        <p>分类下文章。支持 <code>page</code>/<code>per_page</code>。返回 <code>{"items":[...],"category":{...},"page":1,"pages":N}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/tag/:slug</span><span class="auth auth-public">公开</span></div>
        <p>标签下文章。返回结构同上。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/rss/category/:slug</span><span class="auth auth-public">公开</span></div>
        <p>分类 RSS。<code>200</code>，<code>Content-Type: application/rss+xml</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/rss/tag/:slug</span><span class="auth auth-public">公开</span></div>
        <p>标签 RSS。同上。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/archive</span><span class="auth auth-public">公开</span></div>
        <p>归档。<code>200 [{"year":2026,"months":[{"month":1,"count":3}], ...}, ...]</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/post/:slug/like</span><span class="auth auth-public">公开</span></div>
        <p>点赞（计数 +1，带限流防刷）。需 CSRF Token。</p>
        <pre><code class="bash">curl -X POST http://your-domain.com/api/post/test-post/like \
  -H "X-CSRF-Token: xxxx" -b cookies.txt -d '{}'</code></pre>
        <p>成功 <code>200 {"likes":N}</code>；文章不存在 <code>404</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/post/:slug/comment</span><span class="auth auth-public">公开</span></div>
        <p>发表评论（开启评论登录则需登录；开启验证码则需先 <code>/api/captcha/verify</code>）。需 CSRF Token。请求体 <code>{"content":"...","author":"昵称(可选)","parent_id":0,"reply_to":"","captcha":"文本(可选)"}</code>。</p>
        <pre><code class="bash">curl -X POST http://your-domain.com/api/post/test-post/comment \
  -H "Content-Type: application/json" -H "X-CSRF-Token: xxxx" -b cookies.txt \
  -d '{"content":"写得真好","author":"路人"}'</code></pre>
        <p>成功 <code>201 {"ok":true,"comment":{...},"pending":false}</code>；未登录被拒 <code>401</code>；验证码未过 <code>400</code>；含屏蔽词 <code>400</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/post/:slug/related</span><span class="auth auth-public">公开</span></div>
        <p>相关文章（同标签/同分类）。<code>200 {"items":[PostCard...]}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/post/:slug/also-viewed</span><span class="auth auth-public">公开</span></div>
        <p>「看了又看」协同过滤推荐。<code>200 {"items":[PostCard...]}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/search</span><span class="auth auth-public">公开</span></div>
        <p>全文搜索。查询参数 <code>q</code>、<code>page</code>、<code>per_page</code>。FTS5 优先，不可用时自动降级 LIKE。<code>200 {"items":[...],"page":1,"pages":N,"total":N}</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/post/:id/publish-now</span><span class="auth auth-admin">超管</span></div>
        <p>立即发布定时文章。成功 <code>200 {"ok":true}</code>；无权限 <code>403</code>。</p>
      </div>

      <!-- ============ 统计 ============ -->
      <div id="stats" class="doc-section">
        <h1>统计 Stats</h1>
        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/stats/visit</span><span class="auth auth-public">公开</span></div>
        <p>上报访问（CSRF 豁免）。请求体 <code>{"path":"/..."}</code>。成功 <code>200 {"ok":true}</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/stats/search</span><span class="auth auth-public">公开</span></div>
        <p>记录搜索词（CSRF 豁免，120 次/时限流）。请求体 <code>{"keyword":"..."}</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/stats/read</span><span class="auth auth-public">公开</span></div>
        <p>记录文章阅读（CSRF 豁免，60 次/分限流）。请求体 <code>{"slug":"..."}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/stats/summary</span><span class="auth auth-public">公开</span></div>
        <p>统计汇总。<code>200 {"views":N,"visitors":N,"region_top":[...],"hot_posts":[...],"hot_queries":[...],"hourly_dist":[...],"trend":[...]}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/stats/trend</span><span class="auth auth-public">公开</span></div>
        <p>访客趋势。查询参数 <code>days</code>（默认 7）。<code>200 [{"date":"YYYY-MM-DD","pv":N,"uv":N}, ...]</code>。</p>
      </div>

      <!-- ============ 社交广场 ============ -->
      <div id="social" class="doc-section">
        <h1>社交广场 Social</h1>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/moments</span><span class="auth auth-public">公开</span></div>
        <p>微动态列表。支持 <code>page</code>/<code>per_page</code>。<code>200 {"items":[{"id","author","content","likes","comments":[...],"created_at"}],"page":1,"pages":N}</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/moment</span><span class="auth auth-login">登录</span></div>
        <p>发布微动态（5 次/分限流，纯文本存储）。请求体 <code>{"content":"..."}</code>。成功 <code>201 {"ok":true,"moment":{...}}</code>；未登录 <code>401</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/moment/:id/like</span><span class="auth auth-login">登录</span></div>
        <p>微动态点赞。成功 <code>200 {"ok":true}</code>；未登录 <code>401</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/moment/:id/comment</span><span class="auth auth-public">公开</span></div>
        <p>微动态评论。请求体 <code>{"content":"...","nickname":"可选"}</code>。成功 <code>201 {"ok":true,"comment":{...}}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/feed/circle</span><span class="auth auth-public">公开</span></div>
        <p>博客圈（聚合友链 RSS，15 分钟缓存 + SSRF 防护）。查询参数 <code>refresh=1</code> 强制刷新。v3.8.6 起响应新增 <code>debug</code> 字段（自诊断信息：友链总数/已填 RSS/抓取/跳过/原因），便于排查「空白」问题。</p>
        <pre><code class="bash">curl "http://your-domain.com/api/feed/circle"</code></pre>
        <pre><code class="json">{
  "items": [ { "title":"友链文章","link":"https://example.com/p/1","source":"友链名","published":"..." } ],
  "debug": { "total_links":3, "links_with_rss":1, "feedparser_ok":true, "fetched":1, "skipped":2, "notes":["跳过友链「B」：RSS 地址未过安全校验"] }
}</code></pre>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/social-accounts</span><span class="auth auth-public">公开</span></div>
        <p>作者社交账号墙。<code>200 [{"platform":"github","text":"...","url":"..."}, ...]</code>。</p>
      </div>

      <!-- ============ 专题 ============ -->
      <div id="series" class="doc-section">
        <h1>专题 Series</h1>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/series</span><span class="auth auth-public">公开</span></div>
        <p>专题列表。<code>200 {"items":[{"id","name","slug","description","post_count","updated_at"}],"page":1,"pages":N}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/series/:slug</span><span class="auth auth-public">公开</span></div>
        <p>专题详情（含本系列文章与「本系列热门标签」）。<code>200 {"series":{...},"posts":[PostCard...]}</code>；不存在 <code>404</code>。</p>
      </div>

      <!-- ============ 留言墙 ============ -->
      <div id="guestbook" class="doc-section">
        <h1>留言墙 Guestbook</h1>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/guestbook</span><span class="auth auth-public">公开</span></div>
        <p>留言列表。支持 <code>page</code>/<code>per_page</code>。<code>200 {"items":[{"id","author","content","likes","region","device","created_at"}],"page":1,"pages":N,"total":N}</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/guestbook</span><span class="auth auth-public">公开</span></div>
        <p>发表留言（开启验证码则需先 <code>/api/captcha/verify</code>）。请求体 <code>{"content":"...","author":"昵称(可选)"}</code>。成功 <code>201 {"ok":true}</code>；验证码未过 <code>400</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/guestbook/:id/like</span><span class="auth auth-public">公开</span></div>
        <p>留言点赞。成功 <code>200 {"ok":true,"likes":N}</code>；不存在 <code>404</code>。</p>
      </div>

      <!-- ============ 订阅 ============ -->
      <div id="subscribe" class="doc-section">
        <h1>订阅 Subscribe</h1>
        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/subscribe</span><span class="auth auth-public">公开</span></div>
        <p>邮件订阅（需验证码校验）。请求体 <code>{"email":"user@example.com"}</code>。成功 <code>200 {"ok":true,"message":"订阅成功，请查收确认邮件"}</code>；重复 <code>200 {"ok":true,"message":"你已经订阅啦"}</code>。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/unsubscribe</span><span class="auth auth-public">公开</span></div>
        <p>退订。参数/请求体 <code>{"email":"...","token":"退订令牌"}</code>。成功 <code>200 {"ok":true,"message":"已退订"}</code>；令牌无效 <code>400</code>。</p>
      </div>

      <!-- ============ 通知 ============ -->
      <div id="notifications" class="doc-section">
        <h1>通知 Notifications</h1>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/notifications</span><span class="auth auth-login">登录</span></div>
        <p>通知列表。<code>200 {"items":[{"id","content","link","read","created_at"}],"unread":N}</code>；未登录 <code>401</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/notification/:id/read</span><span class="auth auth-login">登录</span></div>
        <p>标记单条已读。成功 <code>200 {"ok":true}</code>；非本人通知 <code>404</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/notifications/read-all</span><span class="auth auth-login">登录</span></div>
        <p>全部标记已读。成功 <code>200 {"ok":true}</code>。</p>
      </div>

      <!-- ============ 系统 ============ -->
      <div id="system" class="doc-section">
        <h1>系统 System</h1>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/health</span><span class="auth auth-public">公开</span></div>
        <p>
          健康探活。<code>200 {"ok":true,"version":"{{ appVersion || '…' }}","db":"up"}</code>；
          数据库不可用返回 <code>503</code>（此时 <code>"db":"down"</code>）。
          <span class="p-note">本页顶栏显示的版本号就取自这里 —— 之前它写死在模板里，已经落后好几个版本。</span>
        </p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/version/check</span><span class="auth auth-login">登录</span></div>
        <p>检测新版本。<code>200 {"latest":"v{{ appVersion || '…' }}","current":"v{{ appVersion || '…' }}","has_update":false}</code>（对比 GitHub latest tag 与本地 <code>APP_VERSION</code>）。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/version/update</span><span class="auth auth-admin">超管</span></div>
        <p>触发在线更新。成功 <code>200 {"ok":true,"message":"更新已触发，服务器将自动重启"}</code>（异步执行 <code>update.sh</code>）。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/version/status</span><span class="auth auth-admin">超管</span></div>
        <p>更新状态（后台轮询）。<code>200 {"status":"idle|running|done","message":"..."}</code>；无权限 <code>403</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/webhook/deploy</span><span class="auth auth-public">公开</span></div>
        <p>部署 Webhook（CSRF 豁免，但需密钥鉴权）。请求头 <code>X-Deploy-Secret: &lt;与配置相同的密钥&gt;</code>。成功 <code>200 {"ok":true,"message":"部署已触发"}</code>；密钥错误 <code>401</code>。</p>
      </div>

      <!-- ============ 其他接口（分享卡 / 壳页 / 管理类） ============ -->
      <div id="more" class="doc-section">
        <h1>其他接口 More</h1>
        <p>
          下面三组不在「数据接口」范围内，但同样对外开放。<strong>逐条清单以仓库 <code>myblog/API.md</code> 为准</strong>，
          这里只给入口与边界条件 —— 写全 74 条管理接口会让本页变成没人读的清单。
        </p>

        <h3>分享卡与社交图</h3>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/og/post/:slug</span><span class="auth auth-public">公开</span></div>
        <p>
          文章分享卡的服务端壳页（社交平台抓取 <code>og:*</code> 用）。附加 <code>?seo=1</code> 走爬虫通道；
          响应头恒为 <code>Cache-Control: no-store</code> —— 壳页与前端 SPA 共用同一个 URL，
          一旦允许中间层缓存，真人就会拿到没有样式的壳页（v4.10.1 的真实事故）。
        </p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/og/post/:slug.png</span><span class="auth auth-public">公开</span></div>
        <p>
          动态生成文章分享卡 PNG。配色与版式取自后台「主题美化 / 分享卡」设置（<strong>没有查询参数</strong>）；
          按 <code>slug + 更新时间 + 主题色</code> 落盘缓存；文章不可见或绘制失败时回退默认图，不会 500。
        </p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/qr?url=…</span><span class="auth auth-public">公开</span></div>
        <p>
          站点二维码，输出 SVG。<strong>只接受本站 URL</strong>（<code>site_url</code> 前缀或站内相对路径），
          否则本接口就成了公共二维码生成器、可给钓鱼链接批量做码；限流 60 秒 / 30 次。
        </p>

        <h3>列表页壳页</h3>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/og/page/&lt;path&gt;</span><span class="auth auth-public">公开</span></div>
        <p>
          归档 / 分类 / 标签 / 系列 / 关于 / 友链的爬虫可见版本，带真实文章列表与 <code>CollectionPage</code> JSON-LD。
          只认上述路径，<strong>其余一律 404 + noindex</strong>（不兜底成通用页）；可见性口径与前台一致。
        </p>

        <h3>自检</h3>
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/seo/shell-check?slug=…</span><span class="auth auth-public">公开</span></div>
        <p>
          爬虫通道自检：用不同 UA 直接调壳页逻辑（进程内直调，<strong>零出网</strong>），
          返回每个 UA 会被判定成「壳页 / 重定向 / 隔离」以及原因。它在用户本机跑，
          所以能改代码解决；<em>nginx 有没有配好</em>不归它管，那层靠 <code>deploy_guide.md</code> 里的 curl 核验。
        </p>

        <h3>管理类接口 <code>/api/mobile/*</code></h3>
        <p>
          共 <strong>74</strong> 条，供原生 App / 脚本调用，<strong>全部需要登录会话</strong>，权限逐条对齐后台对应页面
          （写操作另有超管限制）。分组：
        </p>
        <table class="params-table">
          <thead><tr><th>分组</th><th>前缀</th><th>说明</th></tr></thead>
          <tbody>
            <tr><td>概览与统计</td><td><code>/mobile/overview</code> <code>/mobile/stats</code> <code>/mobile/taxonomy</code></td><td>后台首页指标与分类法（分类 / 标签 / 系列一起返回）</td></tr>
            <tr><td>文章</td><td><code>/mobile/post*</code></td><td>列表 / 详情 / 新建 / 编辑 / 发布 / 撤下 / 置顶 / 移入回收站</td></tr>
            <tr><td>版本历史</td><td><code>/mobile/post/:id/history*</code></td><td>历次快照、单次详情、版本 diff、回滚</td></tr>
            <tr><td>回收站</td><td><code>/mobile/trash*</code></td><td>列表 / 还原 / 彻底删除</td></tr>
            <tr><td>评论</td><td><code>/mobile/comment*</code></td><td>列表、单条审核、批量审核、全部标记已读</td></tr>
            <tr><td>访客与风控</td><td><code>/mobile/visit-logs</code> <code>/mobile/blocked</code> <code>/mobile/ip/*</code></td><td>访客日志、拦截名单、IP 封禁 / 解封</td></tr>
            <tr><td>内容分区</td><td><code>/mobile/{category,tag,series}*</code></td><td>分类 / 标签（含合并）/ 系列的增删改</td></tr>
            <tr><td>社交与留言</td><td><code>/mobile/{moments,guestbook,link-application}*</code></td><td>微动态、留言墙、友链申请审批</td></tr>
            <tr><td>公告与订阅</td><td><code>/mobile/announcement*</code> <code>/mobile/subscriber*</code></td><td>公告增删改与上下线、订阅者启用 / 删除</td></tr>
            <tr><td>友链</td><td><code>/mobile/link*</code></td><td>增删改与排序</td></tr>
            <tr><td>媒体</td><td><code>/mobile/upload</code> <code>/mobile/media*</code></td><td>上传、媒体库列表、删除</td></tr>
            <tr><td>数据与设置</td><td><code>/mobile/{stats/report,audit-logs,backups,settings,seo/summary,cert,users}</code></td><td>只读为主；唯一写操作是 <code>POST /mobile/user/:id/role</code>（改角色）</td></tr>
          </tbody>
        </table>
        <p class="p-note">
          邮箱等个人信息在返回时已遮敏；审计日志不返回 <code>payload</code>；站点设置只返回白名单键。
        </p>
      </div>

      <!-- ============ SSR 页面 / 源 ============ -->
      <div id="pages" class="doc-section">
        <h1>SSR 页面与订阅源</h1>
        <p>以下为服务端渲染（SSR）页面与标准订阅源，可直接在浏览器访问或用于 SEO / 抓取。</p>
        <table class="params-table">
          <thead><tr><th>路径</th><th>说明</th></tr></thead>
          <tbody>
            <tr><td><code>/</code></td><td>首页</td></tr>
            <tr><td><code>/post/:slug</code></td><td>文章详情页（SSR，含评论表单）</td></tr>
            <tr><td><code>/post/:slug/like</code> (POST)</td><td>SSR 点赞入口（同 <code>/api/post/:slug/like</code>，需 CSRF）</td></tr>
            <tr><td><code>/category/:slug</code></td><td>分类页</td></tr>
            <tr><td><code>/tag/:slug</code></td><td>标签页</td></tr>
            <tr><td><code>/search</code></td><td>搜索页</td></tr>
            <tr><td><code>/archive</code></td><td>归档页</td></tr>
            <tr><td><code>/about</code></td><td>关于页</td></tr>
            <tr><td><code>/links</code></td><td>友链页</td></tr>
            <tr><td><code>/feed.xml</code></td><td>全站 RSS 2.0 订阅源</td></tr>
            <tr><td><code>/sitemap.xml</code></td><td>站点地图</td></tr>
            <tr><td><code>/robots.txt</code></td><td>爬虫协议</td></tr>
          </tbody>
        </table>
      </div>

      <!-- ============ 二次开发指南 ============ -->
      <div id="devguide" class="doc-section">
        <h1>二次开发指南</h1>
        <p>llhhy-blog 后端是标准 Flask 应用，API 按功能拆成蓝图（Blueprint）包；前端是 Vue 3 SPA。下面演示如何在不改动核心代码的前提下，新增你自己的接口与页面。</p>

        <h3>1. 项目结构（API 在哪）</h3>
        <pre><code class="bash">myblog/
├── app.py              # 应用工厂、CSRF before_request、蓝图注册
├── config.py           # APP_VERSION 等配置
├── api/
│   ├── __init__.py     # api_bp 聚合导出（功能模块在此登记）
│   ├── common.py       # 共享辅助（api_bp、db、当前用户、序列化、CSRF 工具）
│   ├── auth.py  site.py  posts.py  stats.py  social.py
│   ├── series.py  guestbook.py  subscribe.py  notifications.py  system.py
├── models.py           # SQLAlchemy 模型
├── utils.py            # rate_limit / render_markdown / check_csrf_token ...
└── stats.py            # 独立的统计模块（本模块内显式 import）</code></pre>

        <h3>2. 新增一个后端 API（完整步骤）</h3>
        <p>① 新建模块 <code>myblog/api/bookmark.py</code>（或归入已有模块）；② 从 <code>.common</code> 取共享符号写路由；③ 若是新模块，在 <code>api/__init__.py</code> 追加一行 <code>from . import bookmark</code>；④ 共享逻辑一律放 <code>common.py</code>，<strong>模块间不要互相 import</strong>（避免循环依赖）。</p>
        <pre><code class="python"># myblog/api/bookmark.py
from .common import api_bp, db, _current_user_or_none
from models import Bookmark  # 你的模型

@api_bp.route("/bookmarks", methods=["GET"])
def list_bookmarks():
    u = _current_user_or_none()
    if not u:
        return {"error": "请先登录"}, 401
    items = Bookmark.query.filter_by(user_id=u.id).all()
    return {"items": [{"id": b.id, "slug": b.slug, "note": b.note} for b in items]}

@api_bp.route("/bookmark", methods=["POST"])
def add_bookmark():
    u = _current_user_or_none()
    if not u:
        return {"error": "请先登录"}, 401
    from flask import request
    data = request.get_json(silent=True) or {}
    b = Bookmark(user_id=u.id, slug=data.get("slug", ""), note=data.get("note", ""))
    db.session.add(b)
    db.session.commit()
    return {"ok": True, "id": b.id}, 201</code></pre>

        <h3>3. 在 __init__.py 登记新模块</h3>
        <pre><code class="python"># myblog/api/__init__.py
from . import auth
from . import bookmark   # ← 新增这一行，顺序不影响路由匹配</code></pre>

        <h3>4. CSRF：写接口怎么过</h3>
        <p>POST / PUT / DELETE / PATCH 默认要求 <code>X-CSRF-Token</code>。若你的接口是「无会话的公开写接口」（如部署回调），在 <code>app.py</code> 的 <code>exempt</code> 元组加入路径前缀即可豁免；否则让调用方先 <code>GET /api/csrf</code> 取 token。前端 <code>apiPost()</code> 已自动带 token。</p>

        <h3>5. 鉴权三级别如何实现</h3>
        <pre><code class="python">from .common import _current_user_or_none
from models import User

# 公开：不判断
# 登录：
u = _current_user_or_none()
if not u:
    return {"error": "请先登录"}, 401
# 超管：
if not u.is_super:
    return {"error": "无权限"}, 403</code></pre>

        <h3>6. 响应与限流约定</h3>
        <ul>
          <li>统一用 <code>return jsonify({"ok": True, ...})</code> 或 <code>return {"error": "..."}, 状态码</code>。</li>
          <li>列表类用 <code>items</code> 字段 + 分页元信息，保持与现有接口一致，前端可直接复用。</li>
          <li>防刷：<code>from .common import rate_limit, client_key</code>，例如 <code>if not rate_limit(client_key("bm:"+u.id), limit=20, window=60): return {"error":"频繁"}, 429</code>。</li>
        </ul>

        <h3>7. 前端调用（Vue）</h3>
        <p>统一用 <code>vue-frontend/src/lib/api.js</code> 的 <code>apiGet</code> / <code>apiPost</code>，已自动处理 CSRF、JSON 与错误。</p>
        <pre><code class="js">import { apiGet, apiPost } from "../lib/api.js";

// 读
const list = await apiGet("/api/bookmarks");

// 写（apiPost 自动带 CSRF Token）
await apiPost("/api/bookmark", { slug: "my-post", note: "待读" });</code></pre>

        <h3>8. 新增一个前端页面</h3>
        <p>① 在 <code>vue-frontend/src/views/</code> 新建 <code>BookmarkView.vue</code>；② 在 <code>router.js</code> 注册路由；③ （可选）在 <code>App.vue</code> 导航加链接。</p>
        <pre><code class="js">// router.js
{ path: "/bookmarks", name: "bookmarks", component: () => import("./views/BookmarkView.vue") }</code></pre>

        <h3>9. 本地调试</h3>
        <pre><code class="bash"># 后端（需设置环境变量；Windows 用 venv\Scripts\python.exe）
PYTHONPATH=myblog ADMIN_PASSWORD=testpass SECRET_KEY=dev-key \
  venv/bin/python -m flask --app app run --debug

# 前端（Vite 开发服务器，走代理到后端）
cd vue-frontend &amp;&amp; npm run dev

# 快速用测试客户端验证接口（无需起服务）
PYTHONPATH=myblog ADMIN_PASSWORD=testpass SECRET_KEY=dev-key \
  venv/bin/python -c "
from app import create_app
app = create_app()
c = app.test_client()
print(c.get('/api/posts').get_json())
"</code></pre>

        <h3>10. 别忘了同步文档</h3>
        <p>新增/修改接口后，请同步更新 <code>myblog/API.md</code> 对应章节与 README 的 API 小节，保持站内文档与代码一致（本页 /docs 由前端维护，亦请同步）。</p>
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
hljs.registerLanguage("bash", lBash);
hljs.registerLanguage("shell", lBash);
hljs.registerLanguage("json", lJson);
hljs.registerLanguage("python", lPython);
hljs.registerLanguage("js", lJs);
hljs.registerLanguage("javascript", lJs);
// 既有 tryHl 轮询逻辑依赖 window.hljs，这里直接就绪（轮询保留以兼容时序）
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

// 侧栏导航改为数据驱动：原先是 20 多行硬编码 <a>，既不能搜索也不能标当前节。
// 标题与顺序与改造前逐条一致。
const navSections = [
  { title: "开始", links: [
    { id: "common", label: "通用约定" },
    { id: "auth", label: "认证 Auth" },
  ] },
  { title: "数据接口", links: [
    { id: "site", label: "站点 Site" },
    { id: "posts", label: "文章 Posts" },
    { id: "stats", label: "统计 Stats" },
    { id: "social", label: "社交广场 Social" },
    { id: "series", label: "专题 Series" },
    { id: "guestbook", label: "留言墙 Guestbook" },
    { id: "subscribe", label: "订阅 Subscribe" },
    { id: "notifications", label: "通知 Notifications" },
    { id: "system", label: "系统 System" },
    { id: "more", label: "其他接口 More" },
  ] },
  { title: "页面与订阅源", links: [
    { id: "pages", label: "SSR 页面 / 源" },
  ] },
  { title: "二次开发", links: [
    { id: "devguide", label: "二次开发指南" },
  ] },
];

const query = ref("");
// 各节正文的小写快照：让搜索能命中「正文里的端点路径」，而不只是章节标题。
// 例如输入 mobile / shell-check / slug 都能定位到对应章节。
const sectionText = ref({});

const visibleSections = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return navSections;
  return navSections
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
  const secs = document.querySelectorAll(".docs-main .doc-section");
  if (!secs.length) return;
  let cur = secs[0];
  for (const s of secs) {
    if (s.getBoundingClientRect().top <= ACTIVE_LINE) cur = s;
    else break;
  }
  activeId.value = cur.id;
  let sub = "";
  for (const h of cur.querySelectorAll("h3")) {
    if (h.getBoundingClientRect().top <= ACTIVE_LINE) sub = h.id;
    else break;
  }
  activeSub.value = sub;
}

function buildToc() {
  // 按「章节 → 该章的小节」建树，而不是把 h1 / h3 混成一个平铺列表。
  const sections = [];
  let cur = null;
  let n = 0;
  document.querySelectorAll(".docs-main .doc-section").forEach((sec) => {
    const h1 = sec.querySelector("h1");
    if (!sec.id) sec.id = "doc-sec-" + sections.length;
    cur = { id: sec.id, label: h1 ? h1.textContent.trim() : sec.id, subs: [] };
    sections.push(cur);
    sec.querySelectorAll("h3").forEach((h3) => {
      if (!h3.id) h3.id = "doc-h-" + n++;
      cur.subs.push({ id: h3.id, text: h3.textContent.trim() });
    });
  });
  tocSections.value = sections;
  // 初始定位到第一节，否则首屏右栏是空的（观察器要等滚动才触发）
  if (sections.length && !activeId.value) activeId.value = sections[0].id;

  // 同时建立「节 id → 正文小写」索引，供搜索使用
  const idx = {};
  document.querySelectorAll(".docs-main .doc-section").forEach((sec) => {
    if (sec.id) idx[sec.id] = sec.textContent.toLowerCase();
  });
  sectionText.value = idx;
}

// v3.17.9：复制统一走 lib/clipboard.js 的三层兜底（原 fallbackCopy 已被其覆盖）

onMounted(() => {
  // v3.17.10：highlight.js 与主题样式已本地打包（见 script 顶部 import），不再依赖 CDN 与 CSP 放行

  buildToc();

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

  // highlight.js 通过 CDN 异步加载，挂载后轮询初始化，确保代码块高亮生效
  let n = 0;
  const tryHl = () => {
    if (window.hljs) {
      document.querySelectorAll(".docs-main pre code").forEach((b) => {
        try { window.hljs.highlightElement(b); } catch (e) { /* ignore */ }
      });
    } else if (n < 40) {
      n += 1;
      setTimeout(tryHl, 100);
    }
  };
  tryHl();

  // 给每个代码块加「复制」按钮（仿 API 文档站）
  document.querySelectorAll(".docs-main pre").forEach((pre) => {
    if (pre.querySelector(".copy-btn")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy-btn";
    btn.textContent = "复制";
    btn.addEventListener("click", () => {
      const code = pre.querySelector("code");
      if (!code) return;
      const done = () => { btn.textContent = "已复制"; setTimeout(() => { btn.textContent = "复制"; }, 1500); };
      // v3.17.9：三层兜底复制（Clipboard API → execCommand → 手动提示）
      copyText(code.innerText).then((ok) => { if (ok) done(); });
    });
    pre.appendChild(btn);
  });

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

.nav-section { margin-bottom: var(--space-4); }

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

/* ── 代码块 ───────────────────────────────────────────────────── */
/* 代码块刻意保持深底（highlight.js github-dark 主题就要求深底），
   不随明暗模式翻转 —— 这是唯一不跟 token 的地方。 */
pre {
  background: #1f2937;
  color: #f3f4f6;
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  margin: var(--space-4) 0;
  position: relative;
  line-height: 1.7;
}
/* 复制按钮压在右上角，而 pre 的 padding 只有 16px ——
   给 code 加右侧留白，长代码首行就不会被按钮盖住（原实现的首行总被遮）。 */
pre code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.8px;
  display: block;
  padding-right: 58px;
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

/* ⚠️ 必须用 :deep() —— 这个按钮是 onMounted 里 document.createElement 出来的，
   **拿不到 scoped 的 data-v 属性**，所以裸写 `.copy-btn { … }` 编译成
   `.copy-btn[data-v-xxx]` 永远不匹配。原实现正是如此：按钮从上线起一直是
   一段没样式的裸文字，糊在代码块左下角（靠截图才看出来）。
   `pre :deep(.copy-btn)` 编译成 `pre[data-v-xxx] .copy-btn`，而 pre 在模板里，
   带 data-v，于是能命中动态插入的子节点。 */
pre :deep(.copy-btn) {
  position: absolute;
  top: 7px;
  right: 7px;
  background: rgba(255, 255, 255, .10);
  color: #d7dde5;
  border: 1px solid rgba(255, 255, 255, .18);
  border-radius: var(--radius-xs);
  font-size: 11px;
  line-height: 1.6;
  padding: 2px 9px;
  cursor: pointer;
  opacity: .45;
  transition: opacity var(--transition), background var(--transition);
}
pre:hover :deep(.copy-btn) { opacity: 1; }
pre :deep(.copy-btn):hover,
pre :deep(.copy-btn):focus-visible { background: rgba(255, 255, 255, .22); opacity: 1; }

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
