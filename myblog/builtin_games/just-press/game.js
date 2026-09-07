/* 就是按一下 —— 40 分钟的人生税（纯原创，无外部资源）
 * 第 1 关：狂按 2400 下（静态按钮）
 * 第 2 关：按钮会逃，追着按 1200 下
 * 通关后按“真实用时”弹嘲讽；页内大神榜记录 ID + 用时。
 */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var L1 = 2400, L2 = 1200;           // 两关目标
  var state = {
    phase: "ready", lvl: 1, taps: 0, l1done: 0, l2done: 0,
    totalTaps: 0, sec: 0, lastTs: 0, startedAt: 0,
    sound: true, pid: "无名氏", mutedHint: false,
  };
  var attempts = [];                  // 本场大神榜 {id, sec, taps}
  var audio = null;

  var el = {
    lvl: $("lvl"), cur: $("cur"), tar: $("tar"), line: $("line"),
    tnum: $("tnum"), ring: $("ring"), rate: $("rate"), press: $("press"),
    overlay: $("overlay"), board: $("board"), pid: $("pid"),
    start: $("start"), snd: $("snd"), final: $("final"), again: $("again"),
    fscore: $("fscore"), frank: $("frank"), mock: $("mock"),
  };

  var TARGET = function () { return state.lvl === 1 ? L1 : L2; };

  // ---------- 文案 ----------
  var LINES1 = [
    [50, "才 50 下，你是在给按钮挠痒吗？"],
    [300, "很好，手指已进入无意识状态。"],
    [800, "隔壁电焊工看你的眼神都变了。"],
    [1500, "你已经按了半场，但人生也按掉了一角。"],
    [2100, "快了。机器已经开始崇拜你了。"],
  ];
  var LINES2 = [
    [50, "它跑了！它竟然跑了！"],
    [300, "你以为你在玩游戏，其实是按钮在遛你。"],
    [600, "半程了，按钮开始喘，你更喘。"],
    [1000, "抓它！抓住那个不让你下班的东西！"],
  ];
  var MILE = [10, 50, 100, 300, 600, 900, 1200, 1600, 2000, 2400];

  function pick(lines, v) {
    var cur = lines[0];
    for (var i = 0; i < lines.length; i++) { if (v >= lines[i][0]) cur = lines[i]; }
    return cur[1];
  }

  // ---------- 声音（离线合成） ----------
  function ac() {
    if (!audio) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (AC) audio = new AC();
    }
    if (audio && audio.state === "suspended") audio.resume();
    return audio;
  }
  function tone(freq, dur, type, vol, when) {
    if (!state.sound) return;
    var a = ac(); if (!a) return;
    var t = a.currentTime + (when || 0);
    var o = a.createOscillator(), g = a.createGain();
    o.type = type || "sine"; o.frequency.value = freq;
    g.gain.setValueAtTime(vol || 0.04, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(a.destination);
    o.start(t); o.stop(t + dur + 0.02);
  }
  function tick() { tone(620 + Math.random() * 240, 0.05, "triangle", 0.02); }
  function chime() { tone(880, 0.16, "sine", 0.05); tone(1320, 0.22, "sine", 0.04, 0.07); }
  function fanfare() { [523, 659, 784, 1047].forEach(function (f, i) { tone(f, 0.28, "sine", 0.06, i * 0.13); }); }
  function buzz(ms) { if (navigator.vibrate) try { navigator.vibrate(ms); } catch (e) {} }

  // ---------- 计时 ----------
  function fmt(sec) {
    sec = Math.floor(sec);
    var h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    if (h > 0) return h + " 小时 " + m + " 分";
    if (m > 0) return m + " 分 " + s + " 秒";
    return s + " 秒";
  }
  function fmtClock(sec) {
    var m = Math.floor(sec / 60), s = Math.floor(sec % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
  }
  function renderClock() {
    el.tnum.textContent = fmtClock(state.sec);
    var frac = Math.min(state.sec / 2400, 1); // 以 40 分钟估算画环
    el.ring.style.strokeDashoffset = (289 * (1 - frac)).toFixed(1);
    el.rate.textContent = state.sec > 0
      ? (state.totalTaps / state.sec).toFixed(1) + " 下/秒 · 已按 " + state.totalTaps
      : "0.0 下/秒";
  }

  // ---------- 第 2 关：按钮逃跑 ----------
  function dodge() {
    if (state.lvl !== 2 || state.phase !== "play") return;
    var arena = el.press.parentElement;
    var aw = arena.clientWidth, ah = arena.clientHeight;
    var bw = el.press.offsetWidth, bh = el.press.offsetHeight;
    var x = Math.random() * Math.max(0, aw - bw);
    var y = Math.random() * Math.max(0, ah - bh);
    el.press.style.left = x + "px";
    el.press.style.top = y + "px";
    el.press.style.transform = "translate(0,0)";
  }
  function centerBtn() {
    el.press.style.left = "50%";
    el.press.style.top = "50%";
    el.press.style.transform = "translate(-50%,-50%)";
  }

  // ---------- 关卡切换 ----------
  function levelUp() {
    state.lvl = 2; state.l1done = L1;
    el.lvl.textContent = "第 2 关 · 会跑的按钮";
    el.tar.textContent = L2;
    el.cur.textContent = "0";
    el.line.textContent = "第 1 关达成。你以为结束了吗？按钮可不这么想。";
    chime(); buzz(30);
    dodge();
  }

  function finish() {
    state.phase = "final";
    state.l2done = L2;
    var rec = { id: state.pid, sec: state.sec, taps: state.totalTaps };
    attempts.push(rec);
    renderBoard();
    var rank = rankOf(rec);
    el.fscore.textContent = state.pid + " 完成双关 · 共用时 " + fmt(state.sec)
      + " · 合计按了 " + state.totalTaps + " 下";
    el.frank.textContent = rank === 1 ? "🏆 你是本场手速之王（暂时）。"
      : "本场大神榜第 " + rank + " 名。前面的都不是人。";
    el.mock.textContent = "🎉 恭喜，你的人生因此浪费了 " + fmt(state.sec) + "。";
    el.final.classList.remove("hidden");
    fanfare(); buzz([20, 60, 20, 60, 30]);
  }

  // ---------- 大神榜 ----------
  function sorted() {
    var a = attempts.slice().sort(function (x, y) { return x.sec - y.sec; });
    return a.slice(0, 3);
  }
  function rankOf(rec) {
    var r = 1;
    attempts.forEach(function (x) { if (x.sec < rec.sec || (x.sec === rec.sec && x !== rec)) r++; });
    return r;
  }
  function renderBoard() {
    var top = sorted();
    var html = '<h3>🏆 大神榜（本场）</h3>';
    if (!top.length) html += "<p style='text-align:center;color:#6f76a8'>还没有人敢完成，等你留名。</p>";
    else {
      html += "<ol>";
      top.forEach(function (a) {
        html += "<li><b>" + a.id + "</b> · 用时 " + fmt(a.sec)
          + " · " + a.taps + " 下</li>";
      });
      html += "</ol>";
    }
    el.board.innerHTML = html;
  }

  // ---------- 点击 ----------
  function onPress() {
    if (state.phase !== "play") return;
    state.taps++;
    state.totalTaps++;
    el.cur.textContent = state.taps;
    tick();
    // 第 2 关每按一下按钮就逃一次
    if (state.lvl === 2) dodge();

    var t = state.lvl === 1 ? LINES1 : LINES2;
    if (MILE.indexOf(state.taps) >= 0 || (state.taps % 100 === 0 && state.lvl === 1)) {
      el.line.textContent = state.lvl === 1 ? pick(LINES1, state.taps) : pick(LINES2, state.taps);
      chime(); buzz(12);
    } else if (state.lvl === 2 && state.taps % 50 === 0) {
      el.line.textContent = pick(LINES2, state.taps);
    }

    if (state.lvl === 1 && state.taps >= L1) { levelUp(); return; }
    if (state.lvl === 2 && state.taps >= L2) { finish(); }
  }

  function startRun() {
    state.pid = (el.pid.value || "").trim() || "无名氏";
    state.phase = "play"; state.lvl = 1; state.taps = 0; state.totalTaps = 0;
    state.sec = 0; state.startedAt = Date.now();
    el.overlay.classList.add("hidden");
    el.final.classList.add("hidden");
    el.lvl.textContent = "第 1 关 · 人类迷惑行为";
    el.cur.textContent = "0"; el.tar.textContent = L1;
    el.line.textContent = "开始。记住：这不是为了世界和平。";
    centerBtn();
    renderClock();
  }

  // ---------- 主循环 ----------
  function loop(ts) {
    if (state.phase === "play") {
      if (state.lastTs) {
        var d = ts - state.lastTs;
        if (!document.hidden) state.sec += d / 1000;
      }
      state.lastTs = ts;
      renderClock();
    }
    requestAnimationFrame(loop);
  }

  // ---------- 绑定 ----------
  el.start.addEventListener("pointerdown", function (e) { e.preventDefault(); startRun(); });
  el.press.addEventListener("pointerdown", function (e) { e.preventDefault(); onPress(); });
  el.again.addEventListener("pointerdown", function (e) {
    e.preventDefault();
    el.final.classList.add("hidden");
    startRun();
  });
  el.snd.addEventListener("pointerdown", function (e) {
    e.preventDefault();
    state.sound = !state.sound;
    el.snd.textContent = state.sound ? "🔊" : "🔇";
  });
  window.addEventListener("resize", function () {
    if (state.lvl === 2 && state.phase === "play") dodge();
  });

  renderBoard();
  renderClock();
  requestAnimationFrame(loop);
})();
