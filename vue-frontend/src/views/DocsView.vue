<template>
  <div class="docs-container">
    <aside class="docs-sidebar">
      <div class="sidebar-header">API 文档</div>
      <nav class="sidebar-nav">
        <div class="nav-section">
          <div class="nav-section-title">基础</div>
          <a href="#auth" class="nav-link" @click.prevent="scrollTo('auth')">认证</a>
          <a href="#common" class="nav-link" @click.prevent="scrollTo('common')">通用说明</a>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">文章</div>
          <a href="#post-list" class="nav-link" @click.prevent="scrollTo('post-list')">文章列表</a>
          <a href="#post-detail" class="nav-link" @click.prevent="scrollTo('post-detail')">文章详情</a>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">评论</div>
          <a href="#comment-list" class="nav-link" @click.prevent="scrollTo('comment-list')">评论列表</a>
          <a href="#comment-create" class="nav-link" @click.prevent="scrollTo('comment-create')">创建评论</a>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">RSS & 聚合</div>
          <a href="#rss" class="nav-link" @click.prevent="scrollTo('rss')">RSS 订阅</a>
          <a href="#feed-circle" class="nav-link" @click.prevent="scrollTo('feed-circle')">博客圈</a>
        </div>
      </nav>
    </aside>
    <main class="docs-main">
      <div id="auth" class="doc-section">
        <h1>认证</h1>
        <p>所有需要认证的接口均使用 Cookie 方式传递 session，无需额外 Token。</p>
        <h3>登录</h3>
        <div class="endpoint">
          <span class="method post">POST</span>
          <span class="path">/api/login</span>
        </div>
        <h4>请求参数</h4>
        <table class="params-table">
          <thead><tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
          <tbody>
            <tr><td>username</td><td>string</td><td>是</td><td>用户名</td></tr>
            <tr><td>password</td><td>string</td><td>是</td><td>密码</td></tr>
          </tbody>
        </table>
        <h4>cURL 示例</h4>
        <pre><code class="bash">curl -X POST http://your-domain.com/api/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"username":"admin","password":"your-password"}'</code></pre>
        <h4>响应示例</h4>
        <pre><code class="json">{
  "success": true,
  "message": "登录成功"
}</code></pre>
      </div>

      <div id="common" class="doc-section">
        <h1>通用说明</h1>
        <h3>响应格式</h3>
        <p>成功响应：</p>
        <pre><code class="json">{
  "success": true,
  "data": { ... }
}</code></pre>
        <p>失败响应：</p>
        <pre><code class="json">{
  "success": false,
  "error": "错误信息"
}</code></pre>
        <h3>CSRF 防护</h3>
        <p>v3.1.6 起所有 POST 请求必须携带 CSRF Token。</p>
        <h4>获取 Token</h4>
        <div class="endpoint">
          <span class="method get">GET</span>
          <span class="path">/api/csrf</span>
        </div>
        <pre><code class="bash">curl http://your-domain.com/api/csrf</code></pre>
        <h4>使用 Token</h4>
        <pre><code class="bash">curl -X POST http://your-domain.com/api/post/test/like \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: YOUR_TOKEN_HERE" \
  -b cookies.txt \
  -d '{}'</code></pre>
      </div>

      <div id="post-list" class="doc-section">
        <h1>文章列表</h1>
        <div class="endpoint">
          <span class="method get">GET</span>
          <span class="path">/api/posts</span>
        </div>
        <h4>查询参数</h4>
        <table class="params-table">
          <thead><tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
          <tbody>
            <tr><td>page</td><td>int</td><td>否</td><td>页码，默认 1</td></tr>
            <tr><td>per_page</td><td>int</td><td>否</td><td>每页数量，默认 10</td></tr>
            <tr><td>category</td><td>string</td><td>否</td><td>分类 slug</td></tr>
            <tr><td>tag</td><td>string</td><td>否</td><td>标签 slug</td></tr>
          </tbody>
        </table>
        <h4>cURL 示例</h4>
        <pre><code class="bash">curl "http://your-domain.com/api/posts?page=1&per_page=10"</code></pre>
        <h4>响应示例</h4>
        <pre><code class="json">{
  "success": true,
  "data": {
    "posts": [
      {
        "id": 1,
        "title": "测试文章",
        "slug": "test-post",
        "summary": "文章摘要",
        "created_at": "2026-08-27T12:00:00Z",
        "category": "技术",
        "tags": ["Vue", "Flask"]
      }
    ],
    "total": 50,
    "page": 1,
    "per_page": 10
  }
}</code></pre>
      </div>

      <div id="post-detail" class="doc-section">
        <h1>文章详情</h1>
        <div class="endpoint">
          <span class="method get">GET</span>
          <span class="path">/api/post/:slug</span>
        </div>
        <h4>cURL 示例</h4>
        <pre><code class="bash">curl http://your-domain.com/api/post/test-post</code></pre>
        <h4>响应示例</h4>
        <pre><code class="json">{
  "success": true,
  "data": {
    "id": 1,
    "title": "测试文章",
    "slug": "test-post",
    "content": "<p>文章内容...</p>",
    "created_at": "2026-08-27T12:00:00Z",
    "updated_at": "2026-08-27T12:30:00Z",
    "category": "技术",
    "tags": ["Vue", "Flask"],
    "likes": 5,
    "comments_count": 3
  }
}</code></pre>
        <h3>点赞</h3>
        <div class="endpoint">
          <span class="method post">POST</span>
          <span class="path">/api/post/:slug/like</span>
        </div>
        <p>**需要 CSRF Token**</p>
        <pre><code class="bash">curl -X POST http://your-domain.com/api/post/test-post/like \
  -H "X-CSRF-Token: YOUR_TOKEN_HERE" \
  -b cookies.txt \
  -d '{}'</code></pre>
      </div>

      <div id="comment-list" class="doc-section">
        <h1>评论列表</h1>
        <div class="endpoint">
          <span class="method get">GET</span>
          <span class="path">/api/post/:slug/comments</span>
        </div>
        <h4>cURL 示例</h4>
        <pre><code class="bash">curl http://your-domain.com/api/post/test-post/comments</code></pre>
        <h4>响应示例</h4>
        <pre><code class="json">{
  "success": true,
  "data": {
    "comments": [
      {
        "id": 1,
        "author": "张三",
        "content": "不错",
        "created_at": "2026-08-27T13:00:00Z"
      }
    ],
    "total": 10
  }
}</code></pre>
      </div>

      <div id="comment-create" class="doc-section">
        <h1>创建评论</h1>
        <div class="endpoint">
          <span class="method post">POST</span>
          <span class="path">/api/post/:slug/comment</span>
        </div>
        <p>**需要 CSRF Token + 验证码**</p>
        <h4>请求参数</h4>
        <table class="params-table">
          <thead><tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
          <tbody>
            <tr><td>author</td><td>string</td><td>是</td><td>昵称</td></tr>
            <tr><td>content</td><td>string</td><td>是</td><td>评论内容</td></tr>
            <tr><td>captcha_id</td><td>string</td><td>是</td><td>验证码 ID</td></tr>
            <tr><td>captcha_text</td><td>string</td><td>是</td><td>验证码文本</td></tr>
          </tbody>
        </table>
        <h4>获取验证码</h4>
        <div class="endpoint">
          <span class="method get">GET</span>
          <span class="path">/api/captcha</span>
        </div>
        <pre><code class="bash">curl http://your-domain.com/api/captcha</code></pre>
        <h4>cURL 示例</h4>
        <pre><code class="bash">curl -X POST http://your-domain.com/api/post/test-post/comment \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: YOUR_TOKEN_HERE" \
  -b cookies.txt \
  -d '{
    "author": "张三",
    "content": "不错",
    "captcha_id": "CAPTCHA_ID",
    "captcha_text": "ABCD"
  }'</code></pre>
      </div>

      <div id="rss" class="doc-section">
        <h1>RSS 订阅</h1>
        <div class="endpoint">
          <span class="method get">GET</span>
          <span class="path">/feed</span>
        </div>
        <p>返回 RSS 2.0 格式订阅源。</p>
        <h4>cURL 示例</h4>
        <pre><code class="bash">curl http://your-domain.com/feed</code></pre>
        <h4>分类 RSS</h4>
        <div class="endpoint">
          <span class="method get">GET</span>
          <span class="path">/feed/category/:slug</span>
        </div>
      </div>

      <div id="feed-circle" class="doc-section">
        <h1>博客圈</h1>
        <div class="endpoint">
          <span class="method get">GET</span>
          <span class="path">/api/feed/circle</span>
        </div>
        <p>聚合友链 RSS，返回按时间混排的文章流。</p>
        <h4>查询参数</h4>
        <table class="params-table">
          <thead><tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
          <tbody>
            <tr><td>refresh</td><td>int</td><td>否</td><td>设为 1 强制刷新缓存</td></tr>
          </tbody>
        </table>
        <h4>cURL 示例</h4>
        <pre><code class="bash">curl http://your-domain.com/api/feed/circle</code></pre>
        <h4>响应示例</h4>
        <pre><code class="json">{
  "success": true,
  "data": {
    "items": [
      {
        "title": "友链文章标题",
        "link": "https://example.com/post/1",
        "published_at": "2026-08-27T10:00:00Z",
        "source": "友链名称"
      }
    ]
  }
}</code></pre>
      </div>
    </main>
  </div>
</template>

<script setup>
function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
}
</script>

<style scoped>
.docs-container {
  display: flex;
  max-width: 1200px;
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

.nav-section {
  margin-bottom: 20px;
}

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

.nav-link:hover {
  background-color: #f3f4f6;
  color: #3b82f6;
}

.docs-main {
  flex: 1;
  padding-left: 40px;
}

.doc-section {
  margin-bottom: 60px;
  scroll-margin-top: 20px;
}

.doc-section h1 {
  font-size: 32px;
  font-weight: bold;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e5e7eb;
}

.doc-section h3 {
  font-size: 20px;
  font-weight: bold;
  margin-top: 30px;
  margin-bottom: 15px;
}

.doc-section h4 {
  font-size: 16px;
  font-weight: bold;
  margin-top: 20px;
  margin-bottom: 10px;
}

.doc-section p {
  line-height: 1.8;
  color: #4b5563;
}

.endpoint {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 15px 0;
  padding: 12px;
  background-color: #f8fafc;
  border-radius: 8px;
  border-left: 4px solid #3b82f6;
}

.method {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
  text-transform: uppercase;
}

.method.get {
  background-color: #10b981;
  color: white;
}

.method.post {
  background-color: #3b82f6;
  color: white;
}

.path {
  font-family: 'Courier New', monospace;
  font-size: 14px;
  color: #1f2937;
}

.params-table {
  width: 100%;
  border-collapse: collapse;
  margin: 15px 0;
}

.params-table th,
.params-table td {
  padding: 10px;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
}

.params-table th {
  background-color: #f9fafb;
  font-weight: bold;
}

pre {
  background-color: #1f2937;
  color: #f3f4f6;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 15px 0;
}

code {
  font-family: 'Courier New', monospace;
  font-size: 13px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .docs-container {
    flex-direction: column;
    padding: 10px;
  }

  .docs-sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid #e5e7eb;
    padding-right: 0;
    padding-bottom: 15px;
    max-height: 200px;
    position: static;
  }

  .docs-main {
    padding-left: 0;
    padding-top: 20px;
  }

  .doc-section h1 {
    font-size: 24px;
  }
}
</style>

<!-- highlight.js CDN -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('pre code').forEach((block) => {
    hljs.highlightElement(block);
  });
});
</script>