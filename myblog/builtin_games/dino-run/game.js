/* 恐龙快跑 —— 原创像素风无尽跑酷
   自包含：无网络请求、无 eval、无存储读写、无外部资源。 */
(function () {
  'use strict';

  var canvas = document.getElementById('game');
  var ctx = canvas.getContext('2d');
  var W = canvas.width;
  var H = canvas.height;

  var GROUND_Y = 258;          // 地面基线（恐龙脚底）
  var GRAVITY = 2500;          // px/s^2
  var JUMP_V = -880;           // 起跳速度
  var FAST_DROP = 2600;        // 下蹲快速下落
  var BASE_SPEED = 380;        // 初始速度 px/s
  var MAX_SPEED = 900;
  var DAY_LEN = 45;            // 昼夜切换秒数

  var dino = {
    x: 70, y: GROUND_Y, w: 44, h: 47,
    vy: 0, onGround: true, duck: false,
    runT: 0, dead: false
  };

  var obstacles = [];   // {type, x, y, w, h, frame}
  var clouds = [];
  var ground = [];      // 地面碎石装饰 {x, len}
  var stars = [];

  var speed = BASE_SPEED;
  var dist = 0;
  var score = 0;
  var hi = 0;           // 仅内存记录（沙箱禁存储）
  var state = 'ready';  // ready | run | over
  var night = false;
  var phaseT = 0;
  var last = 0;
  var soundOn = true;
  var spawnGap = 0;     // 生成倒计时秒
  var shake = 0;

  // ---------- 音效（WebAudio 本地合成） ----------
  var AC = null;
  function ac() {
    if (!AC) {
      var C = window.AudioContext || window.webkitAudioContext;
      if (C) AC = new C();
    }
    return AC;
  }
  function beep(freq, dur, type, vol, slide) {
    if (!soundOn) return;
    var a = ac();
    if (!a) return;
    try {
      var o = a.createOscillator(), g = a.createGain();
      o.type = type || 'square';
      o.frequency.value = freq;
      if (slide) o.frequency.exponentialRampToValueAtTime(slide, a.currentTime + dur);
      g.gain.setValueAtTime(vol || 0.06, a.currentTime);
      g.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + dur);
      o.connect(g); g.connect(a.destination);
      o.start(); o.stop(a.currentTime + dur);
    } catch (e) { /* 静音环境忽略 */ }
  }
  var sfx = {
    jump: function () { beep(440, 0.12, 'square', 0.05, 660); },
    duck: function () { beep(240, 0.08, 'square', 0.04); },
    point: function () { beep(880, 0.09, 'sine', 0.05, 1180); },
    die: function () { beep(300, 0.35, 'sawtooth', 0.08, 90); }
  };

  // ---------- 输入 ----------
  function jump() {
    if (state === 'ready') { start(); return; }
    if (state === 'over') { reset(); start(); return; }
    if (dino.onGround) {
      dino.vy = JUMP_V;
      dino.onGround = false;
      dino.duck = false;
      sfx.jump();
    }
  }
  function setDuck(on) {
    if (on && !dino.duck && !dino.onGround) dino.vy = Math.max(dino.vy, 200);
    dino.duck = on;
    if (on && state === 'run' && dino.onGround) sfx.duck();
  }

  document.addEventListener('keydown', function (e) {
    var k = e.code;
    if (k === 'Space' || k === 'ArrowUp' || k === 'KeyW') { e.preventDefault(); jump(); }
    else if (k === 'ArrowDown' || k === 'KeyS') { e.preventDefault(); setDuck(true); }
    else if (k === 'KeyM') { soundOn = !soundOn; }
  });
  document.addEventListener('keyup', function (e) {
    var k = e.code;
    if (k === 'ArrowDown' || k === 'KeyS') setDuck(false);
  });

  // 触屏：上半屏跳、下半屏蹲
  canvas.addEventListener('touchstart', function (e) {
    e.preventDefault();
    var t = e.changedTouches[0];
    var r = canvas.getBoundingClientRect();
    if ((t.clientY - r.top) / r.height > 0.55) setDuck(true); else jump();
  }, { passive: false });
  canvas.addEventListener('touchend', function (e) {
    e.preventDefault(); setDuck(false);
  }, { passive: false });
  canvas.addEventListener('mousedown', function () { jump(); });

  // ---------- 障碍物 ----------
  var CACTI = [
    { s: 1, w: 17, h: 35 }, { s: 2, w: 33, h: 35 },
    { s: 3, w: 50, h: 35 }, { s: 1, w: 17, h: 48 },
    { s: 2, w: 33, h: 48 }
  ];
  function spawn() {
    var r = Math.random();
    var speed01 = (speed - BASE_SPEED) / (MAX_SPEED - BASE_SPEED);
    if (r < 0.18 + 0.12 * speed01) {
      // 翼龙三档：低=必须跳；中=必须蹲（蹲下高度 228px 恰好从下方穿过）；
      // 高=站跑即可通过（装饰性压迫感）
      var lanes = [GROUND_Y - 30, GROUND_Y - 58, GROUND_Y - 88];
      var y = lanes[Math.floor(Math.random() * 3)];
      obstacles.push({ type: 'bird', x: W + 30, y: y, w: 40, h: 26, frame: 0 });
    } else {
      var c = CACTI[Math.floor(Math.random() * CACTI.length)];
      obstacles.push({ type: 'cactus', x: W + 30, y: GROUND_Y - c.h, w: c.w, h: c.h });
    }
    // 间隔随速度缩小但保证可反应
    var gapPx = 300 + Math.random() * 320 - speed01 * 90;
    spawnGap = Math.max(0.55, gapPx / speed);
  }

  // ---------- 碰撞（AABB 略缩边） ----------
  function hit(a, b) {
    var m = 4;
    return a.x + m < b.x + b.w && a.x + a.w - m > b.x &&
           a.y - a.h + m < b.y + b.h && a.y - m > b.y;
  }

  // ---------- 主循环 ----------
  function step(dt) {
    if (state !== 'run') {
      if (state === 'over') { shake = Math.max(0, shake - dt * 6); }
      return;
    }

    speed = Math.min(MAX_SPEED, speed + dt * 7);
    dist += speed * dt;
    score = Math.floor(dist / 10);

    // 得分提示音：每过 100 分
    if (Math.floor(score / 100) > Math.floor((score - speed * dt / 10) / 100)) sfx.point();

    // 昼夜
    phaseT += dt;
    if (phaseT > DAY_LEN) { phaseT = 0; night = !night; }

    // 恐龙
    dino.runT += dt;
    if (!dino.onGround) {
      dino.vy += (dino.duck ? FAST_DROP : GRAVITY) * dt;
      dino.y += dino.vy * dt;
      if (dino.y >= GROUND_Y) { dino.y = GROUND_Y; dino.vy = 0; dino.onGround = true; }
    }

    // 生成障碍
    spawnGap -= dt;
    if (spawnGap <= 0) spawn();

    // 移动障碍 / 装饰
    var i;
    for (i = obstacles.length - 1; i >= 0; i--) {
      obstacles[i].x -= speed * dt;
      if (obstacles[i].x + obstacles[i].w < -20) obstacles.splice(i, 1);
    }
    for (i = clouds.length - 1; i >= 0; i--) {
      clouds[i].x -= (speed * 0.12 + 12) * dt;
      if (clouds[i].x < -80) { clouds[i].x = W + 60; clouds[i].y = 30 + Math.random() * 90; }
    }
    for (i = ground.length - 1; i >= 0; i--) {
      ground[i].x -= speed * dt;
      if (ground[i].x < -40) { ground[i].x = W + Math.random() * 60; }
    }

    // 碰撞
    var box = dino.duck ? { x: dino.x, y: dino.y, w: 46, h: 30 } : { x: dino.x, y: dino.y, w: dino.w, h: dino.h };
    for (i = 0; i < obstacles.length; i++) {
      if (hit(box, obstacles[i])) {
        state = 'over';
        dino.dead = true;
        shake = 1;
        sfx.die();
        if (score > hi) hi = score;
        return;
      }
    }
  }

  // ---------- 绘制 ----------
  function px(x, y, w, h, c) {
    ctx.fillStyle = c;
    ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
  }

  function drawDino() {
    var ink = night ? '#e8e8e8' : '#535353';
    var x = dino.x, y;
    if (dino.duck) {
      y = dino.y - 30;
      // 蹲姿：拉长身体
      px(x, y + 12, 42, 12, ink);          // 身体
      px(x + 6, y + 22, 16, 8, ink);       // 尾下
      px(x + 40, y + 6, 12, 12, ink);      // 头
      px(x + 48, y + 9, 3, 3, night ? '#535353' : '#f7f7f7'); // 眼
      px(x + 50, y + 14, 4, 2, ink);       // 嘴
      // 腿交替
      var f = Math.floor(dino.runT * 10) % 2;
      px(x + 8 + f * 6, y + 24, 6, 6, ink);
      px(x + 22 - f * 6, y + 24, 6, 6, ink);
    } else if (dino.dead) {
      y = dino.y - dino.h;
      px(x, y + 10, 26, 26, ink);
      px(x + 20, y, 18, 16, ink);
      px(x + 24, y + 4, 4, 5, ink);        // X 眼
      px(x + 30, y + 5, 3, 4, ink);
      px(x - 10, y + 18, 12, 6, ink);      // 尾
      px(x + 4, y + 36, 8, 11, ink);
      px(x + 16, y + 36, 8, 11, ink);
    } else {
      y = dino.y - dino.h;
      px(x - 10, y + 20, 14, 8, ink);      // 尾
      px(x + 2, y + 10, 26, 26, ink);      // 身体
      px(x + 20, y, 20, 17, ink);          // 头
      px(x + 26, y + 4, 4, 5, night ? '#535353' : '#f7f7f7'); // 眼
      px(x + 36, y + 8, 6, 3, ink);        // 嘴前
      px(x + 12, y + 18, 8, 5, ink);       // 小手
      var f = Math.floor(dino.runT * (8 + speed / 100)) % 2;
      if (dino.onGround) {
        px(x + 4, y + 36 + (f ? 0 : 0), 8, 11 - (f ? 1 : 0), ink);
        px(x + 16, y + 36 + (f ? 0 : 0), 8, 11 - (f ? 0 : 1), ink);
      } else {
        px(x + 4, y + 36, 8, 11, ink);
        px(x + 16, y + 36, 8, 10, ink);
      }
    }
  }

  function drawCactus(o) {
    var ink = night ? '#c9c9c9' : '#4a4a4a';
    var x = o.x, y = o.y;
    var stemW = o.w >= 33 ? 10 : 8;
    px(x + (o.w - stemW) / 2, y, stemW, o.h, ink);
    if (o.w >= 33) {
      px(x, y + 10, 8, 6, ink); px(x, y + 10, 4, 16, ink);
      px(x + o.w - 8, y + 16, 8, 6, ink); px(x + o.w - 4, y + 16, 4, 14, ink);
    } else {
      px(x - 2, y + 14, 6, 5, ink); px(x - 2, y + 14, 3, 10, ink);
      px(x + o.w - 4, y + 20, 6, 5, ink); px(x + o.w - 1, y + 20, 3, 9, ink);
    }
  }

  function drawBird(o) {
    var ink = night ? '#dcdcdc' : '#535353';
    o.frame += 0.2;
    var up = Math.floor(o.frame) % 2 === 0;
    var x = o.x, y = o.y;
    px(x + 12, y + 8, 24, 10, ink);              // 身
    px(x + 30, y + 4, 10, 8, ink);               // 头
    px(x + 38, y + 6, 4, 3, ink);                // 喙
    px(x + 34, y + 5, 2, 2, night ? '#535353' : '#f7f7f7'); // 眼
    if (up) { px(x + 14, y, 12, 9, ink); px(x + 6, y + 2, 9, 5, ink); }
    else    { px(x + 14, y + 15, 12, 8, ink); px(x + 6, y + 19, 9, 4, ink); }
  }

  function drawText(t, x, y, size, align) {
    ctx.fillStyle = night ? '#d8d8d8' : '#535353';
    ctx.font = 'bold ' + size + 'px "Segoe UI", "Microsoft YaHei", monospace';
    ctx.textAlign = align || 'right';
    ctx.fillText(t, x, y);
  }

  function draw() {
    var bg = night ? '#1b1b1b' : '#f7f7f7';
    var fg = night ? '#e0e0e0' : '#535353';

    ctx.save();
    if (shake > 0) {
      ctx.translate((Math.random() - 0.5) * 8 * shake, (Math.random() - 0.5) * 6 * shake);
    }

    px(-10, -10, W + 20, H + 20, bg);

    // 星星（夜晚）
    if (night) {
      for (var s = 0; s < stars.length; s++) {
        var st = stars[s];
        px(st.x, st.y + Math.sin(phaseT * 2 + st.x) * 1.5, 2, 2, '#9a9a9a');
      }
      // 月亮
      px(W - 130, 40, 26, 26, '#d8d8d8');
      px(W - 122, 36, 20, 20, bg);
    }

    // 云
    for (var c = 0; c < clouds.length; c++) {
      var cl = clouds[c];
      px(cl.x, cl.y, 34, 10, night ? '#3a3a3a' : '#d9d9d9');
      px(cl.x + 8, cl.y - 7, 22, 8, night ? '#3a3a3a' : '#d9d9d9');
    }

    // 地面
    px(0, GROUND_Y + 2, W, 2, fg);
    for (var g = 0; g < ground.length; g++) {
      px(ground[g].x, GROUND_Y + 8, ground[g].len, 2, night ? '#4a4a4a' : '#b5b5b5');
    }

    for (var i = 0; i < obstacles.length; i++) {
      var o = obstacles[i];
      if (o.type === 'cactus') drawCactus(o); else drawBird(o);
    }

    drawDino();

    // 记分板
    var tag = night ? '夜' : '昼';
    drawText('HI ' + pad(hi) + '  ' + pad(score) + '  ' + tag, W - 18, 34, 15);

    if (state === 'ready') {
      drawText('恐龙快跑', W / 2, 120, 30, 'center');
      drawText('按 空格 / 点击 开始 · ↓ 蹲下避开翼龙', W / 2, 155, 14, 'center');
    } else if (state === 'over') {
      drawText('G A M E   O V E R', W / 2, 110, 26, 'center');
      drawText('按 空格 / 点击 重新开始', W / 2, 145, 14, 'center');
      drawText('本局 ' + score + ' · 最高 ' + hi, W / 2, 170, 14, 'center');
    }

    ctx.restore();
  }

  function pad(n) {
    n = String(n);
    while (n.length < 5) n = '0' + n;
    return n;
  }

  function initDecor() {
    clouds.length = 0; ground.length = 0; stars.length = 0;
    for (var i = 0; i < 4; i++) clouds.push({ x: Math.random() * W, y: 30 + Math.random() * 90 });
    for (var j = 0; j < 10; j++) ground.push({ x: Math.random() * W, len: 6 + Math.random() * 22 });
    for (var k = 0; k < 26; k++) stars.push({ x: Math.random() * W, y: Math.random() * 160 });
  }

  function reset() {
    obstacles.length = 0;
    speed = BASE_SPEED; dist = 0; score = 0;
    phaseT = 0; night = false;
    spawnGap = 1.2;
    dino.y = GROUND_Y; dino.vy = 0; dino.onGround = true; dino.duck = false; dino.dead = false;
    dino.runT = 0;
    initDecor();
  }

  function start() {
    if (state === 'ready' || state === 'over') {
      reset();
      state = 'run';
      if (ac() && ac().state === 'suspended') ac().resume();
    }
  }

  function loop(t) {
    if (!last) last = t;
    var dt = Math.min(0.05, (t - last) / 1000);
    last = t;
    step(dt);
    draw();
    requestAnimationFrame(loop);
  }

  reset();
  requestAnimationFrame(loop);
})();
