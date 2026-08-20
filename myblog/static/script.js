// 天气小组件：支持「浏览者定位」「手动输入城市」「记住上次选择」。
// 数据来自后端 /api/weather（内部调用 Open-Meteo 等免费接口，无需 Key）。

function weatherText(code) {
  const map = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "小雨", 55: "中雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "雪", 75: "大雪",
    80: "阵雨", 81: "阵雨", 82: "强阵雨",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷暴",
  };
  return map[code] !== undefined ? map[code] : "未知";
}

async function fetchWeather(params) {
  const url = "/api/weather?" + new URLSearchParams(params).toString();
  // 超时保护：7 秒没返回就放弃，避免天气一直「加载中」
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 7000);
  try {
    const resp = await fetch(url, { signal: ctrl.signal });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function updateWeather(data) {
  const el = document.getElementById("w-text");
  if (el) el.textContent = `${data.name}　${weatherText(data.code)} ${data.temp}°C`;
}

function saveLoc(obj) {
  try { localStorage.setItem("visitor_loc", JSON.stringify(obj)); } catch (e) {}
}
function getLoc() {
  try { return JSON.parse(localStorage.getItem("visitor_loc") || "null"); } catch (e) { return null; }
}

function loadWeather() {
  const el = document.getElementById("weather");
  if (!el) return;
  // 1) 有记忆的访客定位/城市，优先用它
  const stored = getLoc();
  if (stored && (stored.lat && stored.lon || stored.city)) {
    fetchWeather(stored).then(updateWeather).catch(() => updateWeatherDefault(el));
    return;
  }
  // 2) 否则用后台默认坐标，并尝试自动获取浏览者定位
  updateWeatherDefault(el);
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const p = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      saveLoc(p);
      try { updateWeather(await fetchWeather(p)); } catch (e) {}
    }, () => {}, { timeout: 4000 });
  }
}

function updateWeatherDefault(el) {
  const p = { lat: el.dataset.lat, lon: el.dataset.lon };
  fetchWeather(p)
    .then(updateWeather)
    .catch(() => {
      const t = document.getElementById("w-text");
      if (t) t.textContent = (el.dataset.city || "本地") + "　天气获取失败";
    });
}

// 手动「📍 定位」按钮：用浏览者当前位置刷新天气
(function () {
  const btn = document.getElementById("locate-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    if (!navigator.geolocation) { alert("当前浏览器不支持定位"); return; }
    btn.textContent = "定位中…";
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const p = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      saveLoc(p);
      try { updateWeather(await fetchWeather(p)); }
      catch (e) { alert("天气获取失败"); }
      btn.textContent = "📍 定位";
    }, () => { alert("定位失败或被拒绝"); btn.textContent = "📍 定位"; }, { timeout: 5000 });
  });
})();

// 城市查询表单：访客输入城市名查天气
(function () {
  const form = document.getElementById("city-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const inp = document.getElementById("city-input");
    const city = inp.value.trim();
    if (!city) return;
    try {
      const d = await fetchWeather({ city });
      updateWeather(d);
      saveLoc({ city });
    } catch (err) { alert("未找到该城市，或天气获取失败"); }
  });
})();

loadWeather();

// 主题切换：亮/暗，选择记到 localStorage，下次访问记住
(function () {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  function current() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  function apply(theme) {
    if (theme === "dark") document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    btn.textContent = theme === "dark" ? "☀️" : "🌙";
  }
  apply(current());
  btn.addEventListener("click", function () {
    const next = current() === "dark" ? "light" : "dark";
    apply(next);
    try { localStorage.setItem("theme", next); } catch (e) {}
    // 若当前页有代码高亮，主题切换时同步换配色
    if (window.applyHighlightTheme) window.applyHighlightTheme();
  });
})();

// 后台上传图片：通用绑定（可插入正文，也可设为封面图）
function bindUpload(btnId, inputId, onDone) {
  const btn = document.getElementById(btnId);
  const input = document.getElementById(inputId);
  if (!btn || !input) return;
  btn.addEventListener("click", () => input.click());
  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const resp = await fetch("/admin/upload", { method: "POST", body: fd });
      const data = await resp.json();
      if (data.error) { alert(data.error); return; }
      onDone(data.url, file.name);
      input.value = "";
    } catch (e) { alert("上传失败，请重试"); }
  });
}

// 插入正文（Markdown 图片语法）
bindUpload("upload-btn", "image-input", (url, name) => {
  const ta = document.getElementById("content");
  const status = document.getElementById("upload-status");
  if (!ta) return;
  const tag = "\n![" + name + "](" + url + ")\n";
  const start = ta.selectionStart, end = ta.selectionEnd;
  ta.value = ta.value.slice(0, start) + tag + ta.value.slice(end);
  ta.focus();
  ta.selectionStart = ta.selectionEnd = start + tag.length;
  if (status) status.textContent = "已插入 ✓";
});

// 设为封面图
bindUpload("cover-upload-btn", "cover-image-input", (url) => {
  const cov = document.getElementById("cover");
  if (cov) cov.value = url;
  const prev = document.getElementById("cover-preview");
  if (prev) prev.src = url;
});

// 阅读进度条：随页面滚动更新顶部细条宽度
(function () {
  const bar = document.getElementById("reading-progress");
  if (!bar) return;
  function update() {
    const doc = document.documentElement;
    const scrolled = doc.scrollTop || document.body.scrollTop;
    const height = doc.scrollHeight - doc.clientHeight;
    const pct = height > 0 ? (scrolled / height) * 100 : 0;
    bar.style.width = pct + "%";
  }
  window.addEventListener("scroll", update, { passive: true });
  update();
})();

// 回到顶部按钮：滚动超过 400px 显示，点击平滑回顶
(function () {
  const btn = document.getElementById("back-to-top");
  if (!btn) return;
  function toggle() {
    btn.style.display = (window.scrollY > 400) ? "block" : "none";
  }
  window.addEventListener("scroll", toggle, { passive: true });
  btn.addEventListener("click", function () {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  toggle();
})();

// 文章点赞：点击自增计数，同一浏览器用 localStorage 去重（只算一次）
(function () {
  const btn = document.getElementById("like-btn");
  if (!btn) return;
  const slug = btn.dataset.slug;
  const key = "liked_" + slug;
  const countEl = document.getElementById("like-count");
  function markLiked() {
    btn.classList.add("liked");
    btn.textContent = "❤️ 已赞 ";
    if (countEl) btn.appendChild(countEl);
  }
  // 已点赞过：直接置为已赞状态（仍显示服务端真实数）
  let liked = false;
  try { liked = localStorage.getItem(key) === "1"; } catch (e) {}
  if (liked) markLiked();
  btn.addEventListener("click", async () => {
    if (liked) return;
    try {
      const resp = await fetch("/post/" + slug + "/like", { method: "POST" });
      const data = await resp.json();
      if (countEl && typeof data.likes === "number") countEl.textContent = data.likes;
      liked = true;
      try { localStorage.setItem(key, "1"); } catch (e) {}
      markLiked();
    } catch (e) { alert("点赞失败，请重试"); }
  });
})();
