"""The Pickz NBA prop research page (docs/nba_props.html). Data: nba_props.json, written by nba_research.py.

Pickz is dark and phone-first (the Cupertino tokens of dashboard.py: --cu-*). Vanilla JS, no dependencies, so the
board server serves it as a static file next to index.html. JS_CORE holds the pure calculations (stat values, hit
counts, windows, splits, filters, sorting); test_nba_research runs it in node against the Python versions.
"""
from __future__ import annotations

import json

from nba_board import TEAM_ID

CSS = r"""
:root{color-scheme:dark;--cu-bg:#000;--cu-grp:#1c1c1e;--cu-grp2:#2c2c2e;--cu-lbl:#fff;--cu-lbl2:rgba(235,235,245,.6);
--cu-lbl3:rgba(235,235,245,.3);--cu-fill:rgba(120,120,128,.24);--cu-sep:rgba(84,84,88,.65);--cu-blue:#0a84ff;
--cu-grn:#30d158;--cu-org:#ff9f0a;--cu-red:#ff453a;--cu-yel:#ffd60a;--hair:rgba(255,255,255,.08)}
*{box-sizing:border-box}
html,body{margin:0;background:var(--cu-bg);color:var(--cu-lbl);
font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--cu-blue)}
button,select,input{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--cu-blue);outline-offset:2px;border-radius:8px}
.sr{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.wrap{max-width:1180px;margin:0 auto;padding:max(12px,env(safe-area-inset-top)) 16px 48px}
.top{display:flex;align-items:center;gap:10px;margin:4px 0 6px}
.back{font-size:15px;font-weight:600;text-decoration:none;padding:6px 4px}
h1{margin:0;font-size:28px;font-weight:800;letter-spacing:-.02em}
.sub{margin:2px 0 12px;font-size:12px;font-weight:600;color:var(--cu-lbl3);font-variant-numeric:tabular-nums}
.banner{margin:8px 0;padding:10px 12px;border-radius:12px;font-size:13px;font-weight:600;background:rgba(255,159,10,.14);
color:var(--cu-org)}
.banner.err{background:rgba(255,69,58,.14);color:var(--cu-red)}
.row{display:flex;gap:8px;overflow-x:auto;padding:2px 0 8px;scrollbar-width:none}
.row::-webkit-scrollbar{display:none}
.chip{flex:none;display:inline-flex;align-items:center;gap:6px;padding:8px 12px;border-radius:999px;border:0;
background:var(--cu-grp);color:var(--cu-lbl2);font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}
.chip[aria-pressed="true"]{background:var(--cu-lbl);color:#000}
.chip img{width:18px;height:18px}
.chip .lv{color:var(--cu-red);font-weight:800}
.chip[aria-pressed="true"] .lv{color:#c00}
.ctl{display:grid;grid-template-columns:1fr;gap:8px;margin:4px 0 6px}
.ctl .line{display:flex;gap:8px;flex-wrap:wrap}
.field{display:flex;flex-direction:column;gap:3px;min-width:0;flex:1 1 140px}
.field span{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--cu-lbl3)}
.field input,.field select{width:100%;padding:10px 12px;border-radius:12px;border:1px solid var(--hair);
background:var(--cu-grp);font-size:15px}
.search{flex:2 1 220px}
.btn{padding:10px 14px;border-radius:12px;border:0;background:var(--cu-grp2);font-size:14px;font-weight:700;cursor:pointer}
.btn:disabled{opacity:.4;cursor:not-allowed}
.btn.dir{min-width:46px}
details.more summary{cursor:pointer;font-size:13px;font-weight:700;color:var(--cu-lbl2);padding:6px 0;list-style:none}
details.more summary::-webkit-details-marker{display:none}
.count{display:flex;justify-content:space-between;align-items:baseline;margin:14px 0 6px;font-size:11px;font-weight:800;
letter-spacing:.1em;text-transform:uppercase}
.count span{color:var(--cu-lbl3);font-variant-numeric:tabular-nums;text-transform:none;letter-spacing:0}
.list{display:flex;flex-direction:column;gap:8px}
.pc{display:grid;grid-template-columns:44px minmax(0,1fr) auto;grid-template-areas:"av nm ln" "meta meta meta";
gap:6px 12px;align-items:center;width:100%;text-align:left;padding:12px;border-radius:16px;border:0;
background:var(--cu-grp);cursor:pointer}
.pc:hover{background:#232325}
.av{position:relative;width:44px;height:44px;border-radius:50%;background:var(--cu-grp2)}
.pc .av{grid-area:av} .pc .nmw{grid-area:nm;min-width:0} .pc .meta{grid-area:meta} .pc .ln{grid-area:ln}
.av img.hs{width:44px;height:44px;border-radius:50%;object-fit:cover;object-position:50% 12%}
.av img.lg{position:absolute;right:-4px;bottom:-3px;width:20px;height:20px;padding:2px;border-radius:50%;background:#000}
.nm{font-size:16px;font-weight:700;letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mu{font-size:12px;font-weight:600;color:var(--cu-lbl2);font-variant-numeric:tabular-nums}
.ln{text-align:right;font-variant-numeric:tabular-nums}
.ln b{display:block;font-size:20px;font-weight:800;letter-spacing:-.02em}
.ln b i{font-style:normal;font-size:12px;font-weight:700;color:var(--cu-lbl2);margin-right:3px}
.ln small{display:block;font-size:11px;font-weight:700;color:var(--cu-lbl3);white-space:nowrap}
.meta{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;font-weight:600;color:var(--cu-lbl3);
font-variant-numeric:tabular-nums}
.meta b{color:var(--cu-lbl);font-weight:700}
.tag{display:inline-block;padding:2px 6px 1px;border-radius:5px;font-size:10px;font-weight:800;letter-spacing:.05em}
.t-q{background:rgba(255,214,10,.16);color:var(--cu-yel)} .t-o{background:rgba(255,69,58,.16);color:var(--cu-red)}
.t-p{background:rgba(48,209,88,.14);color:var(--cu-grn)} .t-f{background:rgba(255,159,10,.16);color:var(--cu-org)}
.t-l{background:rgba(255,69,58,.18);color:var(--cu-red)} .t-n{background:var(--cu-fill);color:var(--cu-lbl2)}
.empty{padding:32px 8px;text-align:center;color:var(--cu-lbl2);font-size:14px}
.empty b{display:block;color:var(--cu-lbl);font-size:16px;margin-bottom:6px}
.sk{height:84px;border-radius:16px;background:linear-gradient(90deg,var(--cu-grp) 0%,#242426 50%,var(--cu-grp) 100%);
background-size:200% 100%;animation:sh 1.2s infinite}
@keyframes sh{to{background-position:-200% 0}}
@media (prefers-reduced-motion:reduce){.sk{animation:none}}
@media (min-width:900px){
 .ctl{grid-template-columns:1fr}
 .pc{grid-template-columns:44px minmax(200px,1.2fr) minmax(0,2fr) 120px;grid-template-areas:"av nm meta ln"}
}
dialog{width:min(980px,100vw);max-width:100vw;max-height:100dvh;height:100dvh;margin:0 auto;padding:0;border:0;
background:var(--cu-bg);color:var(--cu-lbl)}
dialog::backdrop{background:rgba(0,0,0,.6)}
@media (min-width:900px){dialog{height:auto;max-height:92vh;margin-top:4vh;border-radius:20px;border:1px solid var(--hair)}}
.dl{padding:max(12px,env(safe-area-inset-top)) 16px 40px;overflow-y:auto;max-height:100dvh}
@media (min-width:900px){.dl{max-height:92vh}}
.dh{display:flex;align-items:center;gap:12px;position:sticky;top:0;background:var(--cu-bg);padding:6px 0 10px;z-index:2}
.dh .av{width:54px;height:54px;flex:none}
.dh .av img.hs{width:54px;height:54px}
.dh h2{margin:0;font-size:20px;font-weight:800;letter-spacing:-.01em}
.x{margin-left:auto;width:40px;height:40px;border-radius:50%;border:0;background:var(--cu-grp2);font-size:20px;cursor:pointer}
.sec{margin:18px 0 0}
.sec h3{margin:0 0 8px;font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--cu-lbl2)}
.card{background:var(--cu-grp);border-radius:16px;padding:12px}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;font-variant-numeric:tabular-nums}
.kv div b{display:block;font-size:20px;font-weight:800;letter-spacing:-.02em}
.kv div span{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--cu-lbl3)}
.note{margin-top:8px;font-size:12px;color:var(--cu-lbl3)}
.warn{color:var(--cu-org)}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th{font-size:10px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:var(--cu-lbl3);text-align:left;
padding:6px 6px;border-bottom:1px solid var(--cu-sep)}
td{padding:8px 6px;border-bottom:1px solid var(--hair)}
td.r,th.r{text-align:right}
.scroll{overflow-x:auto}
.ov{color:var(--cu-grn);font-weight:700} .un{color:var(--cu-red);font-weight:700} .pu{color:var(--cu-lbl2);font-weight:700}
svg.ch{width:100%;height:auto;display:block;max-width:100%}
svg.ch text{fill:var(--cu-lbl3);font-size:10px;font-weight:700}
svg.ch .lbl{fill:var(--cu-lbl);font-size:11px;font-weight:800}
svg.ch g.bar:focus{outline:none} svg.ch g.bar:focus rect{stroke:var(--cu-blue);stroke-width:2}
.live{display:flex;align-items:center;gap:10px;font-weight:700}
.rel{display:flex;flex-direction:column;gap:6px}
.rel button{display:flex;justify-content:space-between;gap:10px;width:100%;padding:10px 12px;border-radius:12px;border:0;
background:var(--cu-grp2);text-align:left;cursor:pointer;font-size:13px;font-weight:600}
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
function windowed(logs, win, season) {
  if (win === "l5") return logs.slice(-5);
  if (win === "l10") return logs.slice(-10);
  if (win === "l20") return logs.slice(-20);
  if (win === "season") return logs.filter(function (l) { return seasonOf(l.date) === season; });
  if (win === "last") return logs.filter(function (l) { return seasonOf(l.date) !== season; });
  return logs.slice();
}
function splitRows(logs, market, line, opts) {
  var out = [];
  function add(label, sub) { out.push({label: label, s: hitSummary(sub.map(function (l) { return statValue(l, market); }), line)}); }
  add("Home", logs.filter(function (l) { return l.home === 1; }));
  add("Away", logs.filter(function (l) { return l.home === 0; }));
  if (opts && opts.opp) add("vs " + opts.opp, logs.filter(function (l) { return l.opp === opts.opp; }));
  add("Started", logs.filter(function (l) { return l.starter === 1; }));
  add("Bench", logs.filter(function (l) { return l.starter === 0; }));
  ((opts && opts.without) || []).forEach(function (w) {
    var played = {}; w.played.forEach(function (g) { played[g] = 1; });
    add("Without " + w.name, logs.filter(function (l) { return l.team === w.team && l.date >= w.since && !played[l.gid]; }));
  });
  return out;
}
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
function bestOver(prop, line, book) {
  var best = null;
  ["fd", "dk"].forEach(function (b) {
    if (book && book !== "all" && b !== book) return;
    var r = rungAt(prop.books[b], line);
    if (r && r[1] && (!best || r[1] > best.odds)) best = {book: b, odds: r[1]};
  });
  return best;
}
function l10(prop, logsOf) {
  if (prop.main === null || prop.main === undefined) return null;
  var lg = logsOf(prop).slice(-10).map(function (l) { return statValue(l, prop.market); });
  return hitSummary(lg, prop.main);
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
      var b = line === null ? null : bestOver(p, line, st.book);
      if (!b) return false;
      var am = b.odds >= 2 ? (b.odds - 1) * 100 : -100 / (b.odds - 1);
      if (st.omin !== "" && st.omin != null && am < +st.omin) return false;
      if (st.omax !== "" && st.omax != null && am > +st.omax) return false;
    }
    return true;
  });
}
function sortProps(list, key, dir, logsOf) {
  var sgn = dir === "asc" ? 1 : -1;
  function val(p) {
    if (key === "player") return p.player.toLowerCase();
    if (key === "line") return p.main;
    if (key === "odds") { var b = p.main === null ? null : bestOver(p, p.main, "all"); return b ? b.odds : null; }
    var s = l10(p, logsOf);
    if (key === "avg10") return s && s.n ? s.avg : null;
    if (key === "hit10") return s && s.n ? s.over / s.n : null;
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
  rowsToLogs: rowsToLogs, windowed: windowed, splitRows: splitRows, american: american, decimalOf: decimalOf,
  bestOver: bestOver, filterProps: filterProps, sortProps: sortProps};
"""

JS_APP = r"""
(function () {
var TEAM_ID = __TEAM_ID__;
var D = null, ERR = null, LOADING = true, TIMER = null, OPEN = null;
var ST = {date: null, gid: "all", team: "all", market: "all", book: "all", q: "", sort: "hit10", dir: "desc",
          lmin: "", lmax: "", omin: "", omax: ""};
var DST = {line: null, win: "l10"};
var $ = function (s, r) { return (r || document).querySelector(s); };
function esc(s) { return String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, function (c) {
  return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
function mt(iso, withDay) {
  if (!iso) return "—";
  var d = new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
  var o = {timeZone: "America/Denver", hour: "numeric", minute: "2-digit"};
  if (withDay) { o.weekday = "short"; }
  return d.toLocaleString("en-US", o) + " MT";
}
function ago(iso) {
  if (!iso) return "never";
  var m = (Date.now() - new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z").getTime()) / 60000;
  return m < 1 ? "just now" : m < 60 ? Math.round(m) + " min ago" : Math.round(m / 60) + " h ago";
}
function logo(t, cls) { var id = TEAM_ID[t]; return id ? '<img class="' + (cls || "lg") + '" alt="" src="https://cdn.nba.com/logos/nba/' + id + '/global/D/logo.svg">' : ""; }
function head(pid) { return '<img class="hs" alt="" loading="lazy" src="https://cdn.nba.com/headshots/nba/latest/260x190/' + pid + '.png" onerror="this.remove()">'; }
function gameOf(gid) { return (D.games || []).find(function (g) { return g.gid === gid; }); }
function logsOf(p) {
  var pl = D.players[String(p.pid)];
  if (!pl) return [];
  if (!pl._logs) pl._logs = rowsToLogs(D.log_cols, pl.logs);
  return pl._logs;
}
function label(m) { return (D.markets || {})[m] || m; }
function readHash() {
  var h = new URLSearchParams(location.hash.slice(1));
  Object.keys(ST).forEach(function (k) { if (h.has(k)) ST[k] = h.get(k); });
  return h.get("p");
}
function writeHash() {
  var h = new URLSearchParams();
  Object.keys(ST).forEach(function (k) { if (ST[k] !== "" && ST[k] !== null && ST[k] !== "all") h.set(k, ST[k]); });
  if (OPEN) h.set("p", OPEN);
  history.replaceState(null, "", "#" + h.toString());
}
function injuryTag(p) {
  var g = gameOf(p.gid), inj = D.injuries[g.date + "|" + p.pid];
  if (!inj || !inj.official) return "";
  var s = inj.official.status, c = s === "Out" ? "t-o" : s === "Doubtful" ? "t-o" : s === "Questionable" ? "t-q" : "t-p";
  return '<span class="tag ' + c + '" title="Official report">' + esc(s.toUpperCase()) + "</span>";
}
function stateTag(g) {
  if (!g) return "";
  if (g.state === "live") return '<span class="tag t-l">LIVE ' + esc(g.label) + "</span>";
  if (g.state === "final") return '<span class="tag t-n">FINAL</span>';
  if (g.state === "postponed") return '<span class="tag t-o">POSTPONED</span>';
  return "";
}
function bookCell(p, b) {
  var q = p.books[b];
  if (!q) return "";
  var r = q.main === null ? null : rungAt(q, q.main);
  return '<span>' + (b === "fd" ? "FD" : "DK") + " " + (r ? "<b>" + r[0] + "</b> " + american(r[1]) + "/" + american(r[2]) : "alt lines only") + "</span>";
}
function freshness() {
  var b = D.sources.books, parts = [];
  ["fd", "dk"].forEach(function (k) { if (b[k]) parts.push((k === "fd" ? "FanDuel " : "DraftKings ") + ago(b[k].updated)); });
  var r = D.sources.report[ST.date];
  parts.push(r ? "Report " + mt(r.published) : "No official report for this date yet");
  return "Updated " + ago(D.generated_at) + " · " + parts.join(" · ");
}
function banners() {
  var out = [], b = D.sources.books;
  ["fd", "dk"].forEach(function (k) {
    if (!b[k]) out.push((k === "fd" ? "FanDuel" : "DraftKings") + " has no props stored for these games.");
    else if (b[k].stale) out.push((k === "fd" ? "FanDuel" : "DraftKings") + " prices are " + Math.round(b[k].age_min) + " min old (stale).");
  });
  var age = (Date.now() - new Date(D.generated_at).getTime()) / 60000;
  if (age > 10) out.push("This page's data is " + Math.round(age) + " min old — the research feed may be down.");
  if (!D.sources.matchup.available) out.push("Matchup factors are unavailable (no box-score cache).");
  return out.map(function (t) { return '<div class="banner" role="status">' + esc(t) + "</div>"; }).join("");
}
function controls(props) {
  var games = D.games.filter(function (g) { return g.date === ST.date; });
  var teams = {}, markets = {};
  props.forEach(function (p) { var g = gameOf(p.gid); if (g && g.date === ST.date) { if (p.team) teams[p.team] = 1; markets[p.market] = 1; } });
  var dchips = D.dates.map(function (d) {
    var n = D.games.filter(function (g) { return g.date === d; }).length;
    var lab = new Date(d + "T12:00:00Z").toLocaleDateString("en-US", {weekday: "short", month: "short", day: "numeric", timeZone: "UTC"});
    return '<button class="chip" data-date="' + d + '" aria-pressed="' + (d === ST.date) + '">' + esc(lab) + " · " + n + "</button>";
  }).join("");
  var gchips = ['<button class="chip" data-gid="all" aria-pressed="' + (ST.gid === "all") + '">All games</button>'].concat(games.map(function (g) {
    var t = g.state === "live" ? '<span class="lv">LIVE</span>' : g.state === "final" ? "Final" : g.state === "postponed" ? "PPD" : mt(g.tip);
    return '<button class="chip" data-gid="' + g.gid + '" aria-pressed="' + (ST.gid === g.gid) + '">' + logo(g.away, "") + esc(g.away) + " @ " + esc(g.home) + logo(g.home, "") + " · " + t + "</button>";
  })).join("");
  function opts(obj, cur, all, lab, order) {
    var keys = Object.keys(obj).sort(function (a, b) { return order ? order.indexOf(a) - order.indexOf(b) : a < b ? -1 : 1; });
    return '<option value="all">' + all + "</option>" + keys.map(function (k) {
      return '<option value="' + k + '"' + (k === cur ? " selected" : "") + ">" + esc(lab ? lab(k) : k) + "</option>"; }).join("");
  }
  return '<nav class="row" aria-label="Slate date">' + dchips + '</nav><nav class="row" aria-label="Games">' + gchips + "</nav>" +
    '<div class="ctl"><div class="line">' +
    '<label class="field search"><span>Player or team</span><input id="q" type="search" autocomplete="off" placeholder="Search players" value="' + esc(ST.q) + '"></label>' +
    '<label class="field"><span>Market</span><select id="market">' + opts(markets, ST.market, "All markets", label, ["points", "rebounds", "assists", "threes", "pra", "pts_reb", "pts_ast", "reb_ast"]) + "</select></label>" +
    '<label class="field"><span>Team</span><select id="team">' + opts(teams, ST.team, "All teams") + "</select></label>" +
    '<label class="field"><span>Book</span><select id="book"><option value="all">Both books</option><option value="fd"' + (ST.book === "fd" ? " selected" : "") + '>FanDuel</option><option value="dk"' + (ST.book === "dk" ? " selected" : "") + ">DraftKings</option></select></label>" +
    '<label class="field"><span>Sort</span><select id="sort">' + [["hit10", "L10 over rate"], ["avg10", "L10 average"], ["line", "Line"], ["odds", "Over price"], ["player", "Player"]].map(function (o) {
      return '<option value="' + o[0] + '"' + (o[0] === ST.sort ? " selected" : "") + ">" + o[1] + "</option>"; }).join("") + "</select></label>" +
    '<button class="btn dir" id="dir" aria-label="Sort direction: ' + (ST.dir === "asc" ? "ascending" : "descending") + '">' + (ST.dir === "asc" ? "↑" : "↓") + "</button>" +
    "</div>" +
    '<details class="more"' + (ST.lmin || ST.lmax || ST.omin || ST.omax ? " open" : "") + '><summary>Line and odds range</summary><div class="line">' +
    '<label class="field"><span>Line from</span><input id="lmin" type="number" inputmode="decimal" step="0.5" value="' + esc(ST.lmin) + '"></label>' +
    '<label class="field"><span>Line to</span><input id="lmax" type="number" inputmode="decimal" step="0.5" value="' + esc(ST.lmax) + '"></label>' +
    '<label class="field"><span>Over odds from (US)</span><input id="omin" type="number" inputmode="numeric" placeholder="-200" value="' + esc(ST.omin) + '"></label>' +
    '<label class="field"><span>Over odds to (US)</span><input id="omax" type="number" inputmode="numeric" placeholder="+150" value="' + esc(ST.omax) + '"></label>' +
    "</div></details>" +
    '<div class="line"><button class="btn" id="reset">Reset filters</button></div></div>';
}
function card(p) {
  var g = gameOf(p.gid), s = l10(p, logsOf);
  var hit = s && s.n ? "<b>" + s.over + "/" + s.n + "</b> over L" + s.n : "no games logged";
  var avg = s && s.n ? "avg <b>" + s.avg + "</b>" : "";
  var sea = p.summary && p.summary.season.n ? "season <b>" + p.summary.season.over + "/" + p.summary.season.n + "</b>" : "";
  var live = p.live && g.state !== "pregame" ? '<span class="tag ' + (g.state === "live" ? "t-l" : "t-n") + '">' + (g.state === "live" ? "LIVE " : "FINAL ") + p.live.value + "</span>" : "";
  var flag = p.flag ? '<span class="tag t-f" title="Engine shadow flag — not a bet">ENGINE ' + (p.flag.card === 1 ? "CARD" : "FLAG") + "</span>" : "";
  var opp = p.team ? (p.home ? "vs " : "@ ") + esc(p.opp) : esc(g.away + " @ " + g.home);
  return '<button class="pc" data-id="' + esc(p.id) + '" aria-label="' + esc(p.player + " " + label(p.market) + " " + (p.main === null ? "alt lines" : p.main)) + '">' +
    '<div class="av">' + head(p.pid) + logo(p.team) + "</div>" +
    '<div class="nmw"><div class="nm">' + esc(p.player) + " " + injuryTag(p) + "</div><div class=\"mu\">" + esc(p.team || "") + " " + opp + " · " + (g.state === "pregame" ? mt(g.tip) : esc(g.label || g.state)) + "</div></div>" +
    '<div class="meta">' + bookCell(p, "fd") + bookCell(p, "dk") + "<span>" + hit + "</span><span>" + avg + "</span><span>" + sea + "</span>" + live + flag + stateTag(g === undefined ? null : (g.state === "postponed" ? g : null)) + "</div>" +
    '<div class="ln"><b><i>' + esc(label(p.market)) + "</i>" + (p.main === null ? "—" : p.main) + "</b><small>" + (p.main === null ? "alt lines" : "main line") + "</small></div></button>";
}
function render() {
  var root = $("#app");
  if (LOADING && !D) { root.innerHTML = '<div class="list" aria-busy="true">' + "<div class=\"sk\"></div>".repeat(6) + "</div>"; return; }
  if (!D) {
    root.innerHTML = '<div class="banner err" role="alert">Could not load the prop feed (' + esc(ERR) + ').</div><button class="btn" id="retry">Try again</button>';
    $("#retry").onclick = load; return;
  }
  if (!ST.date || D.dates.indexOf(ST.date) < 0) ST.date = D.dates.find(function (d) { return D.games.some(function (g) { return g.date === d; }); }) || D.dates[0];
  var all = D.props;
  var list = sortProps(filterProps(all, ST, gameOf, logsOf), ST.sort, ST.dir, logsOf);
  var onDate = all.filter(function (p) { var g = gameOf(p.gid); return g && g.date === ST.date; }).length;
  var gamesOnDate = D.games.filter(function (g) { return g.date === ST.date; }).length;
  var body;
  if (!gamesOnDate) body = '<div class="empty"><b>No NBA games on this date.</b></div>';
  else if (!onDate) body = '<div class="empty"><b>No props posted yet for this slate.</b>FanDuel and DraftKings usually post player props on game day. ' + esc(freshness()) + "</div>";
  else if (ST.gid !== "all" && !all.some(function (p) { return p.gid === ST.gid; })) body = '<div class="empty"><b>No props posted yet for this game.</b>' + esc(freshness()) + "</div>";
  else if (!list.length) body = '<div class="empty"><b>No props match these filters.</b><button class="btn" id="reset2">Reset filters</button></div>';
  else body = '<div class="list">' + list.map(card).join("") + "</div>";
  root.innerHTML = banners() + '<p class="sub">' + esc(freshness()) + "</p>" + controls(all) +
    '<div class="count">PROPS<span>' + list.length + " of " + onDate + "</span></div>" + body;
  bind();
}
function bind() {
  document.querySelectorAll("[data-date]").forEach(function (b) { b.onclick = function () { ST.date = b.dataset.date; ST.gid = "all"; ST.team = "all"; writeHash(); render(); }; });
  document.querySelectorAll("[data-gid]").forEach(function (b) { b.onclick = function () { ST.gid = b.dataset.gid; writeHash(); render(); }; });
  ["market", "team", "book", "sort"].forEach(function (id) { var el = $("#" + id); if (el) el.onchange = function () { ST[id] = el.value; writeHash(); render(); }; });
  ["lmin", "lmax", "omin", "omax"].forEach(function (id) { var el = $("#" + id); if (el) el.onchange = function () { ST[id] = el.value; writeHash(); render(); }; });
  var q = $("#q");
  if (q) q.oninput = function () { ST.q = q.value; writeHash(); var pos = q.selectionStart; render(); var n = $("#q"); n.focus(); n.setSelectionRange(pos, pos); };
  var d = $("#dir"); if (d) d.onclick = function () { ST.dir = ST.dir === "asc" ? "desc" : "asc"; writeHash(); render(); $("#dir").focus(); };
  function reset() { ST.gid = "all"; ST.team = "all"; ST.market = "all"; ST.book = "all"; ST.q = ""; ST.lmin = ST.lmax = ST.omin = ST.omax = ""; ST.sort = "hit10"; ST.dir = "desc"; writeHash(); render(); }
  ["#reset", "#reset2"].forEach(function (s) { var b = $(s); if (b) b.onclick = reset; });
  document.querySelectorAll(".pc").forEach(function (b) { b.onclick = function () { openProp(b.dataset.id, b); }; });
}
// ── detail ──
var LAST_FOCUS = null;
function openProp(id, from) {
  var p = D.props.find(function (x) { return x.id === id; });
  if (!p) return;
  OPEN = id; LAST_FOCUS = from || null; DST.line = p.main !== null ? p.main : allLines(p)[0]; DST.win = "l10";
  writeHash();
  var dlg = $("#dlg");
  if (!dlg.open) dlg.showModal();           // open first: the chart is drawn at the dialog's real width
  renderDetail();
  $("#dlg .x").focus();
}
function closeProp() { OPEN = null; writeHash(); var dlg = $("#dlg"); if (dlg.open) dlg.close(); if (LAST_FOCUS && document.body.contains(LAST_FOCUS)) LAST_FOCUS.focus(); }
function allLines(p) {
  var s = {};
  ["fd", "dk"].forEach(function (b) { if (p.books[b]) p.books[b].rungs.forEach(function (r) { s[r[0]] = 1; }); });
  return Object.keys(s).map(Number).sort(function (a, b) { return a - b; });
}
function chart(logs, market, line, avail) {
  var n = logs.length;
  if (!n) return '<div class="empty">No games in this window.</div>';
  var vals = logs.map(function (l) { return statValue(l, market); });
  var max = Math.max(line * 1.25, Math.max.apply(null, vals.filter(function (v) { return v !== null; }).concat([1]))) * 1.08;
  // drawn at the card's real width (1 SVG unit = 1 CSS px), so labels keep their size on any screen
  var W = Math.max(300, Math.min(avail || 360, 940)), bw = Math.max(6, Math.min(56, (W - 34) / n));
  var gap = Math.max(2, bw * .18), H = 210, top = 14, bot = 168;
  W = Math.max(W, 34 + n * bw);
  var y = function (v) { return bot - (v / max) * (bot - top); };
  var out = ['<svg class="ch" viewBox="0 0 ' + W + " " + H + '" role="group" aria-label="' + esc(label(market) + " in each of the last " + n + " games, with the " + line + " line") + '">',
    '<defs><pattern id="hz" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="var(--cu-red)" opacity=".35"/><line x1="0" y1="0" x2="0" y2="5" stroke="var(--cu-red)" stroke-width="3"/></pattern></defs>'];
  [0, max / 2].forEach(function (t) { out.push('<text x="0" y="' + (y(t) + 3) + '">' + Math.round(t) + "</text>"); });
  logs.forEach(function (l, i) {
    var v = vals[i], x = 30 + i * bw, res = v === null ? "no value" : v > line ? "over" : v < line ? "under" : "push";
    var h = v === null ? 0 : Math.max(2, bot - y(v));
    var fill = res === "over" ? "var(--cu-grn)" : res === "under" ? "url(#hz)" : "var(--cu-lbl3)";
    var d = new Date(l.date + "T12:00:00Z").toLocaleDateString("en-US", {month: "short", day: "numeric", timeZone: "UTC"});
    var desc = d + " " + (l.home ? "vs " : "@ ") + l.opp + ": " + (v === null ? "no value" : v + " " + label(market)) + ", " + res + " " + line + " (" + l.min + " min)";
    out.push('<g class="bar" tabindex="0" role="img" aria-label="' + esc(desc) + '"><title>' + esc(desc) + "</title>" +
      '<rect x="' + x + '" y="' + (bot - h) + '" width="' + (bw - gap) + '" height="' + h + '" rx="2" fill="' + fill + '"' + (res === "push" ? ' stroke="var(--cu-lbl2)"' : "") + "/>" +
      (n <= 20 && v !== null ? '<text x="' + (x + (bw - gap) / 2) + '" y="' + (bot - h - 3) + '" text-anchor="middle" class="lbl">' + v + "</text>" : "") +
      (n <= 20 || i % 5 === 4 ? '<text x="' + (x + (bw - gap) / 2) + '" y="' + (bot + 14) + '" text-anchor="middle">' + esc(l.opp) + '</text><text x="' + (x + (bw - gap) / 2) + '" y="' + (bot + 26) + '" text-anchor="middle">' + esc(d) + "</text>" : "") +
      (n <= 20 ? '<text x="' + (x + (bw - gap) / 2) + '" y="' + (bot + 38) + '" text-anchor="middle">' + (res === "over" ? "O" : res === "under" ? "U" : res === "push" ? "P" : "–") + "</text>" : "") + "</g>");
  });
  out.push('<line x1="28" x2="' + W + '" y1="' + y(line) + '" y2="' + y(line) + '" stroke="var(--cu-lbl)" stroke-dasharray="5 4" stroke-width="1.5"/>');
  out.push('<text x="' + (W - 2) + '" y="' + (y(line) - 4) + '" text-anchor="end" class="lbl">LINE ' + line + "</text></svg>");
  return out.join("");
}
function pct(a, n) { return n ? Math.round(100 * a / n) + "%" : "—"; }
function renderDetail() {
  var p = D.props.find(function (x) { return x.id === OPEN; });
  var box = $("#dlgbody");
  if (!p) { box.innerHTML = '<div class="empty"><b>This prop is no longer posted.</b></div>'; return; }
  var g = gameOf(p.gid), line = DST.line, logs = logsOf(p), season = D.season;
  var lines = allLines(p);
  var win = windowed(logs, DST.win, season);
  var s = hitSummary(win.map(function (l) { return statValue(l, p.market); }), line);
  var inj = D.injuries[g.date + "|" + p.pid] || {};
  var wins = [["l5", "L5"], ["l10", "L10"], ["l20", "L20"], ["season", "This season"], ["last", "Last season"], ["all", "All"]];
  var html = [];
  html.push('<div class="dh"><div class="av">' + head(p.pid) + logo(p.team) + '</div><div><h2 id="dlgt">' + esc(p.player) + " · " + esc(label(p.market)) + "</h2>" +
    '<div class="mu">' + esc(p.team || "") + " " + (p.team ? (p.home ? "vs " : "@ ") + esc(p.opp) : esc(g.away + " @ " + g.home)) + " · " + (g.state === "pregame" ? mt(g.tip, true) : esc(g.label || g.state)) + " " + injuryTag(p) + "</div></div>" +
    '<button class="x" aria-label="Close">×</button></div>');
  html.push('<div class="sec"><h3>Line</h3><div class="row" role="group" aria-label="Line">' + lines.map(function (l) {
    return '<button class="chip" data-line="' + l + '" aria-pressed="' + (l === line) + '">' + l + (l === p.main ? " · main" : "") + "</button>"; }).join("") +
    '<button class="chip" data-step="-0.5" aria-label="Line minus 0.5">−0.5</button><button class="chip" data-step="0.5" aria-label="Line plus 0.5">+0.5</button></div></div>');
  html.push('<div class="sec"><h3>Games</h3><div class="row" role="group" aria-label="Window">' + wins.map(function (w) {
    var nn = windowed(logs, w[0], season).length;
    return '<button class="chip" data-win="' + w[0] + '" aria-pressed="' + (w[0] === DST.win) + '"' + (nn ? "" : " disabled") + ">" + w[1] + " · " + nn + "</button>"; }).join("") + "</div></div>");
  html.push('<div class="sec card"><div class="kv">' +
    "<div><b>" + s.over + "/" + s.n + "</b><span>Over " + line + " · " + pct(s.over, s.n) + "</span></div>" +
    "<div><b>" + s.under + "/" + s.n + "</b><span>Under · " + pct(s.under, s.n) + "</span></div>" +
    "<div><b>" + s.push + "</b><span>Push</span></div>" +
    "<div><b>" + (s.avg === null ? "—" : s.avg) + "</b><span>Average</span></div>" +
    "<div><b>" + (s.med === null ? "—" : s.med) + "</b><span>Median</span></div></div>" +
    (s.n && s.n < 5 ? '<div class="note warn">Small sample: ' + s.n + " game" + (s.n === 1 ? "" : "s") + ".</div>" : "") +
    '<div class="note">Historical results only, all teams, ' + (DST.win === "all" ? "this season and last" : wins.find(function (w) { return w[0] === DST.win; })[1]) + ". Not a forecast.</div></div>");
  var cw = Math.max(300, (box.clientWidth || 360) - 56);
  html.push('<div class="sec card">' + chart(win, p.market, line, cw) + '<div class="note">Solid bar = over the line · striped = under · outlined = push. Oldest game on the left.</div></div>');
  if (p.live && g.state !== "pregame") {
    var lv = p.live.value, res = lv > line ? "over" : lv < line ? "under" : "at";
    html.push('<div class="sec card" role="status" aria-live="polite"><div class="live"><span class="tag ' + (g.state === "live" ? "t-l" : "t-n") + '">' + (g.state === "live" ? "LIVE" : "FINAL") + "</span>" +
      esc(lv + " " + label(p.market) + " in " + p.live.min + " min · " + res + " " + line) + "</div><div class=\"note\">" + esc(g.label || "") + (g.score ? " · " + g.away + " " + g.score[0] + ", " + g.home + " " + g.score[1] : "") + " · box score " + ago(g.updated) + "</div></div>");
  } else if (g.state === "live" || g.state === "final") {
    html.push('<div class="sec card"><div class="note">' + (g.error ? esc(g.error) : "No box-score line for this player yet.") + "</div></div>");
  }
  // books
  var brows = ["fd", "dk"].map(function (b) {
    var q = p.books[b], name = b === "fd" ? "FanDuel" : "DraftKings";
    if (!q) return "<tr><td>" + name + '</td><td colspan="4">No quote for this prop</td></tr>';
    var at = rungAt(q, line), mr = q.main === null ? null : rungAt(q, q.main);
    var bstale = D.sources.books[b] && D.sources.books[b].stale ? ' <span class="tag t-q">STALE</span>' : "";
    var r1 = "<tr><td>" + name + bstale + "</td><td class=\"r\">" + (mr ? mr[0] + " (main)" : "—") + '</td><td class="r">' + (mr ? american(mr[1]) : "—") + '</td><td class="r">' + (mr ? american(mr[2]) : "—") + "</td><td>" + mt(q.updated) + "</td></tr>";
    var r2 = mr && mr[0] === line ? "" : "<tr><td>" + name + " at " + line + '</td><td class="r">' + line + '</td><td class="r">' + (at ? american(at[1]) : "not offered") + '</td><td class="r">' + (at && at[2] ? american(at[2]) : at ? "over only" : "—") + "</td><td></td></tr>";
    return r1 + r2;
  }).join("");
  html.push('<div class="sec"><h3>Sportsbooks</h3><div class="card scroll"><table><thead><tr><th>Book</th><th class="r">Line</th><th class="r">Over</th><th class="r">Under</th><th>Updated</th></tr></thead><tbody>' + brows +
    "</tbody></table>" + (p.open ? '<div class="note">FanDuel opened this prop at ' + p.open[0] + " (" + american(p.open[1]) + ") " + mt(p.open[2], true) + ".</div>" : "") +
    '<div class="note">A different line is a different bet; compare prices only at the same line. "Not offered" means the book has no quote at that line.</div></div></div>');
  // splits
  var opt = {opp: p.opp, without: ((D.absences[g.date + "|" + p.team]) || []).map(function (a) { return {name: a.name || "absent teammate", played: a.played, since: a.since, team: p.team}; })};
  var srows = splitRows(logs, p.market, line, opt).map(function (r) {
    return "<tr><td>" + esc(r.label) + (r.s.n && r.s.n < 5 ? ' <span class="tag t-q">SMALL</span>' : "") + '</td><td class="r">' + r.s.n + '</td><td class="r">' + r.s.over + '</td><td class="r">' + r.s.under + '</td><td class="r">' + r.s.push + '</td><td class="r">' + (r.s.avg === null ? "—" : r.s.avg) + "</td></tr>"; }).join("");
  html.push('<div class="sec"><h3>Splits · this season and last · at ' + line + '</h3><div class="card scroll"><table><thead><tr><th>Split</th><th class="r">Games</th><th class="r">Over</th><th class="r">Under</th><th class="r">Push</th><th class="r">Avg</th></tr></thead><tbody>' + srows + "</tbody></table>" +
    (opt.without.length ? '<div class="note">"Without" = games for this team, this season or last, since that teammate\'s first game for it, that he did not play. ' + esc(opt.without.map(function (w) { return w.name; }).join(", ")) + (opt.without.length > 1 ? " are" : " is") + " Out or Doubtful on tonight's official report.</div>" : "") + "</div></div>");
  // context
  var c = p.ctx || {}, ctx = [];
  if (c.pace !== null && c.pace !== undefined && c.opp_games) {
    var pp = Math.round((c.pace - 1) * 100);
    ctx.push("<tr><td>Opponent pace</td><td>" + esc(p.opp) + (pp === 0 ? " plays at about the league's pace" : " averages " + Math.abs(pp) + "% " + (pp > 0 ? "more" : "fewer") + " possessions than the league") + " (" + c.opp_games + " game" + (c.opp_games === 1 ? "" : "s") + ", shrunk toward average)</td></tr>");
    var dd = c.def === null || c.def === undefined ? null : Math.round((c.def - 1) * 100);
    ctx.push("<tr><td>Defense vs " + (c.group === "G" ? "guards" : c.group === "F" ? "forwards" : c.group === "C" ? "centers" : "position") + "</td><td>" + (dd === null ? (p.market === "threes" ? "Not computed for threes." : "Position unknown.") : esc(p.opp) + (dd === 0 ? " allows about the league average " + esc(label(p.market)) + " per possession" : " allows " + Math.abs(dd) + "% " + (dd > 0 ? "more" : "less") + " " + esc(label(p.market)) + " per possession than the league")) + "</td></tr>");
  } else ctx.push('<tr><td>Matchup</td><td>Unavailable: no games for ' + esc(p.opp || "the opponent") + " this season yet.</td></tr>");
  if (g.lines) ctx.push("<tr><td>Game lines</td><td>" + (g.lines.total ? "Total " + g.lines.total : "") + (g.lines.spread_home !== undefined ? " · " + esc(g.home) + " " + (g.lines.spread_home > 0 ? "+" : "") + g.lines.spread_home : "") + " (FanDuel, " + mt(g.lines.updated) + ")</td></tr>");
  else ctx.push("<tr><td>Game lines</td><td>Unavailable</td></tr>");
  var l10g = logs.slice(-10), st10 = l10g.filter(function (l) { return l.starter === 1; }).length;
  if (l10g.length) {
    var m5 = logs.slice(-5), seasonLogs = windowed(logs, "season", season);
    var avgm = function (a) { return a.length ? Math.round(a.reduce(function (t, l) { return t + l.min; }, 0) / a.length * 10) / 10 : null; };
    ctx.push("<tr><td>Role</td><td>Started " + st10 + " of last " + l10g.length + " · " + avgm(m5) + " min last 5" + (seasonLogs.length ? " · " + avgm(seasonLogs) + " min this season" : "") + "</td></tr>");
  }
  html.push('<div class="sec"><h3>Matchup and role</h3><div class="card scroll"><table><tbody>' + ctx.join("") + "</tbody></table>" +
    '<div class="note">Season-to-date box scores (nba_matchup), games before tonight only. The market prices most of this already.</div></div></div>');
  // availability
  var av = [];
  var rep = D.sources.report[g.date];
  if (inj.official) av.push("<tr><td>Official report</td><td><b>" + esc(inj.official.status) + "</b>" + (inj.official.reason ? " · " + esc(inj.official.reason) : "") + " · " + mt(inj.official.published, true) + "</td></tr>");
  else if (rep) av.push("<tr><td>Official report</td><td>" + (inj.listed_team ? "Not listed (report " + mt(rep.published, true) + ")" : esc(p.team || "Team") + " not on the latest report yet (" + mt(rep.published, true) + ")") + "</td></tr>");
  else av.push("<tr><td>Official report</td><td>No official report for this date yet.</td></tr>");
  (inj.news || []).forEach(function (n) { av.push("<tr><td>News · " + esc(n.source) + "</td><td>" + esc(n.status || "") + " · " + mt(n.detected, true) + (n.headline ? " · " + esc(n.headline) : "") + "</td></tr>"); });
  var outs = (D.absences[g.date + "|" + p.team] || []).map(function (a) { return esc(a.name || "") + " (" + esc(a.status) + ")"; });
  if (outs.length) av.push("<tr><td>Teammates out</td><td>" + outs.join(", ") + "</td></tr>");
  html.push('<div class="sec"><h3>Availability</h3><div class="card scroll"><table><tbody>' + av.join("") + "</tbody></table>" +
    '<div class="note">Official = the league\'s injury report. News items are third-party posts the engine stored, not official.</div></div></div>');
  // related
  var rel = (D.related[p.id] || []).map(function (r) {
    var o = D.props.find(function (x) { return x.id === r.id; });
    if (!o) return "";
    return '<button data-rel="' + esc(o.id) + '"><span>' + esc(o.player + " " + label(o.market) + " " + (o.main === null ? "" : o.main)) + "</span><span>r " + (r.r > 0 ? "+" : "") + r.r + " · " + r.n + " games</span></button>";
  }).join("");
  html.push('<div class="sec"><h3>Related props tonight</h3><div class="card">' + (rel ? '<div class="rel">' + rel + '</div><div class="note">Historical association (Pearson r) between this stat and that one, over games both players played for this team, this season and last. A description of the past, not a prediction.</div>' : '<div class="note">No other prop in this game has 15+ shared games to compare.</div>') + "</div></div>");
  if (p.flag) html.push('<div class="sec"><h3>Engine</h3><div class="card"><span class="tag t-f">SHADOW · NOT A BET</span> The engine flagged ' + esc(p.flag.tier) + " at " + p.flag.line + " · " + (p.flag.card === 1 ? "on the card" : "logged only" + (p.flag.why ? " (" + esc(p.flag.why) + ")" : "")) + ".</div></div>");
  // log
  var rows = win.slice().reverse().map(function (l) {
    var v = statValue(l, p.market), r = v === null ? "–" : v > line ? '<span class="ov">O</span>' : v < line ? '<span class="un">U</span>' : '<span class="pu">P</span>';
    return "<tr><td>" + esc(l.date.slice(5)) + (l.team !== p.team ? " · " + esc(l.team) : "") + "</td><td>" + (l.home ? "vs " : "@ ") + esc(l.opp) + "</td><td>" + (l.starter ? "Start" : "Bench") + '</td><td class="r">' + l.min + '</td><td class="r">' + (v === null ? "–" : v) + '</td><td class="r">' + r + "</td></tr>"; }).join("");
  html.push('<div class="sec"><h3>Game log</h3><div class="card scroll"><table><thead><tr><th>Date</th><th>Opp</th><th>Role</th><th class="r">Min</th><th class="r">' + esc(label(p.market)) + '</th><th class="r">vs ' + line + "</th></tr></thead><tbody>" + (rows || '<tr><td colspan="6">No games logged.</td></tr>') + "</tbody></table></div></div>");
  box.innerHTML = html.join("");
  $("#dlg .x").onclick = closeProp;
  box.querySelectorAll("[data-line]").forEach(function (b) { b.onclick = function () { DST.line = +b.dataset.line; renderDetail(); box.querySelector('[data-line="' + DST.line + '"]').focus(); }; });
  box.querySelectorAll("[data-step]").forEach(function (b) { b.onclick = function () { DST.line = Math.max(0.5, Math.round((DST.line + +b.dataset.step) * 2) / 2); renderDetail(); box.querySelector('[data-step="' + b.dataset.step + '"]').focus(); }; });
  box.querySelectorAll("[data-win]").forEach(function (b) { b.onclick = function () { DST.win = b.dataset.win; renderDetail(); box.querySelector('[data-win="' + DST.win + '"]').focus(); }; });
  box.querySelectorAll("[data-rel]").forEach(function (b) { b.onclick = function () { openProp(b.dataset.rel, LAST_FOCUS); }; });
}
function load() {
  LOADING = true; render();
  fetch("nba_props.json?t=" + Date.now(), {cache: "no-store"}).then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(function (j) {
    var first = !D; D = j; ERR = null; LOADING = false;
    render();
    if (OPEN) renderDetail();
    $("#live").textContent = "Prop feed updated " + ago(D.generated_at);
    if (first) { var pid = readHashOpen(); if (pid) openProp(pid); }
  }).catch(function (e) {
    LOADING = false; ERR = e.message || String(e);
    if (D) { $("#live").textContent = "Refresh failed: " + ERR; } else render();
  });
}
var HASH_OPEN = readHash();
function readHashOpen() { var x = HASH_OPEN; HASH_OPEN = null; return x; }
document.addEventListener("DOMContentLoaded", function () {
  $("#dlg").addEventListener("close", function () { if (OPEN) { OPEN = null; writeHash(); } });
  $("#dlg").addEventListener("click", function (e) { if (e.target === $("#dlg")) closeProp(); });
  load();
  TIMER = setInterval(load, 120000);
});
})();
"""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Pickz">
<title>Pickz · NBA Props</title>
<link rel="icon" href="icon-64.png">
<style>__CSS__</style>
</head>
<body>
<div class="wrap">
  <div class="top"><a class="back" href="index.html">‹ Pickz</a></div>
  <h1>NBA Props</h1>
  <main id="app" aria-live="off"></main>
  <div id="live" class="sr" role="status" aria-live="polite"></div>
</div>
<dialog id="dlg" aria-labelledby="dlgt"><div class="dl" id="dlgbody"></div></dialog>
<script>__CORE__</script>
<script>__APP__</script>
</body>
</html>
"""


def page():
    return (PAGE.replace("__CSS__", CSS).replace("__CORE__", JS_CORE)
            .replace("__APP__", JS_APP.replace("__TEAM_ID__", json.dumps(TEAM_ID))))
