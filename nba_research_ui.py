"""The Pickz NBA prop research page (docs/nba_props.html). Data: nba_props.json, written by nba_research.py.

iPhone only (the user, 2026-10-26). The layout follows the conventions of modern prop-research apps — a hit-rate
strip on every prop, a big results-vs-line bar chart with window tabs, an alt-line stepper, with/without filter
chips — in Pickz's own dark tokens (dashboard.py's --cu-*), with no third-party branding or assets. Vanilla JS, no
dependencies; the board server serves it next to index.html. JS_CORE holds the pure calculations;
test_nba_research runs it in node against the Python.
"""
from __future__ import annotations

import json

from nba_board import TEAM_ID

CSS = r"""
:root{color-scheme:dark;--bg:#000;--g1:#1c1c1e;--g2:#2c2c2e;--g3:#3a3a3c;--l1:#fff;--l2:rgba(235,235,245,.62);
--l3:rgba(235,235,245,.32);--sep:rgba(84,84,88,.6);--blue:#0a84ff;--grn:#30d158;--red:#ff453a;--org:#ff9f0a;--yel:#ffd60a;
--hit5:#30d158;--hit4:rgba(48,209,88,.55);--hit3:rgba(120,120,128,.36);--hit2:rgba(255,69,58,.5);--hit1:#ff453a;
--st:env(safe-area-inset-top);--sb:env(safe-area-inset-bottom)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--l1);font-family:-apple-system,"SF Pro Text",system-ui,sans-serif;
-webkit-text-size-adjust:100%;overscroll-behavior-y:none}
body.lock{overflow:hidden}
button,input,select{font:inherit;color:inherit}
button{cursor:pointer}
:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.sr{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.num{font-variant-numeric:tabular-nums}
/* ── top bar ── */
.top{padding:calc(var(--st) + 6px) 16px 0}
.bar{position:sticky;top:0;z-index:20;padding:calc(var(--st) + 6px) 16px 8px;background:rgba(0,0,0,.82);
-webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px)}
.bar.pin{padding-top:calc(var(--st) + 4px);margin-top:2px}
.bar.pin .chips:first-child{margin-top:0}
.bar-r{display:flex;align-items:center;justify-content:space-between;min-height:34px}
.bk{display:inline-flex;align-items:center;gap:2px;padding:6px 8px 6px 0;color:var(--blue);font-size:17px;text-decoration:none;
background:none;border:0}
.bk svg{width:12px;height:20px}
.upd{font-size:12px;color:var(--l3)}
h1{margin:2px 0 10px;font-size:34px;font-weight:800;letter-spacing:-.02em}
.srch{display:flex;align-items:center;gap:8px;height:38px;padding:0 10px;border-radius:11px;background:var(--g1)}
.srch svg{flex:none;width:16px;height:16px;color:var(--l3)}
.srch input{flex:1;min-width:0;height:100%;border:0;background:none;font-size:17px;outline:none}
.srch input::placeholder{color:var(--l3)}
.srch .clr{border:0;background:var(--g3);width:18px;height:18px;border-radius:50%;font-size:12px;line-height:18px;padding:0;
color:var(--bg)}
.seg{display:flex;padding:2px;border-radius:9px;background:var(--g1);margin-top:10px}
.seg button{flex:1;height:30px;border:0;border-radius:7px;background:none;font-size:13px;font-weight:600;color:var(--l1)}
.seg button[aria-pressed="true"]{background:var(--g3);box-shadow:0 3px 8px rgba(0,0,0,.25)}
.chips{display:flex;gap:8px;overflow-x:auto;margin:10px -16px 0;padding:0 16px;scrollbar-width:none;
-webkit-overflow-scrolling:touch}
.chips::-webkit-scrollbar{display:none}
.chip{flex:none;display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 14px;border-radius:17px;border:0;
background:var(--g1);color:var(--l1);font-size:14px;font-weight:600;white-space:nowrap}
.chip[aria-pressed="true"]{background:var(--l1);color:#000}
.chip img{width:20px;height:20px}
.chip .t{color:var(--l3);font-weight:500}
.chip[aria-pressed="true"] .t{color:rgba(0,0,0,.55)}
.chip .lv{color:var(--red);font-weight:800}
.tools{display:flex;align-items:center;gap:8px;margin-top:10px}
.tools .seg{margin:0;flex:0 0 150px}
.pill{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 12px;border-radius:17px;border:0;
background:var(--g1);font-size:14px;font-weight:600}
.pill b{display:inline-block;min-width:18px;height:18px;padding:0 5px;border-radius:9px;background:var(--blue);font-size:12px;
line-height:18px;text-align:center}
.pill svg{width:14px;height:14px}
.sp{flex:1}
/* ── list ── */
main{padding:6px 16px calc(var(--sb) + 30px)}
.hd{display:flex;justify-content:space-between;align-items:baseline;margin:14px 2px 8px;font-size:13px;font-weight:600;
color:var(--l2);text-transform:uppercase;letter-spacing:.03em}
.hd span{text-transform:none;letter-spacing:0;color:var(--l3)}
.pr{display:block;width:100%;margin:0 0 10px;padding:12px 12px 10px;border:0;border-radius:18px;background:var(--g1);
text-align:left;transition:transform .12s ease}
.pr:active{transform:scale(.985);background:#232325}
.pr-t{display:flex;align-items:center;gap:12px}
.av{position:relative;flex:none;width:52px;height:52px;border-radius:50%;background:var(--g2)}
.av .hs{width:52px;height:52px;border-radius:50%;object-fit:cover;object-position:50% 14%}
.av .lg{position:absolute;right:-4px;bottom:-3px;width:22px;height:22px;padding:2px;border-radius:50%;background:#000}
.who{flex:1;min-width:0}
.nm{font-size:17px;font-weight:700;letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sub{margin-top:2px;font-size:13px;color:var(--l2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ln{flex:none;text-align:right}
.ln .v{font-size:22px;font-weight:800;letter-spacing:-.02em;line-height:1.05}
.ln .v i{font-style:normal;font-size:13px;font-weight:700;color:var(--l2);margin-right:2px}
.ln .o{font-size:12px;font-weight:600;color:var(--l3)}
.hits{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:10px}
.hit{border-radius:9px;padding:5px 0 4px;text-align:center;background:var(--g2)}
.hit i{display:block;font-style:normal;font-size:10px;font-weight:700;letter-spacing:.04em;color:rgba(255,255,255,.7)}
.hit b{display:block;font-size:14px;font-weight:800}
.h5{background:var(--hit5);color:#000}.h5 i{color:rgba(0,0,0,.6)}
.h4{background:var(--hit4)} .h3{background:var(--hit3)} .h2{background:var(--hit2)}
.h1{background:var(--hit1)} .h0 b{color:var(--l3)}
.tg{display:inline-block;margin-left:6px;padding:2px 6px 1px;border-radius:5px;font-size:10px;font-weight:800;
letter-spacing:.04em;vertical-align:2px}
.tq{background:rgba(255,214,10,.18);color:var(--yel)} .to{background:rgba(255,69,58,.2);color:var(--red)}
.tp{background:rgba(48,209,88,.16);color:var(--grn)} .tl{background:var(--red);color:#fff}
.tf{background:rgba(255,159,10,.18);color:var(--org)} .tn{background:var(--g3);color:var(--l2)}
.empty{padding:56px 24px;text-align:center;color:var(--l2);font-size:15px;line-height:1.4}
.empty b{display:block;margin-bottom:6px;color:var(--l1);font-size:18px}
.empty button{margin-top:16px}
.btn{height:44px;padding:0 20px;border:0;border-radius:12px;background:var(--g2);font-size:16px;font-weight:600}
.btn.pri{background:var(--blue)}
.ban{margin:10px 16px 0;padding:10px 12px;border-radius:12px;background:rgba(255,159,10,.14);color:var(--org);font-size:13px;
font-weight:600}
.ban.err{background:rgba(255,69,58,.15);color:var(--red)}
.sk{height:118px;margin:0 0 10px;border-radius:18px;background:linear-gradient(90deg,var(--g1),#252527,var(--g1));
background-size:200% 100%;animation:sk 1.1s infinite}
@keyframes sk{to{background-position:-200% 0}}
@media (prefers-reduced-motion:reduce){.sk{animation:none}.pr{transition:none}}
/* ── bottom sheet ── */
.scrim{position:fixed;inset:0;z-index:40;background:rgba(0,0,0,.45);opacity:0;transition:opacity .2s}
.scrim.on{opacity:1}
.sheet{position:fixed;left:0;right:0;bottom:0;z-index:41;max-height:86vh;overflow-y:auto;padding:8px 16px calc(var(--sb) + 16px);
border-radius:14px 14px 0 0;background:var(--g1);transform:translateY(100%);transition:transform .28s cubic-bezier(.2,.9,.3,1)}
.sheet.on{transform:none}
.grab{width:36px;height:5px;margin:0 auto 10px;border-radius:3px;background:var(--g3)}
.sheet h2{margin:0 0 10px;font-size:20px;font-weight:700}
.opt{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:48px;padding:0 4px;border:0;
border-bottom:.5px solid var(--sep);background:none;font-size:17px;text-align:left}
.opt .ck{color:var(--blue);font-weight:700}
.fl{display:block;margin:12px 0 0}
.fl span{display:block;margin:0 0 6px 4px;font-size:13px;color:var(--l2)}
.fl select,.fl input{width:100%;height:44px;padding:0 12px;border:0;border-radius:10px;background:var(--g2);font-size:17px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sheet .acts{display:flex;gap:10px;margin-top:18px}
.sheet .acts .btn{flex:1}
/* ── player page ── */
.pg{position:fixed;inset:0;z-index:30;overflow-y:auto;background:var(--bg);transform:translateX(100%);
transition:transform .32s cubic-bezier(.2,.9,.3,1);-webkit-overflow-scrolling:touch}
.pg.on{transform:none}
@media (prefers-reduced-motion:reduce){.pg,.sheet{transition:none}}
.pg .bar{padding-bottom:6px}
.hero{display:flex;align-items:center;gap:14px;padding:4px 16px 0}
.hero .av{width:78px;height:78px}
.hero .av .hs{width:78px;height:78px}
.hero .av .lg{width:30px;height:30px}
.hero h2{margin:0;font-size:24px;font-weight:800;letter-spacing:-.02em;line-height:1.15}
.hero .sub{white-space:normal}
.box{margin:12px 16px 0;padding:14px;border-radius:18px;background:var(--g1)}
.box h3{margin:0 0 10px;font-size:13px;font-weight:600;color:var(--l2);text-transform:uppercase;letter-spacing:.03em}
.lc{display:flex;align-items:center;justify-content:space-between}
.lc .big{font-size:34px;font-weight:800;letter-spacing:-.02em}
.lc .big i{font-style:normal;font-size:16px;font-weight:700;color:var(--l2);margin-right:4px}
.stp{display:flex;gap:8px}
.stp button{width:44px;height:44px;border:0;border-radius:22px;background:var(--g2);font-size:24px;font-weight:500;line-height:1}
.bks{margin-top:12px;border-top:.5px solid var(--sep)}
.bkr{display:grid;grid-template-columns:28px 1fr auto auto;align-items:center;gap:10px;min-height:52px;
border-bottom:.5px solid var(--sep);font-size:15px}
.bkr:last-child{border-bottom:0}
.bkr img{width:28px;height:28px;border-radius:7px}
.bkr .ln2{color:var(--l2);font-size:12px}
.bkr .od{min-width:62px;padding:6px 0;border-radius:8px;background:var(--g2);text-align:center;font-weight:700}
.bkr .od.best{background:rgba(48,209,88,.18);color:var(--grn)}
.bkr .od.na{color:var(--l3);font-weight:500;font-size:12px}
.note{margin-top:8px;font-size:12px;line-height:1.35;color:var(--l3)}
.wins{display:flex;gap:8px;overflow-x:auto;margin:14px 0 0;padding:0 16px;scrollbar-width:none}
.wins::-webkit-scrollbar{display:none}
.win{flex:none;min-width:64px;padding:7px 10px 6px;border:0;border-radius:12px;background:var(--g1);text-align:center}
.win i{display:block;font-style:normal;font-size:11px;font-weight:600;color:var(--l2)}
.win b{display:block;font-size:16px;font-weight:800}
.win[aria-pressed="true"]{background:var(--l1);color:#000}
.win[aria-pressed="true"] i{color:rgba(0,0,0,.6)}
.win:disabled{opacity:.35}
.sum{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:8px}
.sum .r{font-size:28px;font-weight:800;letter-spacing:-.02em}
.sum .r small{font-size:14px;font-weight:600;color:var(--l2);margin-left:4px}
.sum .a{text-align:right;font-size:13px;color:var(--l2);line-height:1.5}
.sum .a b{color:var(--l1)}
.chw{overflow-x:auto;margin:0 -14px;padding:0 14px;scrollbar-width:none}
.chw::-webkit-scrollbar{display:none}
svg.ch{display:block}
svg.ch text{fill:var(--l3);font-size:10px;font-weight:600}
svg.ch .vl{fill:var(--l1);font-size:12px;font-weight:800}
svg.ch .ll{fill:#000;font-size:11px;font-weight:800}
svg.ch g.br:focus{outline:none} svg.ch g.br:focus rect{stroke:var(--blue);stroke-width:2}
.fch{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.fch .chip{height:32px;font-size:13px;background:var(--g2)}
.fch .chip[aria-pressed="true"]{background:var(--blue);color:#fff}
.kv{display:flex;justify-content:space-between;align-items:center;gap:12px;min-height:44px;border-bottom:.5px solid var(--sep);
font-size:15px}
.kv:last-child{border-bottom:0}
.kv span{color:var(--l2)}
.kv b{text-align:right;font-weight:600}
.rk{display:inline-block;min-width:34px;margin-left:8px;padding:3px 6px;border-radius:7px;font-size:12px;font-weight:800;text-align:center}
.rk.g{background:rgba(48,209,88,.18);color:var(--grn)} .rk.r{background:rgba(255,69,58,.18);color:var(--red)}
.rk.n{background:var(--g2);color:var(--l2)}
.rel{display:flex;gap:10px;overflow-x:auto;margin:0 -14px;padding:0 14px;scrollbar-width:none}
.rel::-webkit-scrollbar{display:none}
.rc{flex:none;width:150px;padding:10px;border:0;border-radius:14px;background:var(--g2);text-align:left}
.rc .nm{font-size:14px}
.rc .sub{font-size:12px}
.rc .rr{margin-top:6px;font-size:12px;font-weight:700;color:var(--l2)}
details.log summary{display:flex;justify-content:space-between;align-items:center;min-height:30px;list-style:none;
font-size:13px;font-weight:600;color:var(--l2);text-transform:uppercase;letter-spacing:.03em}
details.log summary::-webkit-details-marker{display:none}
details.log summary:after{content:"Show";text-transform:none;letter-spacing:0;color:var(--blue);font-weight:500;font-size:15px}
details.log[open] summary:after{content:"Hide"}
table{width:100%;margin-top:8px;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
th{padding:6px 4px;border-bottom:.5px solid var(--sep);font-size:11px;font-weight:600;color:var(--l3);text-align:left}
td{padding:9px 4px;border-bottom:.5px solid var(--sep)}
th.r,td.r{text-align:right}
.ov{color:var(--grn);font-weight:800} .un{color:var(--red);font-weight:800} .pu{color:var(--l2);font-weight:800}
.live{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:700}
.end{height:calc(var(--sb) + 30px)}
"""

JS_CORE = r"""
var MARKET_PARTS = {points:["pts"], rebounds:["reb"], assists:["ast"], threes:["fg3m"], pra:["pts","reb","ast"],
  pts_reb:["pts","reb"], pts_ast:["pts","ast"], reb_ast:["reb","ast"]};
function statValue(log, market) {
  var parts = MARKET_PARTS[market], s = 0;
  for (var i = 0; i < parts.length; i++) {
    var v = log[parts[i]];
    if (v === null || v === undefined) return null;
    s += Number(v);
  }
  return s;
}
function hitSummary(values, line) {
  var vals = values.filter(function (v) { return v !== null && v !== undefined; });
  if (!vals.length) return {n: 0, over: 0, under: 0, push: 0, avg: null, med: null};
  var over = 0, under = 0, sum = 0;
  vals.forEach(function (v) { if (v > line) over++; else if (v < line) under++; sum += v; });
  var s = vals.slice().sort(function (a, b) { return a - b; }), m = s.length >> 1;
  var med = s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  return {n: vals.length, over: over, under: under, push: vals.length - over - under,
          avg: Math.round(sum / vals.length * 100) / 100, med: med};
}
function seasonOf(date) {
  var y = +date.slice(0, 4), mo = +date.slice(5, 7);
  if (mo < 8) y -= 1;
  return y + "-" + String(y + 1).slice(2);
}
function rowsToLogs(cols, rows) {
  return rows.map(function (r) { var o = {}; cols.forEach(function (c, i) { o[c] = r[i]; }); return o; });
}
function windowed(logs, win, season, opp) {
  if (win === "l5") return logs.slice(-5);
  if (win === "l10") return logs.slice(-10);
  if (win === "l20") return logs.slice(-20);
  if (win === "h2h") return logs.filter(function (l) { return l.opp === opp; });
  if (win === "season") return logs.filter(function (l) { return seasonOf(l.date) === season; });
  if (win === "last") return logs.filter(function (l) { return seasonOf(l.date) !== season; });
  return logs.slice();
}
// chip filters on the player page: home / starter = true, false or null (any); without = [{played, since, team}]
function filterLogs(logs, f) {
  f = f || {};
  return logs.filter(function (l) {
    if (f.home === true && l.home !== 1) return false;
    if (f.home === false && l.home !== 0) return false;
    if (f.starter === true && l.starter !== 1) return false;
    if (f.starter === false && l.starter !== 0) return false;
    for (var i = 0; i < (f.without || []).length; i++) {
      var w = f.without[i];
      if (l.team !== w.team || l.date < w.since || w.played.indexOf(l.gid) >= 0) return false;
    }
    return true;
  });
}
function splitRows(logs, market, line, opts) {
  var out = [];
  function add(label, sub) { out.push({label: label, s: hitSummary(sub.map(function (l) { return statValue(l, market); }), line)}); }
  add("Home", logs.filter(function (l) { return l.home === 1; }));
  add("Away", logs.filter(function (l) { return l.home === 0; }));
  if (opts && opts.opp) add("vs " + opts.opp, logs.filter(function (l) { return l.opp === opts.opp; }));
  add("Started", logs.filter(function (l) { return l.starter === 1; }));
  add("Bench", logs.filter(function (l) { return l.starter === 0; }));
  ((opts && opts.without) || []).forEach(function (w) { add("Without " + w.name, filterLogs(logs, {without: [w]})); });
  return out;
}
// the hit rate of a side ("over" / "under") at a line: a fraction, or null with no games
function sideRate(s, side) { return s.n ? (side === "under" ? s.under : s.over) / s.n : null; }
function american(dec) {
  if (!dec || dec <= 1) return "—";
  return dec >= 2 ? "+" + Math.round((dec - 1) * 100) : "-" + Math.round(100 / (dec - 1));
}
function decimalOf(am) {
  am = Number(am);
  if (!am || isNaN(am)) return null;
  return am > 0 ? 1 + am / 100 : 1 + 100 / Math.abs(am);
}
function rungAt(bookq, line) {
  if (!bookq) return null;
  for (var i = 0; i < bookq.rungs.length; i++) if (bookq.rungs[i][0] === line) return bookq.rungs[i];
  return null;
}
function bestPrice(prop, line, book, side) {
  var best = null, k = side === "under" ? 2 : 1;
  ["fd", "dk"].forEach(function (b) {
    if (book && book !== "all" && b !== book) return;
    var r = rungAt(prop.books[b], line);
    if (r && r[k] && (!best || r[k] > best.odds)) best = {book: b, odds: r[k]};
  });
  return best;
}
function bestOver(prop, line, book) { return bestPrice(prop, line, book, "over"); }
function propRates(prop, logs, side, season) {
  var out = {};
  if (prop.main === null || prop.main === undefined) return out;
  ["l5", "l10", "l20", "h2h", "season"].forEach(function (w) {
    var s = hitSummary(windowed(logs, w, season, prop.opp).map(function (l) { return statValue(l, prop.market); }), prop.main);
    out[w] = {n: s.n, rate: sideRate(s, side), avg: s.avg};
  });
  return out;
}
function l10(prop, logsOf) {
  if (prop.main === null || prop.main === undefined) return null;
  return hitSummary(logsOf(prop).slice(-10).map(function (l) { return statValue(l, prop.market); }), prop.main);
}
function filterProps(props, st, gameOf, logsOf) {
  var q = (st.q || "").trim().toLowerCase();
  return props.filter(function (p) {
    var g = gameOf(p.gid);
    if (!g || g.date !== st.date) return false;
    if (st.gid && st.gid !== "all" && p.gid !== st.gid) return false;
    if (st.team && st.team !== "all" && p.team !== st.team) return false;
    if (st.market && st.market !== "all" && p.market !== st.market) return false;
    if (st.book && st.book !== "all" && !p.books[st.book]) return false;
    if (q && p.player.toLowerCase().indexOf(q) < 0 && (p.team || "").toLowerCase() !== q) return false;
    var line = p.main;
    if (st.lmin !== "" && st.lmin !== undefined && st.lmin !== null && (line === null || line < +st.lmin)) return false;
    if (st.lmax !== "" && st.lmax !== undefined && st.lmax !== null && (line === null || line > +st.lmax)) return false;
    if ((st.omin !== "" && st.omin != null) || (st.omax !== "" && st.omax != null)) {
      var b = line === null ? null : bestPrice(p, line, st.book, st.side);
      if (!b) return false;
      var am = b.odds >= 2 ? (b.odds - 1) * 100 : -100 / (b.odds - 1);
      if (st.omin !== "" && st.omin != null && am < +st.omin) return false;
      if (st.omax !== "" && st.omax != null && am > +st.omax) return false;
    }
    return true;
  });
}
// keys: hit5 / hit10 / hit20 / h2h / szn (the side's hit rate), avgdiff (L10 average minus the line, signed by side),
// line, odds (the side's best price), player; avg10 kept for old links
function sortProps(list, key, dir, logsOf, side, season) {
  var sgn = dir === "asc" ? 1 : -1;
  side = side || "over";
  var W = {hit5: "l5", hit10: "l10", hit20: "l20", h2h: "h2h", szn: "season"};
  function val(p) {
    if (key === "player") return p.player.toLowerCase();
    if (key === "line") return p.main;
    if (key === "odds") { var b = p.main === null ? null : bestPrice(p, p.main, "all", side); return b ? b.odds : null; }
    if (W[key]) { var r = propRates(p, logsOf(p), side, season)[W[key]]; return r && r.rate !== null ? r.rate : null; }
    var s = l10(p, logsOf);
    if (!s || !s.n) return null;
    if (key === "avg10") return s.avg;
    if (key === "avgdiff") return (side === "under" ? -1 : 1) * (s.avg - p.main);
    return null;
  }
  return list.map(function (p, i) { return {p: p, v: val(p), i: i}; }).sort(function (a, b) {
    if (a.v === null && b.v === null) return a.i - b.i;          // stable; missing values always last
    if (a.v === null) return 1;
    if (b.v === null) return -1;
    if (a.v < b.v) return -sgn;
    if (a.v > b.v) return sgn;
    return a.i - b.i;
  }).map(function (x) { return x.p; });
}
if (typeof module !== "undefined") module.exports = {statValue: statValue, hitSummary: hitSummary, seasonOf: seasonOf,
  rowsToLogs: rowsToLogs, windowed: windowed, filterLogs: filterLogs, splitRows: splitRows, sideRate: sideRate,
  american: american, decimalOf: decimalOf, bestOver: bestOver, bestPrice: bestPrice, propRates: propRates,
  filterProps: filterProps, sortProps: sortProps};
"""

JS_APP = r"""
(function () {
const TEAM_ID = __TEAM_ID__;
const ORDER = ["points", "rebounds", "assists", "threes", "pra", "pts_reb", "pts_ast", "reb_ast"];
const NAME = {points: "Points", rebounds: "Rebounds", assists: "Assists", threes: "3-Pointers", pra: "Pts+Reb+Ast",
              pts_reb: "Pts+Reb", pts_ast: "Pts+Ast", reb_ast: "Reb+Ast"};
const SORTS = [["hit10", "L10 hit rate"], ["hit5", "L5 hit rate"], ["hit20", "L20 hit rate"], ["h2h", "Head-to-head hit rate"],
               ["szn", "Season hit rate"], ["avgdiff", "L10 average vs line"], ["line", "Line"], ["odds", "Best price"],
               ["player", "Player name"]];
let D = null, ERR = null, LOADING = true, CUR = null;
const ST = {date: null, gid: "all", market: "points", side: "over", q: "", sort: "hit10", dir: "desc", team: "all",
            book: "all", lmin: "", lmax: "", omin: "", omax: ""};
const DT = {line: null, win: "l10", home: null, starter: null, without: {}};
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const iso = s => new Date(/Z|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");
const mt = (s, day) => s ? iso(s).toLocaleString("en-US", Object.assign({timeZone: "America/Denver", hour: "numeric", minute: "2-digit"}, day ? {weekday: "short"} : {})) : "—";
const ago = s => { if (!s) return "never"; const m = (Date.now() - iso(s).getTime()) / 60000; return m < 1 ? "just now" : m < 60 ? Math.round(m) + "m ago" : Math.round(m / 60) + "h ago"; };
const logo = (t, c) => TEAM_ID[t] ? `<img class="${c || "lg"}" alt="" src="https://cdn.nba.com/logos/nba/${TEAM_ID[t]}/global/D/logo.svg">` : "";
const head = pid => `<img class="hs" alt="" loading="lazy" src="https://cdn.nba.com/headshots/nba/latest/260x190/${pid}.png" onerror="this.style.visibility='hidden'">`;
const short = m => (D.markets || {})[m] || m;
const gameOf = gid => D.games.find(g => g.gid === gid);
const pct = r => r === null || r === undefined ? "–" : Math.round(r * 100) + "%";
const hcls = (r, n) => r === null || r === undefined || !n ? "h0" : r >= .7 ? "h5" : r >= .6 ? "h4" : r > .4 ? "h3" : r > .3 ? "h2" : "h1";
const ord = n => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");
const CHEV = '<svg viewBox="0 0 12 20" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2 2 10l8 8"/></svg>';
function logsOf(p) {
  const pl = D.players[String(p.pid)];
  if (!pl) return [];
  if (!pl._logs) pl._logs = rowsToLogs(D.log_cols, pl.logs);
  return pl._logs;
}
function hashState() {
  const h = new URLSearchParams();
  Object.keys(ST).forEach(k => { if (ST[k] !== "" && ST[k] !== null && ST[k] !== "all") h.set(k, ST[k]); });
  if (CUR) h.set("p", CUR);
  return "#" + h.toString();
}
function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  Object.keys(ST).forEach(k => { if (h.has(k)) ST[k] = h.get(k); });
  return h.get("p");
}
const save = () => history.replaceState(history.state, "", hashState());
function injTag(p) {
  const g = gameOf(p.gid), inj = D.injuries[g.date + "|" + p.pid];
  if (!inj || !inj.official) return "";
  const s = inj.official.status, c = s === "Out" || s === "Doubtful" ? "to" : s === "Questionable" ? "tq" : "tp";
  return `<span class="tg ${c}">${esc(s === "Questionable" ? "Q" : s === "Doubtful" ? "DOUBT" : s.toUpperCase())}</span>`;
}
function when(g) {
  if (g.state === "live") return '<span class="tg tl">LIVE</span> ' + esc(g.label || "");
  if (g.state === "final") return "Final";
  if (g.state === "postponed") return '<span class="tg to">PPD</span>';
  return mt(g.tip);
}
const vs = p => p.team ? (p.home ? "vs " : "@ ") + p.opp : "";
// ── list ──
function availMarkets() {
  const m = {};
  D.props.forEach(p => { const g = gameOf(p.gid); if (g && g.date === ST.date) m[p.market] = 1; });
  return ORDER.filter(k => m[k]);
}
function filtersOn() { return ["team", "book"].filter(k => ST[k] !== "all").length + ["lmin", "lmax", "omin", "omax"].filter(k => ST[k] !== "").length; }
function header() {
  const days = D.dates.map((d, i) => {
    const n = D.games.filter(g => g.date === d).length;
    const lab = i === 0 ? "Today" : i === 1 ? "Tomorrow" : d;
    return `<button data-date="${d}" aria-pressed="${d === ST.date}">${lab} · ${n}</button>`;
  }).join("");
  const mk = availMarkets().map(m => `<button class="chip" data-market="${m}" aria-pressed="${m === ST.market}">${esc(NAME[m])}</button>`).join("");
  const games = D.games.filter(g => g.date === ST.date).map(g =>
    `<button class="chip" data-gid="${g.gid}" aria-pressed="${g.gid === ST.gid}">${logo(g.away, "")}${esc(g.away)} @ ${esc(g.home)}${logo(g.home, "")} <span class="t">${g.state === "live" ? '<span class="lv">LIVE</span>' : g.state === "final" ? "Final" : g.state === "postponed" ? "PPD" : mt(g.tip)}</span></button>`).join("");
  const fo = filtersOn();
  return `<div class="top"><div class="bar-r"><a class="bk" href="index.html">${CHEV}Pickz</a><span class="upd" id="upd">Updated ${ago(D.generated_at)}</span></div>
    <h1>NBA Props</h1>
    <label class="srch"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="7" cy="7" r="5"/><path d="m11 11 3.5 3.5" stroke-linecap="round"/></svg>
      <span class="sr">Search players</span><input id="q" type="search" placeholder="Search players or team" autocomplete="off" autocorrect="off" value="${esc(ST.q)}">
      ${ST.q ? '<button class="clr" id="qx" aria-label="Clear search">×</button>' : ""}</label>
    <div class="seg" role="group" aria-label="Day">${days}</div>
    <nav class="chips" aria-label="Games"><button class="chip" data-gid="all" aria-pressed="${ST.gid === "all"}">All games</button>${games}</nav></div>
    <div class="bar pin"><nav class="chips" aria-label="Markets">${mk}</nav>
    <div class="tools"><div class="seg" role="group" aria-label="Side"><button data-side="over" aria-pressed="${ST.side === "over"}">Over</button><button data-side="under" aria-pressed="${ST.side === "under"}">Under</button></div>
      <span class="sp"></span>
      <button class="pill" id="sortb" aria-haspopup="dialog"><svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 2v10M1.5 9.5 4 12l2.5-2.5M10 12V2M7.5 4.5 10 2l2.5 2.5"/></svg>${esc((SORTS.find(s => s[0] === ST.sort) || SORTS[0])[1].replace(" hit rate", ""))}</button>
      <button class="pill" id="filtb" aria-haspopup="dialog">Filters${fo ? `<b>${fo}</b>` : ""}</button></div></div>`;
}
function row(p) {
  const g = gameOf(p.gid), logs = logsOf(p), r = propRates(p, logs, ST.side, D.season);
  const best = p.main === null ? null : bestPrice(p, p.main, ST.book, ST.side);
  const cells = [["L5", "l5"], ["L10", "l10"], ["L20", "l20"], ["H2H", "h2h"], ["SZN", "season"]].map(([lab, k]) => {
    const x = r[k] || {n: 0, rate: null};
    return `<div class="hit ${hcls(x.rate, x.n)}"><i>${lab}</i><b>${pct(x.rate)}</b></div>`;
  }).join("");
  const live = p.live && g.state !== "pregame" ? `<span class="tg ${g.state === "live" ? "tl" : "tn"}">${g.state === "live" ? "LIVE" : "FINAL"} ${p.live.value}</span>` : "";
  const flag = p.flag && p.flag.card === 1 ? '<span class="tg tf">ENGINE</span>' : "";
  return `<button class="pr" data-id="${esc(p.id)}"><div class="pr-t"><div class="av">${head(p.pid)}${logo(p.team)}</div>
    <div class="who"><div class="nm">${esc(p.player)}${injTag(p)}${live}${flag}</div><div class="sub">${esc(vs(p))} · ${when(g)}</div></div>
    <div class="ln"><div class="v num"><i>${ST.side === "under" ? "U" : "O"}</i>${p.main === null ? "—" : p.main}</div><div class="o num">${best ? american(best.odds) + " " + best.book.toUpperCase() : p.main === null ? "alt only" : "—"}</div></div></div>
    <div class="hits num" aria-label="Hit rates">${cells}</div></button>`;
}
function banners() {
  const out = [], b = D.sources.books;
  [["fd", "FanDuel"], ["dk", "DraftKings"]].forEach(([k, n]) => {
    if (b[k] && b[k].stale) out.push(`${n} prices are ${Math.round(b[k].age_min)} min old.`);
  });
  if ((Date.now() - iso(D.generated_at).getTime()) / 60000 > 10) out.push("This page hasn't refreshed for a while — the prop feed may be down.");
  return out.map(t => `<div class="ban" role="status">${esc(t)}</div>`).join("");
}
function render() {
  const app = $("#app");
  if (!D) {
    app.innerHTML = LOADING ? '<div class="top"><div class="bar-r"><a class="bk" href="index.html">' + CHEV + 'Pickz</a></div><h1>NBA Props</h1></div><main aria-busy="true">' + '<div class="sk"></div>'.repeat(6) + "</main>"
      : '<div class="top"><div class="bar-r"><a class="bk" href="index.html">' + CHEV + 'Pickz</a></div><h1>NBA Props</h1></div><div class="empty" role="alert"><b>Couldn\'t load props</b>' + esc(ERR) + '<br><button class="btn pri" id="retry">Try again</button></div>';
    const r = $("#retry"); if (r) r.onclick = load;
    return;
  }
  if (!ST.date || D.dates.indexOf(ST.date) < 0) ST.date = D.dates.find(d => D.props.some(p => (gameOf(p.gid) || {}).date === d)) || D.dates[0];
  const mks = availMarkets();
  if (mks.length && mks.indexOf(ST.market) < 0) ST.market = mks[0];
  const onDate = D.props.filter(p => (gameOf(p.gid) || {}).date === ST.date);
  const list = sortProps(filterProps(D.props, ST, gameOf, logsOf), ST.sort, ST.dir, logsOf, ST.side, D.season);
  let body;
  if (!D.games.some(g => g.date === ST.date)) body = '<div class="empty"><b>No games</b>There are no NBA games on this day.</div>';
  else if (!onDate.length) body = '<div class="empty"><b>No props yet</b>The books usually post player props on game day.</div>';
  else if (ST.gid !== "all" && !onDate.some(p => p.gid === ST.gid)) body = '<div class="empty"><b>No props for this game yet</b>Check back closer to tip.</div>';
  else if (!list.length) body = '<div class="empty"><b>No matches</b>Nothing fits these filters.<br><button class="btn" id="reset2">Reset filters</button></div>';
  else body = `<div class="hd"><span>${esc(NAME[ST.market] || "")}</span><span>${list.length} props · ${ST.side} hit rate at the main line</span></div>` + list.map(row).join("");
  app.innerHTML = header() + banners() + `<main>${body}</main>`;
  bindList();
}
function bindList() {
  $$("[data-date]").forEach(b => b.onclick = () => { ST.date = b.dataset.date; ST.gid = "all"; save(); render(); });
  $$("[data-market]").forEach(b => b.onclick = () => { ST.market = b.dataset.market; save(); render(); });
  $$("[data-gid]").forEach(b => b.onclick = () => { ST.gid = b.dataset.gid; save(); render(); });
  $$("[data-side]").forEach(b => b.onclick = () => { ST.side = b.dataset.side; save(); render(); });
  const q = $("#q");
  if (q) q.oninput = () => { ST.q = q.value; save(); const at = q.selectionStart; render(); const n = $("#q"); n.focus(); n.setSelectionRange(at, at); };
  const qx = $("#qx"); if (qx) qx.onclick = e => { e.preventDefault(); ST.q = ""; save(); render(); };
  $("#sortb").onclick = sortSheet;
  $("#filtb").onclick = filterSheet;
  const r2 = $("#reset2"); if (r2) r2.onclick = resetFilters;
  $$(".pr").forEach(b => b.onclick = () => openProp(b.dataset.id));
}
function resetFilters() { Object.assign(ST, {team: "all", book: "all", lmin: "", lmax: "", omin: "", omax: "", q: "", gid: "all"}); save(); render(); }
// ── sheets ──
let SHEET_FOCUS = null;
function openSheet(html, bind) {
  SHEET_FOCUS = document.activeElement;
  const s = $("#sheet"), sc = $("#scrim");
  s.innerHTML = '<div class="grab"></div>' + html;
  s.hidden = sc.hidden = false;
  requestAnimationFrame(() => { s.classList.add("on"); sc.classList.add("on"); });
  bind(s);
  const f = s.querySelector("button, select, input"); if (f) f.focus();
}
function closeSheet() {
  const s = $("#sheet"), sc = $("#scrim");
  s.classList.remove("on"); sc.classList.remove("on");
  setTimeout(() => { s.hidden = sc.hidden = true; s.innerHTML = ""; }, 280);
  if (SHEET_FOCUS && document.body.contains(SHEET_FOCUS)) SHEET_FOCUS.focus();
}
function sortSheet() {
  openSheet('<h2 id="sht">Sort by</h2>' + SORTS.map(([k, lab]) => `<button class="opt" data-sort="${k}">${lab}<span class="ck">${k === ST.sort ? (ST.dir === "desc" ? "↓" : "↑") : ""}</span></button>`).join("") +
    '<div class="note">Tap the selected option again to flip the order. Hit rates are for the chosen side (Over / Under) at each prop\'s main line.</div>', s => {
    $$("[data-sort]", s).forEach(b => b.onclick = () => {
      const k = b.dataset.sort;
      if (k === ST.sort) ST.dir = ST.dir === "desc" ? "asc" : "desc";
      else { ST.sort = k; ST.dir = k === "player" || k === "line" ? "asc" : "desc"; }
      save(); render(); closeSheet();
    });
  });
}
function filterSheet() {
  const teams = {};
  D.props.forEach(p => { if ((gameOf(p.gid) || {}).date === ST.date && p.team) teams[p.team] = 1; });
  const opt = (v, lab, cur) => `<option value="${v}"${v === cur ? " selected" : ""}>${esc(lab)}</option>`;
  openSheet(`<h2 id="sht">Filters</h2>
    <label class="fl"><span>Team</span><select id="f-team">${opt("all", "All teams", ST.team)}${Object.keys(teams).sort().map(t => opt(t, t, ST.team)).join("")}</select></label>
    <label class="fl"><span>Sportsbook</span><select id="f-book">${opt("all", "FanDuel and DraftKings", ST.book)}${opt("fd", "FanDuel", ST.book)}${opt("dk", "DraftKings", ST.book)}</select></label>
    <div class="two"><label class="fl"><span>Line from</span><input id="f-lmin" type="number" inputmode="decimal" step="0.5" value="${esc(ST.lmin)}"></label>
    <label class="fl"><span>Line to</span><input id="f-lmax" type="number" inputmode="decimal" step="0.5" value="${esc(ST.lmax)}"></label></div>
    <div class="two"><label class="fl"><span>Odds from</span><input id="f-omin" type="number" inputmode="numeric" placeholder="-200" value="${esc(ST.omin)}"></label>
    <label class="fl"><span>Odds to</span><input id="f-omax" type="number" inputmode="numeric" placeholder="+150" value="${esc(ST.omax)}"></label></div>
    <div class="note">Odds are the best ${ST.side} price at the main line, in US odds.</div>
    <div class="acts"><button class="btn" id="f-reset">Reset</button><button class="btn pri" id="f-ok">Show props</button></div>`, s => {
    $("#f-ok", s).onclick = () => {
      ST.team = $("#f-team", s).value; ST.book = $("#f-book", s).value;
      ["lmin", "lmax", "omin", "omax"].forEach(k => ST[k] = $("#f-" + k, s).value);
      save(); render(); closeSheet();
    };
    $("#f-reset", s).onclick = () => { closeSheet(); resetFilters(); };
  });
}
// ── player page ──
function allLines(p) {
  const s = {};
  ["fd", "dk"].forEach(b => { if (p.books[b]) p.books[b].rungs.forEach(r => s[r[0]] = 1); });
  return Object.keys(s).map(Number).sort((a, b) => a - b);
}
function openProp(id, push) {
  const p = D.props.find(x => x.id === id);
  if (!p) return;
  const fresh = CUR !== id;
  CUR = id;
  if (fresh) Object.assign(DT, {line: p.main !== null ? p.main : allLines(p)[0], win: "l10", home: null, starter: null, without: {}});
  if (push !== false) history.pushState({p: id}, "", hashState());
  renderProp();
  const pg = $("#pg");
  pg.hidden = false;
  document.body.classList.add("lock");
  requestAnimationFrame(() => pg.classList.add("on"));
  if (fresh) pg.scrollTop = 0;
  setTimeout(() => { const b = $("#pg .bk"); if (b) b.focus({preventScroll: true}); }, 50);
}
function closeProp() {
  const pg = $("#pg");
  pg.classList.remove("on");
  document.body.classList.remove("lock");
  setTimeout(() => { if (!pg.classList.contains("on")) pg.hidden = true; }, 330);
  const id = CUR; CUR = null;
  const b = id && document.querySelector(`.pr[data-id="${CSS.escape(id)}"]`); if (b) b.focus({preventScroll: true});
}
function chart(logs, market, line) {
  const n = logs.length;
  if (!n) return '<div class="empty" style="padding:30px 0"><b>No games</b>Nothing matches this window and these filters.</div>';
  const vals = logs.map(l => statValue(l, market));
  const vmax = Math.max(line * 1.3, Math.max(...vals.filter(v => v !== null), 1));
  const avail = Math.max(250, Math.min(window.innerWidth, 500) - 110);   // the card's inner width less the label room
  const bw = Math.max(22, Math.min(44, avail / n)), gap = Math.round(bw * .22);
  const W = Math.max(avail, n * bw + 4) + 50, H = 230, top = 22, bot = 182;   // + room for the line label
  const y = v => bot - v / vmax * (bot - top);
  const out = [`<svg class="ch" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(NAME[market])} by game, ${n} games, line ${line}">`,
    '<defs><pattern id="hz" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="#ff453a"/><line x1="0" y1="0" x2="0" y2="6" stroke="#b32a22" stroke-width="3"/></pattern></defs>'];
  logs.forEach((l, i) => {
    const v = vals[i], x = 2 + i * bw, w = bw - gap, res = v === null ? "none" : v > line ? "over" : v < line ? "under" : "push";
    const h = v === null ? 0 : Math.max(3, bot - y(v));
    const fill = res === "over" ? "#30d158" : res === "under" ? "url(#hz)" : "#636366";
    const d = iso(l.date + "T12:00:00Z").toLocaleDateString("en-US", {month: "numeric", day: "numeric", timeZone: "UTC"});
    const desc = `${d} ${l.home ? "vs" : "at"} ${l.opp}: ${v === null ? "no value" : v} ${short(market)}, ${res} ${line}, ${l.min} min`;
    out.push(`<g class="br" tabindex="0" role="img" aria-label="${esc(desc)}"><title>${esc(desc)}</title>` +
      `<rect x="${x}" y="${bot - h}" width="${w}" height="${h}" rx="5" fill="${fill}"/>` +
      (v !== null ? `<text class="vl" x="${x + w / 2}" y="${bot - h - 5}" text-anchor="middle">${v}</text>` : "") +
      `<text x="${x + w / 2}" y="${bot + 15}" text-anchor="middle">${esc(l.opp)}</text><text x="${x + w / 2}" y="${bot + 28}" text-anchor="middle">${d}</text></g>`);
  });
  const ly = y(line);
  out.push(`<line x1="0" x2="${W}" y1="${ly}" y2="${ly}" stroke="#fff" stroke-width="1.5" stroke-dasharray="6 5" opacity=".9"/>`);
  out.push(`<rect x="${W - 46}" y="${ly - 9}" width="44" height="18" rx="9" fill="#fff"/><text class="ll" x="${W - 24}" y="${ly + 4}" text-anchor="middle">${line}</text></svg>`);
  return out.join("");
}
function renderProp() {
  const p = D.props.find(x => x.id === CUR), pg = $("#pg");
  if (!p) { pg.innerHTML = `<div class="bar"><div class="bar-r"><button class="bk">${CHEV}Props</button></div></div><div class="empty"><b>No longer posted</b>The books have taken this prop down.</div>`; $("#pg .bk").onclick = () => history.back(); return; }
  const g = gameOf(p.gid), line = DT.line, side = ST.side, logs = logsOf(p);
  const without = (D.absences[g.date + "|" + p.team] || []).map(a => ({key: String(a.pid), name: a.name || "teammate", played: a.played, since: a.since, team: p.team, status: a.status}));
  const f = {home: DT.home, starter: DT.starter, without: without.filter(w => DT.without[w.key])};
  const base = filterLogs(logs, f);
  const wins = [["l5", "L5"], ["l10", "L10"], ["l20", "L20"], ["h2h", "H2H"], ["season", D.season], ["last", "Last szn"]];
  const winHtml = wins.map(([k, lab]) => {
    const w = windowed(base, k, D.season, p.opp), s = hitSummary(w.map(l => statValue(l, p.market)), line);
    return `<button class="win" data-win="${k}" aria-pressed="${k === DT.win}"${w.length ? "" : " disabled"}><i>${esc(lab)}</i><b>${pct(sideRate(s, side))}</b></button>`;
  }).join("");
  const win = windowed(base, DT.win, D.season, p.opp);
  const s = hitSummary(win.map(l => statValue(l, p.market)), line);
  const hits = side === "under" ? s.under : s.over;
  const mkts = ORDER.filter(m => D.props.some(x => x.gid === p.gid && x.pid === p.pid && x.market === m));
  const inj = D.injuries[g.date + "|" + p.pid] || {};
  // books
  const bestNow = bestPrice(p, line, "all", side);
  const bk = [["fd", "FanDuel", "book-fd.png"], ["dk", "DraftKings", "book-dk.png"]].map(([b, name, img]) => {
    const q = p.books[b];
    if (!q) return `<div class="bkr"><img src="${img}" alt=""><span>${name}</span><span class="od na" style="grid-column:span 2">no prop posted</span></div>`;
    const r = rungAt(q, line);
    const ov = r && r[1] ? `<span class="od${bestNow && bestNow.book === b && side === "over" ? " best" : ""}">O ${american(r[1])}</span>` : '<span class="od na">—</span>';
    const un = r && r[2] ? `<span class="od${bestNow && bestNow.book === b && side === "under" ? " best" : ""}">U ${american(r[2])}</span>` : '<span class="od na">—</span>';
    const other = !r ? `<span class="od na" style="grid-column:span 2">not at ${line} · main ${q.main === null ? "—" : q.main}</span>` : ov + un;
    return `<div class="bkr"><img src="${img}" alt=""><span>${name}${D.sources.books[b] && D.sources.books[b].stale ? ' <span class="tg tq">STALE</span>' : ""}<br><span class="ln2">${q.main === line ? "main line" : r ? "alt line" : "other line"} · ${mt(q.updated)}</span></span>${other}</div>`;
  }).join("");
  const opened = p.open ? `<div class="note">FanDuel opened ${p.open[0]} (${american(p.open[1])}) ${mt(p.open[2], true)}.</div>` : "";
  // matchup
  const c = p.ctx || {}, gp = {G: "guards", F: "forwards", C: "centers"}[c.group];
  const rk = (r, n, goodHigh) => r ? `<span class="rk ${n ? (r <= Math.ceil(n / 3) ? (goodHigh ? "g" : "r") : r > n - Math.ceil(n / 3) ? (goodHigh ? "r" : "g") : "n") : "n"}">${ord(r)}</span>` : "";
  const mrows = [];
  if (c.opp_games) {
    mrows.push(`<div class="kv"><span>${esc(short(p.market))} allowed to ${gp || "his position"}</span><b>${c.def_rank ? rk(c.def_rank, c.teams, side === "over") : p.market === "threes" ? "n/a for threes" : "—"}</b></div>`);
    mrows.push(`<div class="kv"><span>${esc(p.opp)} pace</span><b>${c.pace_rank ? rk(c.pace_rank, c.teams, side === "over") : "—"}</b></div>`);
  } else mrows.push(`<div class="kv"><span>Opponent</span><b>No ${esc(p.opp || "")} games yet this season</b></div>`);
  if (g.lines) mrows.push(`<div class="kv"><span>Game</span><b>${g.lines.total ? "Total " + g.lines.total : ""}${g.lines.spread_home !== undefined ? " · " + esc(g.home) + " " + (g.lines.spread_home > 0 ? "+" : "") + g.lines.spread_home : ""}</b></div>`);
  const l10g = logs.slice(-10), m5 = logs.slice(-5);
  const avgm = a => a.length ? (Math.round(a.reduce((t, l) => t + l.min, 0) / a.length * 10) / 10) : "—";
  if (l10g.length) mrows.push(`<div class="kv"><span>Role</span><b>${l10g.filter(l => l.starter === 1).length}/${l10g.length} starts · ${avgm(m5)} min L5</b></div>`);
  // availability
  const rep = D.sources.report[g.date];
  const arows = [];
  arows.push(`<div class="kv"><span>Official report</span><b>${inj.official ? esc(inj.official.status) + (inj.official.reason ? " · " + esc(inj.official.reason.replace("Injury/Illness - ", "")) : "") : rep ? (inj.listed_team ? "Not listed" : "Team not listed yet") : "Not out yet"}</b></div>`);
  if (rep) arows.push(`<div class="kv"><span>Report time</span><b>${mt((inj.official || {}).published || rep.published, true)}</b></div>`);
  (inj.news || []).forEach(n => arows.push(`<div class="kv"><span>News · ${esc(n.source)}</span><b>${esc(n.headline || n.status || "")} · ${mt(n.detected)}</b></div>`));
  if (without.length) arows.push(`<div class="kv"><span>Teammates out</span><b>${without.map(w => esc(w.name) + " (" + esc(w.status) + ")").join(", ")}</b></div>`);
  // related
  const rel = (D.related[p.id] || []).map(r => {
    const o = D.props.find(x => x.id === r.id); if (!o) return "";
    return `<button class="rc" data-rel="${esc(o.id)}"><div class="nm">${esc(o.player.split(" ").slice(-1)[0])} ${esc(short(o.market))}</div><div class="sub">${o.main === null ? "alt lines" : "O/U " + o.main}</div><div class="rr">r ${r.r > 0 ? "+" : ""}${r.r} · ${r.n} games</div></button>`;
  }).join("");
  const live = p.live && g.state !== "pregame" ? `<div class="box" role="status"><div class="live"><span class="tg ${g.state === "live" ? "tl" : "tn"}">${g.state === "live" ? "LIVE" : "FINAL"}</span>${p.live.value} ${esc(short(p.market))} in ${p.live.min} min</div><div class="note">${esc(g.label || "")}${g.score ? " · " + esc(g.away) + " " + g.score[0] + " – " + esc(g.home) + " " + g.score[1] : ""} · box score ${ago(g.updated)}. ${p.live.value > line ? "Over" : p.live.value < line ? "Under" : "At"} ${line} so far.</div></div>` : "";
  const logRows = win.slice().reverse().map(l => {
    const v = statValue(l, p.market), r = v === null ? "–" : v > line ? '<span class="ov">O</span>' : v < line ? '<span class="un">U</span>' : '<span class="pu">P</span>';
    return `<tr><td>${esc(l.date.slice(5).replace("-", "/"))}</td><td>${l.home ? "" : "@"}${esc(l.opp)}${l.team !== p.team ? " <span style='color:var(--l3)'>(" + esc(l.team) + ")</span>" : ""}</td><td class="r">${l.min}</td><td class="r"><b>${v === null ? "–" : v}</b></td><td class="r">${r}</td></tr>`;
  }).join("");
  const chips = [["home", true, "Home"], ["home", false, "Away"], ["starter", true, "Starter"], ["starter", false, "Bench"]].map(([k, v, lab]) =>
    `<button class="chip" data-f="${k}" data-v="${v}" aria-pressed="${DT[k] === v}">${lab}</button>`).join("") +
    without.map(w => `<button class="chip" data-wo="${w.key}" aria-pressed="${!!DT.without[w.key]}">Without ${esc(w.name.split(" ").slice(-1)[0])}</button>`).join("");
  pg.innerHTML = `<div class="bar"><div class="bar-r"><button class="bk">${CHEV}Props</button><span class="upd">${esc(NAME[p.market])}</span></div></div>
    <div class="hero"><div class="av">${head(p.pid)}${logo(p.team)}</div><div><h2>${esc(p.player)}</h2><div class="sub">${esc(p.team || "")} ${esc(vs(p))} · ${when(g)} ${injTag(p)}</div></div></div>
    <nav class="chips" aria-label="Markets" style="margin:14px 0 0">${mkts.map(m => `<button class="chip" data-mk="${m}" aria-pressed="${m === p.market}">${esc(NAME[m])}</button>`).join("")}</nav>
    ${live}
    <div class="box"><div class="lc"><div class="big num"><i>${side === "under" ? "UNDER" : "OVER"}</i>${line}</div>
      <div class="stp"><button data-step="-0.5" aria-label="Lower the line by half a point">−</button><button data-step="0.5" aria-label="Raise the line by half a point">+</button></div></div>
      <div class="bks">${bk}</div>${line !== p.main && p.main !== null ? `<div class="note">The main line is ${p.main}. Prices are shown at ${line} where a book offers it.</div>` : ""}${opened}</div>
    <div class="wins" role="group" aria-label="Games window">${winHtml}</div>
    <div class="box"><div class="sum"><div class="r num">${hits}/${s.n}<small>${side} ${line}</small></div><div class="a num">Avg <b>${s.avg === null ? "–" : s.avg}</b><br>Median <b>${s.med === null ? "–" : s.med}</b></div></div>
      <div class="chw" id="chw">${chart(win, p.market, line)}</div>
      <div class="fch" role="group" aria-label="Filter games">${chips}</div>
      ${s.n && s.n < 5 ? '<div class="note" style="color:var(--org)">Small sample: ' + s.n + " game" + (s.n === 1 ? "" : "s") + ".</div>" : ""}
      <div class="note">Past results only, every team he played for. Green = over the line, striped red = under, grey = push.</div></div>
    <div class="box"><h3>Matchup</h3>${mrows.join("")}<div class="note">${esc(p.opp || "Opponent")}'s rank among ${c.teams || "the"} teams this season: 1st = allows the most / plays fastest. Green = helps the ${side}.</div></div>
    <div class="box"><h3>Availability</h3>${arows.join("")}<div class="note">Official = the NBA injury report. News is third-party.</div></div>
    ${rel ? `<div class="box"><h3>Related props</h3><div class="rel">${rel}</div><div class="note">How closely the two stats moved together in past games (r from −1 to +1). History, not a prediction.</div></div>` : ""}
    ${p.flag ? `<div class="box"><h3>Engine</h3><span class="tg tf" style="margin:0 6px 0 0">SHADOW · NOT A BET</span>${esc(p.flag.tier)} at ${p.flag.line} · ${p.flag.card === 1 ? "on the card" : "logged only" + (p.flag.why ? " (" + esc(p.flag.why.toLowerCase()) + ")" : "")}</div>` : ""}
    <div class="box"><details class="log"><summary>Game log · ${win.length}</summary><table><thead><tr><th>Date</th><th>Opp</th><th class="r">Min</th><th class="r">${esc(short(p.market))}</th><th class="r">${line}</th></tr></thead><tbody>${logRows || '<tr><td colspan="5">No games.</td></tr>'}</tbody></table></details></div>
    <div class="end"></div>`;
  const cw = $("#chw"); if (cw) cw.scrollLeft = cw.scrollWidth;
  $("#pg .bk").onclick = () => history.back();
  $$("[data-step]", pg).forEach(b => b.onclick = () => { DT.line = Math.max(0.5, Math.round((DT.line + +b.dataset.step) * 2) / 2); renderProp(); $(`[data-step="${b.dataset.step}"]`, pg).focus({preventScroll: true}); });
  $$("[data-win]", pg).forEach(b => b.onclick = () => { DT.win = b.dataset.win; renderProp(); $(`[data-win="${DT.win}"]`, pg).focus({preventScroll: true}); });
  $$("[data-f]", pg).forEach(b => b.onclick = () => { const k = b.dataset.f, v = b.dataset.v === "true"; DT[k] = DT[k] === v ? null : v; renderProp(); $(`[data-f="${k}"][data-v="${b.dataset.v}"]`, pg).focus({preventScroll: true}); });
  $$("[data-wo]", pg).forEach(b => b.onclick = () => { const k = b.dataset.wo; DT.without[k] = !DT.without[k]; renderProp(); $(`[data-wo="${k}"]`, pg).focus({preventScroll: true}); });
  $$("[data-mk]", pg).forEach(b => b.onclick = () => { const id = p.gid + "|" + p.pid + "|" + b.dataset.mk; if (id !== p.id) { openProp(id, false); history.replaceState({p: id}, "", hashState()); } });
  $$("[data-rel]", pg).forEach(b => b.onclick = () => openProp(b.dataset.rel));
}
// ── data ──
function load() {
  if (!D) { LOADING = true; render(); }
  fetch("nba_props.json?t=" + Date.now(), {cache: "no-store"}).then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(j => {
      const first = !D; D = j; ERR = null; LOADING = false;
      const y = window.scrollY;
      render(); if (!first) window.scrollTo(0, y);
      if (CUR) renderProp();
      $("#live").textContent = "Props updated";
      if (first && HASH_P) { history.replaceState(null, "", hashState()); openProp(HASH_P); }
    })
    .catch(e => { LOADING = false; ERR = e.message || String(e); if (!D) render(); else { const u = $("#upd"); if (u) u.textContent = "Refresh failed"; } });
}
const HASH_P = readHash();
window.addEventListener("popstate", () => { const p = new URLSearchParams(location.hash.slice(1)).get("p"); if (p && p !== CUR) openProp(p, false); else if (!p && CUR) closeProp(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") { if (!$("#sheet").hidden) closeSheet(); else if (CUR) history.back(); } });
document.addEventListener("DOMContentLoaded", () => {
  $("#scrim").onclick = closeSheet;
  load();
  setInterval(load, 120000);
  setInterval(() => { const u = $("#upd"); if (u && D) u.textContent = "Updated " + ago(D.generated_at); }, 30000);
});
})();
"""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Pickz">
<meta name="theme-color" content="#000000">
<title>Pickz · NBA Props</title>
<link rel="icon" href="icon-64.png">
<link rel="apple-touch-icon" href="icon-180.png">
<style>__CSS__</style>
</head>
<body>
<div id="app"></div>
<div id="pg" class="pg" role="dialog" aria-modal="true" aria-label="Prop details" hidden></div>
<div id="scrim" class="scrim" hidden></div>
<div id="sheet" class="sheet" role="dialog" aria-modal="true" aria-labelledby="sht" hidden></div>
<div id="live" class="sr" role="status" aria-live="polite"></div>
<script>__CORE__</script>
<script>__APP__</script>
</body>
</html>
"""


def page():
    return (PAGE.replace("__CSS__", CSS).replace("__CORE__", JS_CORE)
            .replace("__APP__", JS_APP.replace("__TEAM_ID__", json.dumps(TEAM_ID))))
