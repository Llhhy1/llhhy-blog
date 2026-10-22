<template>
  <div class="widget weather-widget">
    <h3>{{ t('weather') }}</h3>
    <p class="w-text" id="weather-text">{{ t('loading') }}</p>
    <div class="w-actions">
      <input v-model="city" class="w-input" type="text" :placeholder="t('weather_city_ph')" @keydown.enter.prevent="search" />
      <button class="w-btn primary" type="button" @click="search">{{ t('query') }}</button>
      <button class="w-btn" type="button" :title="t('use_my_location')" @click="locate">{{ t('locate') }}</button>
    </div>
    <p class="w-msg" id="weather-msg">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { t } from "../store.js";

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
      let desc = data.description || t("w_" + codeToNum(data.code)) || t("unknown");
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
    msg.value = t("net_error");
    // 坐标/定位请求失败时回退默认城市，保证天气区始终有内容（兜底请求不带坐标，不会递归）
    if (query.lat || query.lon) {
      fetchWeather({});
    }
  } finally {
    clearTimeout(timer);
  }
}

// 天气代码 → 归一化数字（后端可能给 number 或字符串）
function codeToNum(code) {
  const n = parseInt(code, 10);
  return isNaN(n) ? "" : n;
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
  if (!city.value.trim()) { msg.value = t("city_required"); return; }
  fetchWeather({ city: city.value.trim() });
}

function locate() {
  // 浏览器定位 API 只在 HTTPS（安全上下文）下可用；HTTP 环境会拿不到 geolocation
  if (!navigator.geolocation) {
    msg.value = t("locate_unsupported");
    fetchWeather({});  // 回退到后台默认城市
    return;
  }
  msg.value = t("locating");
  navigator.geolocation.getCurrentPosition(
    (pos) => fetchWeather({ lat: pos.coords.latitude, lon: pos.coords.longitude, geo: "1" }),
    () => { msg.value = t("locate_failed"); fetchWeather({}); },  // 定位失败也回退默认城市
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
