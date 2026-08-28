/**
 * 插件 HTML 消毒（v3.9.0 M3）。
 *
 * 红线：插件提供的 html 槽位内容必须经 DOMPurify 消毒后才能 v-html 渲染，
 * 否则插件作者手滑会引入 XSS。仅允许安全标签，禁用 on* 事件属性与 script/iframe 等。
 */
import DOMPurify from "dompurify";

export function sanitizeHtml(html) {
  if (!html) return "";
  try {
    return DOMPurify.sanitize(html, {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ["script", "iframe", "object", "embed", "link", "style"],
      FORBID_ATTR: ["onerror", "onload", "onclick", "onmouseover", "style"],
    });
  } catch (e) {
    // 兜底：消毒失败一律不渲染，避免注入
    return "";
  }
}
