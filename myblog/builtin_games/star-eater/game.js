/* 贪吃星 —— 单文件、无依赖、纯 Canvas。
 *
 * 设计要点：
 * - 格子逻辑（COLS×ROWS），移动按"步"推进而非按帧，避免高速穿墙；
 * - 移动端优先：滑动 + 方向键双通道，方向键做 180° 反向拦截；
 * - 最高分只落 localStorage，读写都包 try（沙箱内 localStorage 可能被限制，
 *   抛异常会让整个游戏初始化失败 —— 宁可没最高分也不能开不了局）。
 */
(function () {
  "use strict";

  var COLS = 15, ROWS = 15, BASE_MS = 132, MIN_MS = 62;
  var BEST_KEY = "star-eater.best";

  var cv = document.getElementById("cv");
  var ctx = cv.getContext("2d");
  var scoreV = document.getElementById("scoreV");
  var lenV = document.getElementById("lenV");
  var bestV = document.getElementById("bestV");
  var overlay = document.getElementById("overlay");
  var ovtitle = document.getElementById("ovtitle");
  var ovmsg = document.getElementById("ovmsg");
  var pad = document.getElementById("pad");

  var snake, dir, nextDir, food, score, alive, acc, last, timer, started;

  function readBest() {
    try { return parseInt(localStorage.getItem(BEST_KEY) || "0", 10) || 0; }
    catch (e) { return 0; }
  }
  function writeBest(v) {
    try { localStorage.setItem(BEST_KEY, String(v)); } catch (e) { /* 沙箱禁存储则忽略 */ }
  }

  // 触摸设备才显示方向按钮：桌面上它只会碍事
  if (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) {
    pad.classList.add("show");
  }

  function reset() {
    var cy = Math.floor(ROWS / 2);
    snake = [{ x: 4, y: cy }, { x: 3, y: cy }, { x: 2, y: cy }];
    dir = { x: 1, y: 0 };
    nextDir = { x: 1, y: 0 };
    score = 0;
    alive = true;
    acc = 0;
    last = 0;
    placeFood();
    paintScores();
    hideOverlay();
  }

  function placeFood() {
    var free = [], x, y;
    for (y = 0; y < ROWS; y++) {
      for (x = 0; x < COLS; x++) {
        if (!hit(x, y)) free.push({ x: x, y: y });
      }
    }
    // free 为空 = 棋盘被占满 = 通关
    food = free.length ? free[(Math.random() * free.length) | 0] : null;
    if (!food) alive = false;
  }

  function hit(x, y) {
    for (var i = 0; i < snake.length; i++) {
      if (snake[i].x === x && snake[i].y === y) return true;
    }
    return false;
  }

  function step() {
    dir = nextDir;
    var head = snake[0];
    var nx = head.x + dir.x, ny = head.y + dir.y;

    if (nx < 0 || ny < 0 || nx >= COLS || ny >= ROWS) return die("撞到边界了");
    // 尾巴这一步会让位，所以撞到尾尖不算死（经典规则）
    for (var i = 0; i < snake.length - 1; i++) {
      if (snake[i].x === nx && snake[i].y === ny) return die("咬到自己了");
    }

    snake.unshift({ x: nx, y: ny });
    if (food && nx === food.x && ny === food.y) {
      score += 1;
      paintScores();
      placeFood();          // 内部可能置 alive=false（棋盘填满）
      if (!alive) { end("占满了整片星空", "你把 " + COLS + "×" + ROWS + " 格全吃完了，无人能敌"); return; }
    } else {
      snake.pop();
    }
  }

  function die(why) { die.reason = why; end("游戏结束", why); }
  die.reason = "";

  function end(title, msg) {
    alive = false;
    var best = readBest();
    var isBest = score > best;
    if (isBest) { best = score; writeBest(best); }
    bestV.textContent = best;
    ovtitle.textContent = title;
    ovmsg.textContent = msg + "　本局 " + score + " 分" +
      (isBest ? "（新纪录！）" : "　最高 " + best);
    overlay.classList.add("show");
  }

  function hideOverlay() { overlay.classList.remove("show"); }

  function paintScores() {
    scoreV.textContent = score;
    lenV.textContent = snake.length;
    bestV.textContent = readBest();
  }

  // 速度随长度提升，封顶 MIN_MS
  function interval() {
    return Math.max(MIN_MS, BASE_MS - (snake.length - 3) * 7);
  }

  function draw() {
    var w = cv.width, cell = w / COLS;
    ctx.clearRect(0, 0, w, w);

    // 棋盘底纹
    for (var y = 0; y < ROWS; y++) {
      for (var x = 0; x < COLS; x++) {
        if ((x + y) % 2 === 0) {
          ctx.fillStyle = "rgba(255,255,255,.022)";
          ctx.fillRect(x * cell, y * cell, cell, cell);
        }
      }
    }

    if (food) {
      var cx = food.x * cell + cell / 2, cy = food.y * cell + cell / 2;
      var g = ctx.createRadialGradient(cx, cy, 1, cx, cy, cell * 0.46);
      g.addColorStop(0, "#ffe9a8"); g.addColorStop(1, "rgba(255,200,90,0)");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(cx, cy, cell * 0.46, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#ffd66b";
      ctx.beginPath(); ctx.arc(cx, cy, cell * 0.19, 0, Math.PI * 2); ctx.fill();
    }

    for (var i = snake.length - 1; i >= 0; i--) {
      var s = snake[i];
      ctx.fillStyle = i === 0 ? "#9fd0ff" : (i % 2 ? "#5f8ddb" : "#6f9ce6");
      var pad = cell * (i === 0 ? 0.08 : 0.13);
      round(s.x * cell + pad, s.y * cell + pad, cell - pad * 2, cell - pad * 2, cell * 0.28);
    }
  }

  function round(x, y, w, h, r) {
    ctx.beginPath();
    if (ctx.roundRect) { ctx.roundRect(x, y, w, h, r); }
    else {
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + w, y, x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x, y + h, r);
      ctx.arcTo(x, y + h, x, y, r);
      ctx.arcTo(x, y, x + w, y, r);
      ctx.closePath();
    }
    ctx.fill();
  }

  function loop(ts) {
    if (!started) return;
    if (!last) last = ts;
    var dt = ts - last;
    last = ts;

    if (alive) {
      acc += dt;
      var iv = interval();
      while (acc >= iv && alive) { acc -= iv; step(); }
    }
    draw();
    timer = requestAnimationFrame(loop);
  }

  function setDir(d) {
    // 禁止 180° 掉头（当前尾巴会让位那种极端情况也不允许，避免瞬移感）
    if (d.x === -dir.x && d.y === -dir.y) return;
    nextDir = d;
  }

  var DIRS = {
    up: { x: 0, y: -1 }, down: { x: 0, y: 1 },
    left: { x: -1, y: 0 }, right: { x: 1, y: 0 }
  };

  document.addEventListener("keydown", function (e) {
    var m = {
      ArrowUp: DIRS.up, ArrowDown: DIRS.down,
      ArrowLeft: DIRS.left, ArrowRight: DIRS.right,
      w: DIRS.up, s: DIRS.down, a: DIRS.left, d: DIRS.right,
      W: DIRS.up, S: DIRS.down, A: DIRS.left, D: DIRS.right
    }[e.key];
    if (!m) return;
    e.preventDefault();
    setDir(m);
  });

  var hold = null, rep = null;
  Array.prototype.forEach.call(pad.querySelectorAll("button"), function (b) {
    function go(e) {
      e.preventDefault();
      setDir(DIRS[b.getAttribute("data-dir")]);
    }
    b.addEventListener("pointerdown", function (e) {
      go(e);
      // 长按连发：先等 280ms，再每 110ms 重复
      hold = setTimeout(function () {
        rep = setInterval(function () { setDir(DIRS[b.getAttribute("data-dir")]); }, 110);
      }, 280);
    });
    ["pointerup", "pointerleave", "pointercancel"].forEach(function (ev) {
      b.addEventListener(ev, function () {
        clearTimeout(hold); clearInterval(rep); hold = rep = null;
      });
    });
  });

  // 滑动：位移超过阈值即转向
  var sx = 0, sy = 0, tracking = false;
  cv.addEventListener("pointerdown", function (e) {
    tracking = true; sx = e.clientX; sy = e.clientY;
  });
  cv.addEventListener("pointermove", function (e) {
    if (!tracking) return;
    var dx = e.clientX - sx, dy = e.clientY - sy;
    if (Math.abs(dx) < 18 && Math.abs(dy) < 18) return;
    setDir(Math.abs(dx) > Math.abs(dy)
      ? (dx > 0 ? DIRS.right : DIRS.left)
      : (dy > 0 ? DIRS.down : DIRS.up));
    sx = e.clientX; sy = e.clientY;
  });
  ["pointerup", "pointerleave", "pointercancel"].forEach(function (ev) {
    cv.addEventListener(ev, function () { tracking = false; });
  });

  document.getElementById("again").addEventListener("click", function () {
    reset();
    last = 0;
  });

  // 页面隐藏时暂停，回来别一次性补上大量步数
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { last = 0; acc = 0; }
  });

  // 高分屏下把画布放大到 CSS 尺寸的 2 倍，避免糊
  function fit() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var cssW = cv.clientWidth || 360;
    cv.width = cv.height = Math.round(cssW * dpr);
  }
  window.addEventListener("resize", fit);

  fit();
  reset();
  started = true;
  timer = requestAnimationFrame(loop);
}());