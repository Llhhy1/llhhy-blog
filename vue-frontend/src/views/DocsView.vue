<template>
  <div class="docs-container">
    <aside class="docs-sidebar">
      <div class="sidebar-header">API 文档</div>
      <nav class="sidebar-nav">
        <div class="nav-section">
          <div class="nav-section-title">开始</div>
          <a href="#common" class="nav-link" @click.prevent="scrollTo('common')">通用约定</a>
          <a href="#auth" class="nav-link" @click.prevent="scrollTo('auth')">认证 Auth</a>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">数据接口</div>
          <a href="#site" class="nav-link" @click.prevent="scrollTo('site')">站点 Site</a>
          <a href="#posts" class="nav-link" @click.prevent="scrollTo('posts')">文章 Posts</a>
          <a href="#stats" class="nav-link" @click.prevent="scrollTo('stats')">统计 Stats</a>
          <a href="#social" class="nav-link" @click.prevent="scrollTo('social')">社交广场 Social</a>
          <a href="#series" class="nav-link" @click.prevent="scrollTo('series')">专题 Series</a>
          <a href="#guestbook" class="nav-link" @click.prevent="scrollTo('guestbook')">留言墙 Guestbook</a>
          <a href="#subscribe" class="nav-link" @click.prevent="scrollTo('subscribe')">订阅 Subscribe</a>
          <a href="#notifications" class="nav-link" @click.prevent="scrollTo('notifications')">通知 Notifications</a>
          <a href="#system" class="nav-link" @click.prevent="scrollTo('system')">系统 System</a>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">页面与订阅源</div>
          <a href="#pages" class="nav-link" @click.prevent="scrollTo('pages')">SSR 页面 / 源</a>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">二次开发</div>
          <a href="#devguide" class="nav-link" @click.prevent="scrollTo('devguide')">二次开发指南</a>
        </div>
      </nav>
    </aside>

    <main class="docs-main">
      <!-- ============ 通用约定 ============ -->
      <div id="common" class="doc-section">
        <h1>通用约定</h1>
        <p>本文档覆盖 llhhy-blog 的全部 JSON 接口（前缀 <code>/api</code>）与 SSR 页面。当前版本基于 <strong>v3.8.7</strong>。前端（<code>vue-frontend/src/lib/api.js</code>）与站内页面共用这些接口；你可以用它们自定义客户端、App 或第三方集成。</p>

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
        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/version/check</span><span class="auth auth-login">登录</span></div>
        <p>检测新版本。<code>200 {"latest":"v3.8.7","current":"v3.8.7","has_update":false}</code>（对比 GitHub latest tag 与本地 <code>APP_VERSION</code>）。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/version/update</span><span class="auth auth-admin">超管</span></div>
        <p>触发在线更新。成功 <code>200 {"ok":true,"message":"更新已触发，服务器将自动重启"}</code>（异步执行 <code>update.sh</code>）。</p>

        <div class="endpoint"><span class="method get">GET</span><span class="path">/api/version/status</span><span class="auth auth-admin">超管</span></div>
        <p>更新状态（后台轮询）。<code>200 {"status":"idle|running|done","message":"..."}</code>；无权限 <code>403</code>。</p>

        <div class="endpoint"><span class="method post">POST</span><span class="path">/api/webhook/deploy</span><span class="auth auth-public">公开</span></div>
        <p>部署 Webhook（CSRF 豁免，但需密钥鉴权）。请求头 <code>X-Deploy-Secret: &lt;与配置相同的密钥&gt;</code>。成功 <code>200 {"ok":true,"message":"部署已触发"}</code>；密钥错误 <code>401</code>。</p>
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
    </main>

    <aside class="docs-toc">
      <div class="toc-title">本页目录</div>
      <nav class="toc-nav">
        <a v-for="t in tocItems" :key="t.id" :href="'#'+t.id"
           class="toc-link" :class="{ 'toc-h3': t.level === 3, 'active': activeId === t.id }"
           @click.prevent="scrollTo(t.id)">{{ t.text }}</a>
      </nav>
    </aside>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";

const tocItems = ref([]);
const activeId = ref("");

function scrollTo(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function buildToc() {
  const heads = document.querySelectorAll(".docs-main h1, .docs-main h3");
  const items = [];
  heads.forEach((h, i) => {
    if (!h.id) h.id = "doc-h-" + i;
    items.push({ id: h.id, text: h.textContent.trim(), level: h.tagName === "H3" ? 3 : 1 });
  });
  tocItems.value = items;
}

function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); done(); } catch (e) { /* ignore */ }
  document.body.removeChild(ta);
}

onMounted(() => {
  // highlight.js 通过 CDN 动态加载（写在模板里会在每次挂载重复注入 <script> 并触发告警），
  // 这里幂等地注入一次，下方轮询 window.hljs 即可高亮；CDN 不可达时优雅跳过（不高亮而已）。
  if (!document.getElementById("hljs-cdn-css")) {
    const l = document.createElement("link");
    l.id = "hljs-cdn-css"; l.rel = "stylesheet";
    l.href = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css";
    document.head.appendChild(l);
  }
  if (!document.getElementById("hljs-cdn-js")) {
    const s = document.createElement("script");
    s.id = "hljs-cdn-js";
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js";
    document.head.appendChild(s);
  }

  buildToc();

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
      const text = code.innerText;
      const done = () => { btn.textContent = "已复制"; setTimeout(() => { btn.textContent = "复制"; }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
      } else {
        fallbackCopy(text, done);
      }
    });
    pre.appendChild(btn);
  });

  // 右侧「本页目录」随滚动高亮当前章节
  if ("IntersectionObserver" in window) {
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) activeId.value = e.target.id; });
    }, { rootMargin: "-80px 0px -70% 0px", threshold: 0 });
    document.querySelectorAll(".docs-main h1, .docs-main h3").forEach((h) => obs.observe(h));
  }
});
</script>

<style scoped>
.docs-container {
  display: flex;
  gap: 32px;
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
  min-height: calc(100vh - 100px);
}

.docs-sidebar {
  width: 250px;
  flex-shrink: 0;
  border-right: 1px solid #e5e7eb;
  padding-right: 20px;
  position: sticky;
  top: 80px;
  height: fit-content;
  max-height: calc(100vh - 100px);
  overflow-y: auto;
}

.sidebar-header {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 2px solid #3b82f6;
}

.nav-section { margin-bottom: 20px; }

.nav-section-title {
  font-size: 14px;
  font-weight: bold;
  color: #6b7280;
  margin-bottom: 10px;
  text-transform: uppercase;
}

.nav-link {
  display: block;
  padding: 8px 12px;
  color: #374151;
  text-decoration: none;
  border-radius: 6px;
  transition: all 0.2s;
  font-size: 14px;
}

.nav-link:hover { background-color: #f3f4f6; color: #3b82f6; }

.docs-main { flex: 1; padding-left: 40px; }

.doc-section { margin-bottom: 60px; scroll-margin-top: 20px; }

.doc-section h1 {
  font-size: 32px;
  font-weight: bold;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e5e7eb;
}

.doc-section h3 { font-size: 20px; font-weight: bold; margin-top: 30px; margin-bottom: 15px; }
.doc-section h4 { font-size: 16px; font-weight: bold; margin-top: 20px; margin-bottom: 10px; }
.doc-section p { line-height: 1.8; color: #4b5563; }
.doc-section ul { line-height: 1.9; color: #4b5563; padding-left: 22px; }
.doc-section li { margin-bottom: 4px; }

.endpoint {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 15px 0;
  padding: 12px;
  background-color: #f8fafc;
  border-radius: 8px;
  border-left: 4px solid var(--accent);
  flex-wrap: wrap;
}

.method {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
  text-transform: uppercase;
}

.method.get { background-color: #10b981; color: white; }
.method.post { background-color: #3b82f6; color: white; }

.path {
  font-family: 'Courier New', monospace;
  font-size: 14px;
  color: #1f2937;
}

.auth {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: bold;
  margin-left: auto;
}
.auth-public { background-color: #e5e7eb; color: #374151; }
.auth-login { background-color: #fef3c7; color: #92400e; }
.auth-admin { background-color: #fee2e2; color: #991b1b; }

.params-table { width: 100%; border-collapse: collapse; margin: 15px 0; }
.params-table th, .params-table td { padding: 10px; text-align: left; border-bottom: 1px solid #e5e7eb; }
.params-table th { background-color: #f9fafb; font-weight: bold; }

pre {
  background-color: #1f2937;
  color: #f3f4f6;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 15px 0;
}
code { font-family: 'Courier New', monospace; font-size: 13px; }
.doc-section :not(pre) > code {
  background-color: #f1f5f9;
  color: #b91c1c;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12.5px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .docs-container { flex-direction: column; padding: 10px; }
  .docs-sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid #e5e7eb;
    padding-right: 0;
    padding-bottom: 15px;
    max-height: 200px;
    position: static;
  }
  .docs-main { padding-left: 0; padding-top: 20px; }
  .doc-section h1 { font-size: 24px; }
}

/* 深色模式（跟随站点 data-theme="dark"） */
[data-theme="dark"] .docs-sidebar { border-color: #2a2e35; }
[data-theme="dark"] .sidebar-header { border-color: #3b82f6; }
[data-theme="dark"] .nav-section-title { color: #9aa3ad; }
[data-theme="dark"] .nav-link { color: #c7ccd1; }
[data-theme="dark"] .nav-link:hover { background-color: #23272e; color: #60a5fa; }
[data-theme="dark"] .doc-section h1,
[data-theme="dark"] .doc-section h3,
[data-theme="dark"] .doc-section h4 { color: #e6e8eb; border-color: #2a2e35; }
[data-theme="dark"] .doc-section p,
[data-theme="dark"] .doc-section li { color: #b6bcc4; }
[data-theme="dark"] .doc-section :not(pre) > code { background-color: #23272e; color: #fca5a5; }
[data-theme="dark"] .endpoint { background-color: #1d2025; border-left-color: #3b82f6; }
[data-theme="dark"] .path { color: #e6e8eb; }
[data-theme="dark"] .params-table th,
[data-theme="dark"] .params-table td { border-color: #2a2e35; color: #c7ccd1; }
[data-theme="dark"] .params-table th { background-color: #23272e; }

/* 代码块复制按钮（仿 API 文档站） */
.docs-main pre { position: relative; }
.copy-btn {
  position: absolute; top: 8px; right: 8px;
  background: rgba(255,255,255,.12); color: #e5e7eb;
  border: 1px solid rgba(255,255,255,.22); border-radius: 5px;
  font-size: 11px; padding: 3px 10px; cursor: pointer;
}
.copy-btn:hover { background: rgba(255,255,255,.22); }

/* 右侧「本页目录」TOC 栏 */
.docs-toc {
  width: 200px; flex-shrink: 0;
  position: sticky; top: 80px; height: fit-content;
  max-height: calc(100vh - 100px); overflow-y: auto;
  padding-left: 16px; border-left: 1px solid #e5e7eb;
}
.toc-title { font-size: 12px; font-weight: 700; color: #6b7280; text-transform: uppercase; margin-bottom: 12px; }
.toc-nav { display: flex; flex-direction: column; gap: 2px; }
.toc-link {
  display: block; padding: 5px 10px; font-size: 13px; color: #6b7280;
  text-decoration: none; border-radius: 6px; border-left: 2px solid transparent;
}
.toc-link:hover { color: var(--accent); background: #f3f4f6; }
.toc-link.active { color: var(--accent); border-left-color: var(--accent); font-weight: 600; }
.toc-h3 { padding-left: 22px; font-size: 12.5px; }

[data-theme="dark"] .docs-toc { border-color: #2a2e35; }
[data-theme="dark"] .toc-title { color: #9aa3ad; }
[data-theme="dark"] .toc-link { color: #9aa3ad; }
[data-theme="dark"] .toc-link:hover { background: #23272e; }

/* 中屏隐藏右侧 TOC，避免挤压正文 */
@media (max-width: 1100px) {
  .docs-toc { display: none; }
}
</style>
