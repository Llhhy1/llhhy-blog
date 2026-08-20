<template>
  <div class="widget weather-widget">
    <h3>天气</h3>
    <p class="w-text" id="weather-text">加载中…</p>
    <div class="w-actions">
      <input v-model="city" class="w-input" type="text" placeholder="输入城市，如 上海" @keydown.enter.prevent="search" />
      <button class="w-btn primary" type="button" @click="search">查询</button>
      <button class="w-btn" type="button" title="使用我的位置" @click="locate">📍 定位</button>
    </div>
    <p class="w-msg" id="weather-msg">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";

const city = ref("");
const msg = ref("");
const STORE_KEY = "weather.location";

async function fetchWeather(query) {
  msg.value = "";
  // 超时保护：请求超过 7 秒未返回则放弃，避免一直卡「加载中」
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 7000);
  try {
    const resp = await fetch("/api/weather?" + new URLSearchParams(query).toString(), {
      headers: { Accept: "application/json" },
      signal: ctrl.signal,
    });
    const data = await resp.json();
    if (data.error) { msg.value = data.error; return; }
    const textEl = document.getElementById("weather-text");
    if (textEl) {
      // 后端返回 description（中文天气）与 city/name（城市名），这里兼容处理
      let desc = data.description || codeToText(data.code) || "未知";
      let cityName = data.city || data.name || "";
      let s = desc + " " + data.temp + "°C";
      if (cityName) s += " · " + cityName;
      textEl.textContent = s;
    }
    const cityName = data.city || data.name || "";
    if (cityName) {
      try {
        localStorage.setItem(STORE_KEY, JSON.stringify({ city: cityName, lat: data.lat, lon: data.lon }));
      } catch (e) {}
    }
  } catch (e) {
    msg.value = "网络错误，请稍后再试";
    // 坐标/定位请求失败时回退默认城市，保证天气区始终有内容（兜底请求不带坐标，不会递归）
    if (query.lat || query.lon) {
      fetchWeather({});
    }
  } finally {
    clearTimeout(timer);
  }
}

// 天气代码 → 中文（兜底，接口没给 description 时用）
function codeToText(code) {
  const map = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "小雨", 55: "中雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "雪", 75: "大雪",
    80: "阵雨", 81: "阵雨", 82: "强阵雨",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷暴",
  };
  return map[code];
}

function loadCached() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return false;
    const v = JSON.parse(raw);
    if (v && v.lat && v.lon) {
      fetchWeather({ lat: v.lat, lon: v.lon });
      if (v.city) city.value = v.city;
      return true;
    }
  } catch (e) {}
  return false;
}

function search() {
  if (!city.value.trim()) { msg.value = "请输入城市名"; return; }
  fetchWeather({ city: city.value.trim() });
}

function locate() {
  // 浏览器定位 API 只在 HTTPS（安全上下文）下可用；HTTP 环境会拿不到 geolocation
  if (!navigator.geolocation) {
    msg.value = "当前环境不支持定位，已显示默认城市";
    fetchWeather({});  // 回退到后台默认城市
    return;
  }
  msg.value = "正在获取位置…";
  navigator.geolocation.getCurrentPosition(
    (pos) => fetchWeather({ lat: pos.coords.latitude, lon: pos.coords.longitude, geo: "1" }),
    () => { msg.value = "定位失败，已显示默认城市"; fetchWeather({}); },  // 定位失败也回退默认城市
    { timeout: 8000 }
  );
}

// 组件挂载时：有缓存用缓存，否则自动定位；定位不可用（如 HTTP）直接用默认城市
if (!loadCached()) {
  if (navigator.geolocation) {
    setTimeout(locate, 300);
  } else {
    fetchWeather({});
  }
}
</script>
