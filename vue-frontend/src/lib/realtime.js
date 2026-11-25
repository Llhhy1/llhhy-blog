// SSE 实时推送客户端（v5.14.0）。
//
// 设计要点（每一条都对应线上会出的事）：
//
// 1. **单连接复用**：浏览器对同源 HTTP/1.1 默认只允许 6 条并发连接，一条 SSE 就占一条，
//    而且后端每条连接独占一个 gthread 线程。所以这里全局只维护**一个** EventSource，
//    多个订阅者共用（引用计数），不是每个组件各开一条。
// 2. **有界降级**：后端在连接超限/关闭时会回 503 + `fallback: polling`。但 EventSource
//    拿不到 HTTP 状态码（这是它的设计缺陷），只能看 error 事件。故策略是：
//    连续 3 次 error 且**从没收到过 ready** → 判定为不可用，切轮询；收到过 ready 的
//    断线则交给浏览器自动重连（服务端在 ready 帧里给了 retry: 5000）。
// 3. **后台标签页关闭连接**：标签页在后台时没人看，白占一个线程。隐藏超过 60 秒就断开，
//    重新可见时重连——用户切回来的瞬间正好赶上重连，观感与常驻无异。
// 4. **不碰 CSRF / 不自定义请求头**：EventSource 无法设置 header，靠浏览器自动带同源
//    会话 Cookie，后端也只暴露 GET 只读端点。

const ENDPOINT = "/api/realtime/stream";
const RETRY_HINT = 5000;        // 与服务端 ready 帧里的 retry 保持一致
const MAX_ERRORS = 3;           // 从未 ready 时，连续 error 到这个数就降级
const HIDDEN_GRACE_MS = 60000;  // 后台标签页允许挂多久

let es = null;
let subscribers = 0;
let mode = "off";               // off | sse | polling
let errorStreak = 0;
let everReady = false;
let hiddenTimer = null;
let reconnectTimer = null;
let reconnectDelay = RETRY_HINT;   // 指数退避：5s → 10s → 20s → 40s → 60s 封顶
let handlers = { onOnline: null, onNotification: null, onPending: null, onModeChange: null };

function applyMode(next) {
  if (mode === next) return;
  mode = next;
  try { handlers.onModeChange && handlers.onModeChange(next); } catch (e) { /* 订阅者自己的异常不该影响连接 */ }
}

export function realtimeMode() {
  return mode;
}

function open() {
  if (es || typeof window === "undefined") return;
  if (!window.EventSource) {
    // 老浏览器（含部分 WebView）没有 EventSource：直接走轮询，不报错
    applyMode("polling");
    return;
  }
  if (document.hidden) return;

  try {
    es = new EventSource(ENDPOINT, { withCredentials: true });
  } catch (e) {
    applyMode("polling");
    return;
  }

  es.addEventListener("ready", () => {
    everReady = true;
    errorStreak = 0;
    reconnectDelay = RETRY_HINT;   // 连上了就把退避复位
    applyMode("sse");
    // 刻意**不关闭连接**：ready 只是握手帧，后面还有事件要收。
    // 重连间隔已由服务端帧里的 retry: 5000 声明（见 myblog/realtime.py 的 build_response）。
  });

  es.addEventListener("online", (ev) => {
    const d = safeParse(ev.data);
    if (d && handlers.onOnline) handlers.onOnline(d);
  });

  es.addEventListener("notification", (ev) => {
    const d = safeParse(ev.data);
    if (d && handlers.onNotification) handlers.onNotification(d);
  });

  es.addEventListener("pending", (ev) => {
    const d = safeParse(ev.data);
    if (d && handlers.onPending) handlers.onPending(d);
  });

  es.onerror = () => {
    errorStreak += 1;
    // 连接已彻底关闭（不是浏览器内部重连中）才算一次失败
    if (es && es.readyState === 2 /* CLOSED */) {
      closeConnection();
      if (!everReady && errorStreak >= MAX_ERRORS) {
        applyMode("polling");
        return;
      }
      scheduleReconnect();
    }
  };
}

function scheduleReconnect() {
  // 固定 5 秒重试在「连接名额长期占满」时会变成每客户端 12 次/分钟的无效请求，
  // 故用指数退避封顶 60 秒：短暂抖动很快恢复，长期不可用则逐渐安静下来。
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    if (subscribers > 0) open();
  }, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, 60000);
}

function closeConnection() {
  if (es) {
    try { es.close(); } catch (e) { /* ignore */ }
    es = null;
  }
}

function safeParse(raw) {
  try { return JSON.parse(raw); } catch (e) { return null; }
}

function onVisibility() {
  if (document.hidden) {
    // 不立刻断：短暂切标签页（比如复制个链接）不必重连
    clearTimeout(hiddenTimer);
    hiddenTimer = setTimeout(() => {
      closeConnection();
      applyMode("off");
    }, HIDDEN_GRACE_MS);
  } else {
    clearTimeout(hiddenTimer);
    if (subscribers > 0 && !es) open();
  }
}

/**
 * 开始订阅。重复调用只增加引用计数。
 * @param {{onOnline?:Function,onNotification?:Function,onPending?:Function,onModeChange?:Function}} cb
 * @returns {Function} 取消订阅
 */
export function subscribeRealtime(cb = {}) {
  handlers = { ...handlers, ...cb };
  subscribers += 1;
  if (subscribers === 1) {
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVisibility);
    open();
  }
  let done = false;
  return function unsubscribe() {
    if (done) return;
    done = true;
    subscribers = Math.max(0, subscribers - 1);
    if (subscribers === 0) {
      clearTimeout(hiddenTimer);
      clearTimeout(reconnectTimer);
      closeConnection();
      if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVisibility);
      everReady = false;
      errorStreak = 0;
      applyMode("off");
    }
  };
}
