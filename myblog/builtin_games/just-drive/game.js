/* 就是开车 · NEON —— 荒谬双雄之二 视觉升级版（纯原创，无外部资源）
 * 一条没有尽头的霓虹夜路：左右滑动/←→ 控车。
 * 刺激点：擦肩超车积「连击」、穿过「氮气光带」冲刺加速、车流随时间加密、
 * 撞车不掉命但掉速+重置连击。正式模式 40 分钟 / 试驾 1 分钟。
 */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var MODE = { formal: 2400, demo: 60 };

  var S = {
    phase: "ready", mode: MODE.formal, sec: 0, last: 0, dist: 0,
    lat: 0, tLat: 0, spd: 96, shake: 0, flash: 0,
    boost: 0, boostT: 0, combo: 0, comboT: 0, maxCombo: 0, rings: 0,
    sound: true, pid: "无名氏", lastTaunt: 0,
  };
  var attempts = [];
  var cars = [];
  var rings = [];
  var sparks = [];     // 火花/拖尾粒子
  var stars = [];
  var audio = null;

  var cv = $("stage"), ctx = cv.getContext("2d");
  var W = 0, H = 0, DPR = 1;
  var CAR_Y = 0, VIEW_KM = 0.34, ROAD_HALF = 1.55;

  var el = {
    km: $("km"), spd: $("spd"), combo: $("combo"), boostBar: $("boost"),
    line: $("line"), overlay: $("overlay"), pid: $("pid"), m40: $("m40"), m1: $("m1"),
    board: $("board"), snd: $("snd"), final: $("final"), again: $("again"),
    fscore: $("fscore"), frank: $("frank"), mock: $("mock"),
  };

  // ---------- 视口 ----------
  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = W * DPR; cv.height = H * DPR;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    CAR_Y = Math.round(H * 0.84);
    var n = Math.round(W * H / 9000);
    stars = [];
    for (var i = 0; i < Math.min(140, n); i++) {
      stars.push({ x: Math.random(), y: Math.random() * 0.55,
                   r: Math.random() * 1.3 + .4, p: Math.random() * 6.28, s: .5 + Math.random() * 2 });
    }
  }
  window.addEventListener("resize", resize);

  // ---------- 文案 ----------
  var TAUNTS = [
    [5, "5 km。霓虹很美，但没人等你。"],
    [15, "15 km。后视镜里空无一人。"],
    [30, "30 km。连路灯都开始给你打气。"],
    [55, "55 km。别松油门，人生也是。"],
    [80, "80 km。跑得再快也追不上明天上班的闹钟。"],
  ];
  var CRASH_LINES = ["擦到一下：不痛，就是有点丢人。", "撞了？速度减半，面子减半。", "慢点慢点，路又不会跑（它会）。"];
  var NEAR_LINES = ["漂亮，差 3 厘米！", "擦肩而过，好活儿。", "对面司机骂骂咧咧地点了赞。"];
  var RING_LINES = ["氮气满格，飞！", "光带已吃，车头在发光。", "这速度，路灯都追不上你。"];
  function rnd(a) { return a[Math.floor(Math.random() * a.length)]; }

  // ---------- 声音 ----------
  function ac() {
    if (!audio) { var AC = window.AudioContext || window.webkitAudioContext; if (AC) audio = new AC(); }
    if (audio && audio.state === "suspended") audio.resume();
    return audio;
  }
  function tone(f, dur, type, vol, when, slide) {
    if (!S.sound) return;
    var a = ac(); if (!a) return;
    var t = a.currentTime + (when || 0), o = a.createOscillator(), g = a.createGain();
    o.type = type || "sine"; o.frequency.setValueAtTime(f, t);
    if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(40, slide), t + dur);
    g.gain.setValueAtTime(vol || .04, t);
    g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(g); g.connect(a.destination); o.start(t); o.stop(t + dur + .02);
  }
  function engine() { tone(60, .1, "sawtooth", .012); }
  function whoosh() { tone(900, .28, "sine", .05, 0, 180); }
  function chime() { tone(880, .14, "sine", .05); tone(1320, .2, "sine", .04, .07); }
  function crash() { tone(120, .28, "square", .07, 0, 55); }
  function fanfare() { [523, 659, 784, 1047].forEach(function (f, i) { tone(f, .3, "sine", .06, i * .14); }); }
  function buzz(ms) { if (navigator.vibrate) try { navigator.vibrate(ms); } catch (e) {} }

  // ---------- 格式 ----------
  function fmtClock(s) { var m = Math.floor(s / 60), x = Math.floor(s % 60); return m + ":" + (x < 10 ? "0" : "") + x; }
  function fmt(s) { s = Math.floor(s); var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    if (h) return h + " 小时 " + m + " 分"; if (m) return m + " 分 " + x + " 秒"; return x + " 秒"; }

  // ---------- 几何 ----------
  function roadMid(d) { var s = d * 4.0; return Math.sin(s) * .34 + Math.sin(s * 2.13 + 2) * .16; }
  function ppu(y) { var t = Math.max(0, Math.min(1, (y - H * .15) / (H * .85))); return 46 + 190 * Math.pow(t, 1.22); }
  function distAtY(y) { return S.dist + (H - y) * (VIEW_KM / (H * .85)); }

  // ---------- 背景 ----------
  function drawBack(dt) {
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#05050e"); g.addColorStop(.34, "#151233");
    g.addColorStop(.47, "#3a2a55"); g.addColorStop(.52, "#b98a54"); g.addColorStop(1, "#3a2117");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    // 星
    ctx.fillStyle = "#cfd8ff";
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i];
      var tw = .5 + .5 * Math.sin(S.sec * st.s + st.p);
      ctx.globalAlpha = .25 + .75 * tw;
      ctx.beginPath(); ctx.arc(st.x * W, st.y * H, st.r, 0, 6.283); ctx.fill();
    }
    ctx.globalAlpha = 1;
    // 城市剪影两层视差
    drawSkyline(.36, "#0a0817", S.dist * 6, 30);
    drawSkyline(.3, "#0e0a1f", S.dist * 16, 16);
    // 极光微光
    var au = ctx.createLinearGradient(0, H * .1, 0, H * .34);
    au.addColorStop(0, "rgba(90,220,180,0)"); au.addColorStop(.6, "rgba(90,220,180,.10)");
    au.addColorStop(1, "rgba(255,120,220,.05)");
    ctx.fillStyle = au; ctx.fillRect(0, H * .1, W, H * .24);
  }
  function drawSkyline(baseY, col, shift, amp) {
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.moveTo(0, H * baseY);
    var step = 24;
    for (var x = 0; x <= W; x += step) {
      var n = Math.abs(Math.sin((x + shift) * 0.013)) * amp + Math.abs(Math.sin((x * .03) + shift * .4)) * 8;
      ctx.lineTo(x, H * baseY - n);
    }
    ctx.lineTo(W, H * (baseY + .04)); ctx.lineTo(0, H * (baseY + .04));
    ctx.closePath(); ctx.fill();
  }

  // ---------- 道路（霓虹） ----------
  function drawRoad(dt) {
    var step = 8;
    // 路面
    for (var y = Math.floor(H - step); y > H * .15; y -= step) {
      var y0 = Math.min(y + step, H), y1 = y;
      var m0 = W / 2 + roadMid(distAtY(y0)) * ppu(y0);
      var m1 = W / 2 + roadMid(distAtY(y1)) * ppu(y1);
      var r0 = ROAD_HALF * ppu(y0), r1 = ROAD_HALF * ppu(y1);
      ctx.fillStyle = "#23243a";
      ctx.beginPath(); ctx.moveTo(m0 - r0, y0); ctx.lineTo(m0 + r0, y0);
      ctx.lineTo(m1 + r1, y1); ctx.lineTo(m1 - r1, y1); ctx.closePath(); ctx.fill();
      // 减速带微光 / 路面高光
      if (Math.floor(distAtY(y1) * 12) % 13 === 0) {
        ctx.fillStyle = "rgba(255,255,255,.05)";
        ctx.beginPath(); ctx.moveTo(m0 - r0, y0); ctx.lineTo(m0 + r0, y0);
        ctx.lineTo(m1 + r1, y1); ctx.lineTo(m1 - r1, y1); ctx.closePath(); ctx.fill();
      }
    }
    // 边缘霓虹
    ctx.save();
    ctx.lineCap = "round";
    for (var side = -1; side <= 1; side += 2) {
      ctx.strokeStyle = side < 0 ? "#5ee6ff" : "#ff5ea8";
      ctx.shadowColor = side < 0 ? "rgba(94,230,255,.9)" : "rgba(255,94,168,.9)";
      ctx.shadowBlur = 12; ctx.lineWidth = 3;
      ctx.beginPath();
      for (var yy = H; yy > H * .16; yy -= 5) {
        var mE = W / 2 + roadMid(distAtY(yy)) * ppu(yy) + side * (ROAD_HALF + .06) * ppu(yy);
        if (yy === H) ctx.moveTo(mE, yy); else ctx.lineTo(mE, yy);
      }
      ctx.stroke();
    }
    // 中央虚线（霓虹流动）
    var off = (S.dist * 30) % 34;
    ctx.strokeStyle = "rgba(255,220,140,.75)";
    ctx.shadowColor = "rgba(255,210,120,.8)"; ctx.shadowBlur = 8; ctx.lineWidth = 3;
    for (var dy = -34 + off; dy < H; dy += 34) {
      if (dy < H * .18) continue;
      var mC = W / 2 + roadMid(distAtY(dy)) * ppu(dy);
      var p0 = ppu(dy);
      ctx.beginPath(); ctx.moveTo(mC, dy); ctx.lineTo(mC + 4, dy + 16); ctx.stroke();
    }
    ctx.restore();
    // 路侧灯柱（极速感）
    ctx.save();
    for (var i = 0; i < 14; i++) {
      var f = ((S.dist * 46 + i * 7) % 60) / 60;
      if (f > .92) continue;
      var yy2 = H * .9 - f * H * .8;
      if (yy2 < H * .17) continue;
      for (var s2 = -1; s2 <= 1; s2 += 2) {
        var mx = W / 2 + roadMid(distAtY(yy2)) * ppu(yy2) + s2 * (ROAD_HALF + .42) * ppu(yy2);
        ctx.fillStyle = s2 < 0 ? "rgba(94,230,255,.55)" : "rgba(255,94,168,.55)";
        ctx.beginPath(); ctx.arc(mx, yy2, 2.6, 0, 6.283); ctx.fill();
      }
    }
    ctx.restore();
    if (S.shake > .3) ctx.shake = null;
  }

  // ---------- 光带（氮气门） ----------
  function spawnRing() { if (S.phase !== "play") return;
    rings.push({ a: VIEW_KM * (.3 + Math.random() * .7), lat: (Math.random() - .5) * 1.1 }); }
  function drawRings(dt) {
    var closure = S.spd / 3600;
    for (var i = rings.length - 1; i >= 0; i--) {
      var r = rings[i]; r.a -= closure * dt;
      if (r.a <= .02) { rings.splice(i, 1); continue; }
      var y = H * .15 + H * .85 * (1 - Math.max(0, r.a) / VIEW_KM);
      var cx = W / 2 + (r.lat - roadMid(distAtY(y))) * ppu(y);
      var half = ppu(y) * 1.05;
      ctx.save();
      ctx.shadowColor = "#b06bff"; ctx.shadowBlur = 16;
      var grd = ctx.createLinearGradient(cx - half, 0, cx + half, 0);
      grd.addColorStop(0, "rgba(94,230,255,0)"); grd.addColorStop(.5, "rgba(190,120,255,.95)");
      grd.addColorStop(1, "rgba(255,94,168,0)");
      ctx.fillStyle = grd;
      ctx.fillRect(cx - half, y - 26, half * 2, 52);
      ctx.restore();
      // 判定吃门
      if (y > CAR_Y - 46 && y < CAR_Y + 10 && Math.abs(S.lat - r.lat) < .9) {
        rings.splice(i, 1); S.rings++; S.boost = Math.min(100, S.boost + 40); S.boostT = 3.2;
        whoosh(); buzz(20); el.line.textContent = rnd(RING_LINES);
      }
    }
  }

  // ---------- 对向车 ----------
  function spawnCar() { if (S.phase !== "play") return;
    var dens = 1 + Math.min(1.1, S.sec / 900) + Math.min(.5, S.dist / 120);
    if (Math.random() > dens * .11) return;
    cars.push({ a: VIEW_KM * (.2 + Math.random() * .8), lat: (Math.random() - .5) * 1.75,
                passed: false, w: .9, l: 1.8,
                col: Math.random() < .5 ? "#4fd2ff" : "#ff6b9d" });
  }
  function drawCars(dt) {
    var closure = (S.spd + 88 + Math.random() * 46) / 3600;
    for (var i = cars.length - 1; i >= 0; i--) {
      var c = cars[i]; c.a -= closure * dt;
      if (c.a <= .02) { cars.splice(i, 1); continue; }
      var y = H * .15 + H * .85 * (1 - Math.max(0, c.a) / VIEW_KM);
      if (y < H * .16 || y > H + 40) continue;
      var cx = W / 2 + (c.lat - roadMid(distAtY(y))) * ppu(y);
      var w = c.w * ppu(y) * .2, h = c.l * ppu(y) * .15;
      // 对向车大灯（逼近光）
      ctx.save();
      ctx.shadowColor = "rgba(255,255,235,.6)"; ctx.shadowBlur = 14;
      ctx.fillStyle = "#ffe9a8";
      ctx.beginPath(); ctx.arc(cx - w * .24, y + h * .15, 2.6, 0, 6.283);
      ctx.arc(cx + w * .24, y + h * .15, 2.6, 0, 6.283); ctx.fill();
      ctx.shadowBlur = 0;
      // 车身
      var grad = ctx.createLinearGradient(cx - w / 2, 0, cx + w / 2, 0);
      grad.addColorStop(0, c.col); grad.addColorStop(1, "#20263f");
      ctx.fillStyle = grad;
      ctx.beginPath(); ctx.roundRect(cx - w / 2, y - h, w, h, 6); ctx.fill();
      ctx.fillStyle = "rgba(10,14,30,.6)";
      ctx.fillRect(cx - w / 2 + w * .2, y - h + h * .22, w * .6, h * .3);
      ctx.restore();
      // 判定：擦肩（无碰）与碰撞
      var gap = Math.abs(S.lat - c.lat);
      var hit = Math.abs(y - CAR_Y) < h + 30 && gap < (0.24 + c.w / 2) * 1.12 + .14;
      if (hit && S.sec - S.lastTaunt > 2.5) {
        S.lastTaunt = S.sec; S.spd = Math.max(64, S.spd - 24); S.combo = 0; S.comboT = 0;
        S.flash = .5; S.shake = 12;
        el.line.textContent = rnd(CRASH_LINES); crash(); buzz(30);
        continue;
      }
      if (!c.passed && y + h > CAR_Y - 44 && y < CAR_Y + 14) {
        c.passed = true;
        if (gap < 1.05) {
          S.combo++; S.comboT = 2.6; S.maxCombo = Math.max(S.maxCombo, S.combo);
          S.spd = Math.min(205, S.spd + 6); S.boost = Math.min(100, S.boost + 8);
          var py = CAR_Y - 12, px = cx < W / 2 ? W / 2 + 26 : W / 2 - 26;
          sparks.push({ x: px, y: py, vx: (cx > W / 2 ? -1 : 1) * 90, vy: 30, life: .5, max: .5 });
          if (S.combo % 3 === 0) el.line.textContent = rnd(NEAR_LINES);
          whoosh(); buzz(8);
        }
      }
    }
  }

  // ---------- 粒子 / 火花 ----------
  function drawSparks(dt) {
    for (var i = sparks.length - 1; i >= 0; i--) {
      var p = sparks[i];
      p.life -= dt; if (p.life <= 0) { sparks.splice(i, 1); continue; }
      p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 40 * dt;
      ctx.globalAlpha = Math.max(0, p.life / p.max) * .9;
      ctx.fillStyle = "#ffe9a8";
      ctx.beginPath(); ctx.arc(p.x, p.y, 2.4 * (p.life / p.max) + .5, 0, 6.283); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---------- 主角车（霓虹跑车） ----------
  function drawCar() {
    var cx = W / 2 + (S.lat - roadMid(distAtY(CAR_Y))) * ppu(CAR_Y) + (Math.random() - .5) * S.shake * .4;
    var boosting = S.boostT > 0;
    ctx.save();
    // 尾焰
    if (boosting) {
      for (var i = 0; i < 3; i++) {
        ctx.fillStyle = "rgba(255,150,60,.28)";
        ctx.beginPath();
        ctx.ellipse(cx + (S.lat > S.tLat ? 10 : -10) * -0 + (Math.random() * 8 - 4), CAR_Y + 34 + i * 3, 7 - i, 13 - i * 2, 0, 0, 6.283);
        ctx.fill();
      }
    }
    // 底盘霓虹
    ctx.shadowColor = "#ff4fd8"; ctx.shadowBlur = 22;
    ctx.fillStyle = "#0b0e1c";
    ctx.beginPath(); ctx.roundRect(cx - 16, CAR_Y - 34, 32, 58, 12); ctx.fill();
    ctx.shadowBlur = 0;
    // 车身渐变
    var body = ctx.createLinearGradient(cx - 16, 0, cx + 16, 0);
    body.addColorStop(0, boosting ? "#7fb0ff" : "#3d5bff");
    body.addColorStop(.5, "#1c2450");
    body.addColorStop(1, "#10173a");
    ctx.fillStyle = body;
    ctx.beginPath(); ctx.roundRect(cx - 14, CAR_Y - 32, 28, 54, 11); ctx.fill();
    // 车灯
    ctx.fillStyle = "#ffe9a8";
    ctx.beginPath(); ctx.arc(cx - 7, CAR_Y - 28, 3.4, 0, 6.283); ctx.arc(cx + 7, CAR_Y - 28, 3.4, 0, 6.283); ctx.fill();
    // 座舱
    ctx.fillStyle = "#0a0f24";
    ctx.beginPath(); ctx.roundRect(cx - 9, CAR_Y - 24, 18, 14, 5); ctx.fill();
    ctx.fillStyle = "rgba(127,176,255,.85)";
    ctx.fillRect(cx - 6, CAR_Y - 22, 4, 6); ctx.fillRect(cx + 2, CAR_Y - 22, 4, 6);
    // 尾灯
    ctx.fillStyle = boosting ? "#ff5ea8" : "#b0305a";
    ctx.beginPath(); ctx.arc(cx - 8, CAR_Y + 20, 3, 0, 6.283); ctx.arc(cx + 8, CAR_Y + 20, 3, 0, 6.283); ctx.fill();
    ctx.restore();
  }

  // ---------- 主循环 ----------
  function frame(ts) {
    if (S.phase === "play" && S.last) {
      var dt = Math.min((ts - S.last) / 1000, .12);
      if (!document.hidden) {
        S.sec += dt;
        // 难度缓增
        S.spd = Math.min(150, 96 + S.sec * .018 + S.dist * .02);
        if (S.boostT > 0) { S.boostT -= dt; S.spd = Math.min(235, S.spd + 70); }
        // 氮气能量消耗 + 自然回复
        if (S.boost <= 0) S.boost = Math.min(100, S.boost + .4);
        // 连击计时
        if (S.comboT > 0) { S.comboT -= dt; if (S.comboT <= 0) S.combo = 0; }
        var ds = (S.spd / 3600) * dt;
        S.dist += ds;
        S.lat += (S.tLat - S.lat) * Math.min(1, dt * 5.4);
        var midNow = roadMid(S.dist);
        if (Math.abs(S.lat - midNow) > ROAD_HALF * .8) { S.spd = Math.max(56, S.spd - 3 * dt); S.shake = Math.max(S.shake, 5); }
        else S.shake *= .86;
        if (S.flash > 0) S.flash = Math.max(0, S.flash - dt * 1.6);
        var dInt = Math.floor(S.dist);
        if (dInt > 0 && dInt % 5 === 0 && dInt !== Math.floor(S.dist - ds)) {
          el.line.textContent = TAUNTS.reduce(function (acc, t) { return dInt >= t[0] ? t : acc; })[1];
        }
        spawnCar(); spawnRing();
        if (S.sec >= S.mode) finish();
      }
      S.last = ts;
      updateHud();
    } else { S.last = ts; }
    drawBack(1);
    drawRoad(1);
    drawRings(1);
    drawCars(1);
    drawSparks(1);
    if (S.phase === "play") { drawCar(); engine(); }
    // 撞击红闪
    if (S.flash > 0) {
      ctx.fillStyle = "rgba(255,40,80," + (S.flash * .32).toFixed(3) + ")";
      ctx.fillRect(0, 0, W, H);
    }
    requestAnimationFrame(frame);
  }

  function updateHud() {
    el.km.textContent = S.dist.toFixed(1);
    el.spd.textContent = Math.round(S.spd);
    el.combo.textContent = S.combo;
    el.boostBar.style.width = S.boost + "%";
  }

  // ---------- 流程 ----------
  function finish() {
    S.phase = "final";
    var rec = { id: S.pid, sec: Math.floor(S.sec), dist: S.dist, combo: S.maxCombo };
    attempts.push(rec); renderBoard();
    var rank = rankOf(rec);
    el.fscore.textContent = S.pid + " 狂飙 " + S.dist.toFixed(1) + " km · 最佳连击 ×" + S.maxCombo
      + " · 氮气 " + S.rings + " 门 · 用时 " + fmt(S.sec);
    el.frank.textContent = rank === 1 ? "🏆 本场唯一午夜车神（暂时）。" : "大神榜第 " + rank + " 名。前面的车更快。";
    el.mock.textContent = "🏁 恭喜，你孤独地浪费了 " + fmt(S.sec) + "。前方没有出口，也没有人等你。";
    el.final.classList.remove("hidden");
    fanfare(); buzz([20, 60, 20, 60, 30]);
  }

  function sorted() { return attempts.slice().sort(function (a, b) { return a.sec - b.sec; }).slice(0, 3); }
  function rankOf(rec) { var r = 1; attempts.forEach(function (x) { if (x.sec < rec.sec || (x.sec === rec.sec && x !== rec)) r++; }); return r; }
  function renderBoard() {
    var top = sorted(), html = "<h3>🏆 大神榜（霓虹等级）</h3>";
    if (!top.length) html += "<p style='text-align:center;color:#6f76a8'>还没人敢开完，等你破纪录。</p>";
    else { html += "<ol>"; top.forEach(function (a) { html += "<li><b>" + a.id + "</b> · " + a.dist.toFixed(1) + " km · 连击×" + a.combo + " · " + fmt(a.sec) + "</li>"; }); html += "</ol>"; }
    el.board.innerHTML = html;
  }

  function startRun(modeSec) {
    S.pid = (el.pid.value || "").trim() || "无名氏";
    S.phase = "play"; S.mode = modeSec; S.sec = 0; S.last = 0; S.dist = 0;
    S.lat = 0; S.tLat = 0; S.spd = 96; S.shake = 0; S.flash = 0;
    S.boost = 40; S.boostT = 0; S.combo = 0; S.comboT = 0; S.maxCombo = 0; S.rings = 0;
    cars = []; rings = []; sparks = [];
    el.overlay.classList.add("hidden"); el.final.classList.add("hidden");
    el.km.textContent = "0.0"; el.spd.textContent = "96"; el.combo.textContent = "0";
    el.line.textContent = "出发。把油门踩进霓虹里。";
    updateHud();
  }

  // ---------- 输入 ----------
  var dragging = false;
  function steer(px) { S.tLat = Math.max(-1.5, Math.min(1.5, (px / W - .5) * 4.8)); }
  cv.addEventListener("pointerdown", function (e) { if (S.phase !== "play") return; dragging = true; cv.setPointerCapture(e.pointerId); steer(e.clientX); });
  cv.addEventListener("pointermove", function (e) { if (dragging && S.phase === "play") steer(e.clientX); });
  cv.addEventListener("pointerup", function () { dragging = false; if (S.phase === "play") S.tLat = 0; });
  window.addEventListener("keydown", function (e) {
    if (S.phase !== "play") return;
    if (e.key === "ArrowLeft" || e.key === "a") S.tLat = -1.45;
    if (e.key === "ArrowRight" || e.key === "d") S.tLat = 1.45;
  });
  window.addEventListener("keyup", function (e) {
    if (e.key === "ArrowLeft" || e.key === "a" || e.key === "ArrowRight" || e.key === "d") { if (!dragging) S.tLat = 0; }
  });
  el.m40.addEventListener("pointerdown", function (e) { e.preventDefault(); startRun(MODE.formal); });
  el.m1.addEventListener("pointerdown", function (e) { e.preventDefault(); startRun(MODE.demo); });
  el.again.addEventListener("pointerdown", function (e) { e.preventDefault(); el.final.classList.add("hidden"); startRun(MODE.formal); });
  el.snd.addEventListener("pointerdown", function (e) { e.preventDefault(); S.sound = !S.sound; el.snd.textContent = S.sound ? "🔊" : "🔇"; });

  resize(); renderBoard(); updateHud();
  requestAnimationFrame(frame);
})();
