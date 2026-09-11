/**
 * v3.17.9：健壮复制到剪贴板（三层兜底，解决「一键复制按钮失效」）
 *
 * 1) Clipboard API —— 需安全上下文（https）+ 权限 + 用户手势；
 * 2) 临时 textarea + document.execCommand('copy') —— 兼容 http、微信内置浏览器、老浏览器、权限被拒；
 * 3) window.prompt —— 最后兜底，保证「永不失效」（自动复制不行就让用户手抄）。
 *
 * @param {string} text 要复制的内容
 * @returns {Promise<boolean>} true=已自动复制成功；false=已走手动兜底（内容已呈现给用户）
 */
export async function copyText(text) {
  const s = text == null ? "" : String(text);
  if (!s) return false;

  // 1) Clipboard API
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(s);
      return true;
    }
  } catch (e) {
    /* 落到下一层兜底 */
  }

  // 2) execCommand 兜底
  try {
    const ta = document.createElement("textarea");
    ta.value = s;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:-2000px;left:0;opacity:0;";
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, s.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    if (ok) return true;
  } catch (e) {
    /* 落到手动兜底 */
  }

  // 3) 手动兜底
  try {
    window.prompt("自动复制被浏览器拦截，请手动复制（Ctrl/Cmd+C）：", s);
  } catch (e) {
    /* ignore */
  }
  return false;
}

export default copyText;
