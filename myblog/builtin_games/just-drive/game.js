/* 就是开车 —— 荒谬双雄之二（纯原创，无外部资源）
 * 一条没有尽头的公路：左右滑动控车（← → 也可）。
 * 正式模式开满 40 分钟算通关；1 分钟为试驾模式。
 * 撞车/溜肩不掉血：只减速 + 被作者嘲讽。通关按真实用时弹文案并记 ID 大神榜。
 */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var MODE = { formal: 2400, demo: 60 }; // 秒

  var state = {
    phase: "ready", mode: MODE.formal, sec: 0, last: 0, dist: 0,
    lat: 0, targetLat: 0, speedKmh: 118, shake: 0,
    sound: true, pid: "无名氏", lastTaunt: 0,
  };
  var attempts = [];   // 大神榜（本场）
  var cars = [];       // 对向来车
  var audio = null;

  var cv = $("stage"), ctx = cv.getContext("2d");
  var W = 0, H = 0, DPR = 1, CAR_Y = 0;
  var HORIZON = 0.16, VIEW_KM = 0.34, ROAD_HALF = 1.5, CAR_ROW = 0.84;

  var el = {
    km: $("km"), clock: $("clock"), near: $("near"), line: $("line"),
    overlay: $("overlay"), pid: $("pid"), m40: $("m40"), m1: $("m1"),
    board: $("board"), snd: $("snd"), final: $("final"), again: $("again"),
    fscore: $("fscore"), frank: $("frank"), mock: $("mock"),
  };

  // ---------- 尺寸 ----------
  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = W * DPR; cv.height = H * DPR;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    CAR_Y = Math.round(H * 0.84);
  }
  window.addEventListener("resize", resize);

  // ---------- 文案 ----------
  var TAUNT_DIST = [
    [5, "5 km。你甚至还没开出小区。"],
    [15, "15 km。后视镜里空无一人。"],
    [30, "30 km。已经开始跟路边的仙人掌说话。"],
    [50, "50 km。仙人掌都懒得理你了。"],
    [70, "70 km。人类文明在倒退，你在前进（并没有）。"],
    [90, "90 km。到了吗？还没。这就是意义（没有意义）。"],
  ];
  var CRASH_LINES = [
    "撞了？没事，保险不用你赔，时间也不用你补。",
    "擦到一下，车速慢点，你的人生也慢点。",
    "别慌，这条路连尽头都没有，急什么。",
  ];
  function pickOnce(list) { return list[Math.floor(Math.random() * list.length)]; }
  function distTaunt(d) {
    var cur = TAUNT_DIST[0];
    for (var i = 0; i < TAUNT_DIST.length; i++) if (d >= TAUNT_DIST[i][0]) cur = TAUNT_DIST[i];
    return cur[1];
  }

  // ---------- 声音 ----------
  function ac() {
    if (!audio) { var AC = window.AudioContext || window.webkitAudioContext; if (AC) audio = new AC(); }
    if (audio && audio.state === "suspended") audio.resume();
    return audio;
  }
  function tone(f, dur, type, vol, when) {
    if (!state.sound) return;
    var a = ac(); if (!a) return;
    var t = a.currentTime + (when || 0), o = a.createOscillator(), g = a.createGain();
    o.type = type || "sine"; o.frequency.value = f;
    g.gain.setValueAtTime(vol || 0.04, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(a.destination); o.start(t); o.stop(t + dur + 0.02);
  }
  function engine() { tone(70, 0.12, "sawtooth", 0.015); }
  function bump() { tone(160, 0.2, "square", 0.05); }
  function fanfare() { [523, 659, 784, 1047].forEach(function (f, i) { tone(f, 0.3, "sine", 0.06, i * 0.14); }); }
  function buzz(ms) { if (navigator.vibrate) try { navigator.vibrate(ms); } catch (e) {} }

  // ---------- 道路几何 ----------
  function roadMid(distKm) {
    var s = distKm * 4.0;
    return Math.sin(s) * 0.34 + Math.sin(s * 2.13 + 2.0) * 0.16;
  }
  function ppu(y) { // 每「路宽单位」的像素（近大远小）
    var t = Math.max(0, Math.min(1, (y - HORIZON * H) / (H * (1 - HORIZON))));
    return 40 + 180 * Math.pow(t, 1.25);
  }
  function distAtY(y) { return state.dist + (H - y) * (VIEW_KM / (H * (1 - HORIZON))); }

  function drawRoad() {
    var step = 8;
    ctx.save();
    // 底色：夜砂
    var sky = ctx.createLinearGradient(0, 0, 0, H);
    sky.addColorStop(0, "#1a1038"); sky.addColorStop(0.45, "#241a44");
    sky.addColorStop(0.5, "#b98a54"); sky.addColorStop(1, "#6b4a2e");
    ctx.fillStyle = sky; ctx.fillRect(0, 0, W, H);
    // 路面（按行采样连线成带）
    ctx.fillStyle = "#3d3f52";
    for (var y = Math.floor(H - step); y > HORIZON * H; y -= step) {
      var y0 = Math.min(y + step, H), y1 = y;
      var m0 = W / 2 + roadMid(distAtY(y0)) * ppu(y0);
      var m1 = W / 2 + roadMid(distAtY(y1)) * ppu(y1);
      var r0 = ROAD_HALF * ppu(y0), r1 = ROAD_HALF * ppu(y1);
      ctx.beginPath();
      ctx.moveTo(m0 - r0, y0); ctx.lineTo(m0 + r0, y0);
      ctx.lineTo(m1 + r1, y1); ctx.lineTo(m1 - r1, y1);
      ctx.closePath(); ctx.fill();
    }
    // 中线虚线（抽 3 条采样行意思一下，省性能但保持景深感）
    ctx.fillStyle = "rgba(255,220,140,.55)";
    for (var i = 0; i < 9; i++) {
      var y2 = HORIZON * H + 10 + (H * (1 - HORIZON) - 20) * (i / 9);
      var m2 = W / 2 + roadMid(distAtY(y2)) * ppu(y2);
      ctx.fillRect(m2 - 2, y2 - 10, 4, 8);
    }
    ctx.restore();
  }

  function screenX(latKm, y) { return W / 2 + (latKm - roadMid(distAtY(y))) * ppu(y) + state.shake; }

  // ---------- 对向来车 ----------
  function spawnCar() {
    if (state.phase !== "play") return;
    cars.push({ ahead: VIEW_KM * (0.25 + Math.random() * 0.75), lat: (Math.random() - 0.5) * 1.7,
                passed: false, w: 0.9, l: 1.7, col: Math.random() < 0.5 ? "#ff9d6b" : "#8fb8ff" });
  }

  function drawCars(dt) {
    var closure = (state.speedKmh + 90 + Math.random() * 40) / 3600; // km/s
    for (var i = cars.length - 1; i >= 0; i--) {
      var c = cars[i];
      c.ahead -= closure * dt;
      if (c.ahead <= 0.02) { cars.splice(i, 1); continue; }
      var y = H * (1 - HORIZON) * (1 - Math.max(0, c.ahead) / VIEW_KM) + HORIZON * H;
      var cx = screenX(c.lat, y), w = c.w * ppu(y) * 0.22, h = c.l * ppu(y) * 0.16;
      ctx.fillStyle = c.col;
      ctx.beginPath(); ctx.roundRect(cx - w / 2, y - h, w, h, 6); ctx.fill();
      ctx.fillStyle = "rgba(0,0,0,.25)";
      ctx.fillRect(cx - w / 2 + 3, y - h + 3, w - 6, 4);
      // 擦肩判定：与车同行 x 区间 && 纵向重叠即算
      if (!c.passed && y < CAR_Y && y + h > CAR_Y - 26) {
        c.passed = true;
        if (Math.abs(state.lat - c.lat) < 1.1) { nearCount++; el.near.textContent = nearCount; }
      }
      // 碰撞（含轻微错位缓冲）：减速 + 嘲讽（冷却）
      var cy = CAR_Y;
      if (Math.abs(y - cy) < h + 30 && Math.abs(state.lat - c.lat) < (0.22 + c.w / 2) * 1.1 + 0.15 && state.sec - state.lastTaunt > 3) {
        state.lastTaunt = state.sec;
        state.speedKmh = Math.max(70, state.speedKmh - 6);
        state.shake = 10;
        el.line.textContent = pickOnce(CRASH_LINES);
        bump(); buzz(15);
      }
    }
  }

  var nearCount = 0;

  // ---------- 主角车 ----------
  function drawCar() {
    var cx = screenX(state.lat, CAR_Y);
    ctx.fillStyle = "#e14f3c";
    ctx.beginPath(); ctx.roundRect(cx - 15, CAR_Y - 30, 30, 52, 9); ctx.fill();
    ctx.fillStyle = "#a9c7ff";
    ctx.fillRect(cx - 11, CAR_Y - 22, 22, 14);
    ctx.fillStyle = "#ffd98a";
    ctx.fillRect(cx - 12, CAR_Y + 12, 24, 6);
  }

  // ---------- 主循环 ----------
  function frame(ts) {
    if (state.phase === "play") {
      if (state.last) {
        var dt = Math.min((ts - state.last) / 1000, 0.12);
        if (!document.hidden) {
          state.sec += dt;
          var ds = (state.speedKmh / 3600) * dt;
          state.dist += ds;
          // 转弯惯性恢复 + 速度缓回
          state.speedKmh = Math.min(118, state.speedKmh + 0.4 * dt);
          state.lat += (state.targetLat - state.lat) * Math.min(1, dt * 5);
          // 溜肩：离中线太远 → 拖慢 + 抖
          if (Math.abs(state.lat - roadMid(state.dist)) > ROAD_HALF * 0.78) {
            state.speedKmh = Math.max(60, state.speedKmh - 2.2 * dt);
            state.shake = 6;
          } else {
            state.shake *= 0.88;
          }
          nearCount = nearCount;
          // 里程碑文案
          var prev = Math.floor(state.dist);
          var nowD = Math.floor(state.dist);
          if (nowD !== prev && nowD % 5 === 0) el.line.textContent = distTaunt(nowD);
          // 定时产车
          if (Math.random() < dt * 0.9) spawnCar();
          if (state.sec % 300 < dt && state.sec > 0) el.line.textContent = "已开 " + Math.round(state.sec / 60) + " 分钟。路的尽头是下一条路。";
          // 结束
          if (state.sec >= state.mode) finish();
        }
      }
      state.last = ts;
      updateHud();
    }
    // 渲染
    drawRoad();
    drawCars(1);
    if (state.phase === "play") { drawCar(); engine(); }
    requestAnimationFrame(frame);
  }

  function updateHud() {
    el.km.textContent = state.dist.toFixed(1);
    el.clock.textContent = fmtClock(state.sec);
  }

  // ---------- 格式 ----------
  function fmtClock(s) {
    var m = Math.floor(s / 60), ss = Math.floor(s % 60);
    return m + ":" + (ss < 10 ? "0" : "") + ss;
  }
  function fmt(s) {
    s = Math.floor(s);
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    if (h > 0) return h + " 小时 " + m + " 分";
    if (m > 0) return m + " 分 " + x + " 秒";
    return x + " 秒";
  }

  // ---------- 流程 ----------
  function finish() {
    state.phase = "final";
    var rec = { id: state.pid, sec: Math.floor(state.sec), dist: state.dist };
    attempts.push(rec);
    renderBoard();
    var rank = rankOf(rec);
    el.fscore.textContent = state.pid + " 孤独地开了 " + state.dist.toFixed(1)
      + " km · 用时 " + fmt(state.sec);
    el.frank.textContent = rank === 1 ? "🏆 本场唯一幸存驾驶员（暂时）。"
      : "大神榜第 " + rank + " 名。前面的更孤独。";
    el.mock.textContent = "🏁 恭喜，你孤独地浪费了 " + fmt(state.sec)
      + "。前方没有出口，也没有人等你。";
    el.final.classList.remove("hidden");
    fanfare(); buzz([20, 60, 20, 60, 30]);
  }

  function sorted() { return attempts.slice().sort(function (a, b) { return a.sec - b.sec; }).slice(0, 3); }
  function rankOf(rec) {
    var r = 1;
    attempts.forEach(function (x) { if (x.sec < rec.sec || (x.sec === rec.sec && x !== rec)) r++; });
    return r;
  }
  function renderBoard() {
    var top = sorted(), html = "<h3>🏆 大神榜（孤独级别）</h3>";
    if (!top.length) html += "<p style='text-align:center;color:#6f76a8'>还没有人敢开完，等你破纪录。</p>";
    else {
      html += "<ol>";
      top.forEach(function (a) {
        html += "<li><b>" + a.id + "</b> · " + a.dist.toFixed(1) + " km · " + fmt(a.sec) + "</li>";
      });
      html += "</ol>";
    }
    el.board.innerHTML = html;
  }

  function startRun(modeSec) {
    state.pid = (el.pid.value || "").trim() || "无名氏";
    state.phase = "play"; state.mode = modeSec; state.sec = 0; state.last = 0;
    state.dist = 0; state.lat = 0; state.targetLat = 0; state.shake = 0;
    cars = []; nearCount = 0;
    el.overlay.classList.add("hidden");
    el.final.classList.add("hidden");
    el.km.textContent = "0.0"; el.clock.textContent = "0:00"; el.near.textContent = "0";
    el.line.textContent = "出发。前方没有车，也没有人。路是真的长。";
  }

  // ---------- 输入 ----------
  var dragStart = null;
  function steer(px) {
    state.targetLat = Math.max(-1.5, Math.min(1.5, (px / W - 0.5) * 4.6));
  }
  cv.addEventListener("pointerdown", function (e) {
    if (state.phase !== "play") return;
    dragStart = e.clientX;
    cv.setPointerCapture(e.pointerId);
    steer(e.clientX);
  });
  cv.addEventListener("pointermove", function (e) {
    if (state.phase !== "play" || dragStart === null) return;
    steer(e.clientX);
  });
  cv.addEventListener("pointerup", function () {
    dragStart = null; state.targetLat = 0; // 松手自动回中，方便手指连续滑动
  });
  window.addEventListener("keydown", function (e) {
    if (state.phase !== "play") return;
    if (e.key === "ArrowLeft" || e.key === "a") state.targetLat = -1.4;
    if (e.key === "ArrowRight" || e.key === "d") state.targetLat = 1.4;
  });
  window.addEventListener("keyup", function (e) {
    if (e.key === "ArrowLeft" || e.key === "a" || e.key === "ArrowRight" || e.key === "d") {
      if (!dragStart) state.targetLat = 0;
    }
  });

  el.m40.addEventListener("pointerdown", function (e) { e.preventDefault(); startRun(MODE.formal); });
  el.m1.addEventListener("pointerdown", function (e) { e.preventDefault(); startRun(MODE.demo); });
  el.again.addEventListener("pointerdown", function (e) { e.preventDefault(); el.final.classList.add("hidden"); startRun(MODE.formal); });
  el.snd.addEventListener("pointerdown", function (e) {
    e.preventDefault(); state.sound = !state.sound; el.snd.textContent = state.sound ? "🔊" : "🔇";
  });

  resize();
  renderBoard();
  updateHud();
  requestAnimationFrame(frame);
})();
