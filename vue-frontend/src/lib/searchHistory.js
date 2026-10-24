// 搜索历史（v4.9.0 · ROADMAP §3.1）
//
// 纯前端 localStorage，零后端、零表结构变更 —— 搜索词属于**本机浏览痕迹**，
// 没有理由上报服务器（既增隐私面，又要为它建表）。
//
// 三个刻意的取舍：
// 1. **全函数 try/catch**：Safari 无痕模式下 localStorage.setItem 会直接抛
//    QuotaExceededError；隐私插件也会禁用它。历史是锦上添花的功能，
//    不该因为存不了就让搜索页挂掉。
// 2. **读时校验类型**：localStorage 里的内容用户可手工改、也可能被别的版本
//    写脏。返回前过滤掉非字符串，避免渲染出 [object Object]。
// 3. **去重并提到最前**：重复搜同一个词不该占两个坑位。

const KEY = "llhhy_search_history";
const MAX = 10;

export function getHistory() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr.filter((x) => typeof x === "string" && x.trim()).slice(0, MAX);
  } catch (e) {
    return [];
  }
}

function _save(arr) {
  try {
    localStorage.setItem(KEY, JSON.stringify(arr));
  } catch (e) {
    /* 存不了就算了，不影响搜索本身 */
  }
  return arr;
}

export function addHistory(keyword) {
  const k = (keyword || "").trim();
  if (!k) return getHistory();
  const rest = getHistory().filter((x) => x !== k);
  return _save([k, ...rest].slice(0, MAX));
}

export function removeHistory(keyword) {
  return _save(getHistory().filter((x) => x !== keyword));
}

export function clearHistory() {
  return _save([]);
}
