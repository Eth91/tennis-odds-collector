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
svg.ch .dt{font-size:9px;letter-spacing:-.03em}
svg.ch .ll{fill:#000;font-size:11px;font-weight:800}
svg.ch g.br:focus{outline:none} svg.ch g.br:focus rect{stroke:var(--blue);stroke-width:2}
.fch{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.fch .pill{height:32px;background:var(--blue);font-size:13px}
.fch .pill b{background:#fff;color:var(--blue)}
.fch .x{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 10px 0 12px;border:0;border-radius:16px;
background:rgba(10,132,255,.2);color:#64b0ff;font-size:13px;font-weight:600}
.fch .x span{font-size:15px;opacity:.8}
.rg{margin:16px 0 0}
.rg-h{display:flex;justify-content:space-between;align-items:baseline;font-size:15px}
.rg-h b{font-variant-numeric:tabular-nums}
.dual{position:relative;height:36px;margin:2px 4px 0}
.dual .trk,.dual .fil{position:absolute;top:16px;height:4px;border-radius:2px}
.dual .trk{left:0;right:0;background:var(--g3)}
.dual .fil{background:var(--blue)}
.dual input{position:absolute;left:-14px;width:calc(100% + 28px);top:0;height:36px;margin:0;background:none;pointer-events:none;
-webkit-appearance:none;appearance:none}
.dual input::-webkit-slider-runnable-track{height:36px;background:none}
.dual input::-webkit-slider-thumb{pointer-events:auto;-webkit-appearance:none;width:28px;height:28px;margin-top:4px;border-radius:50%;
background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.45)}
.dual input::-moz-range-thumb{pointer-events:auto;width:28px;height:28px;border:0;border-radius:50%;background:#fff}
.sg{margin:16px 0 0}
.sg>span{display:block;margin:0 0 6px;font-size:15px}
.sg .seg{margin:0}
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
/* ── player page (prop-research layout) ── */
.ph{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px;padding:calc(var(--st) + 8px) 16px 8px;
background:linear-gradient(#000 70%,rgba(0,0,0,0))}
.cb{flex:none;display:inline-flex;align-items:center;justify-content:center;width:52px;height:52px;border-radius:50%;
border:1px solid #2c2c2e;background:rgba(28,28,30,.92);color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.5)}
.cb svg{width:24px;height:24px}
.cb.fav{color:var(--yel)} .cb.fav svg{fill:var(--yel)}
.ph-t{flex:1;min-width:0;text-align:center;line-height:1.2}
.ph-t b{display:block;font-size:17px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ph-t span{display:block;font-size:14px;color:var(--l2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mt{margin:4px 16px 0;border:1px solid #2c2c2e;border-radius:28px;background:#121214;overflow:hidden}
.mt-in{display:flex;gap:2px;overflow-x:auto;padding:5px;scrollbar-width:none}
.mt-in::-webkit-scrollbar{display:none}
.mt button{flex:none;height:44px;padding:0 18px;border:0;border-radius:22px;background:none;color:var(--l2);font-size:17px;font-weight:500}
.mt button[aria-pressed="true"]{background:#2c2c2e;color:#fff}
.hro{position:relative;display:flex;min-height:230px;margin-top:14px;padding:0 16px;border-bottom:1px solid #2c2c2e;overflow:hidden}
.hro-l{position:relative;z-index:1;padding-top:8px;max-width:58%}
.hro-l h2{margin:0 0 6px;font-size:32px;font-weight:700;letter-spacing:-.01em;line-height:1.1}
.hro-s{font-size:18px;color:var(--l2);line-height:1.45}
.tlg{display:flex;align-items:center;justify-content:center;width:68px;height:68px;margin:22px 0 18px;border-radius:50%}
.tlg img{width:48px;height:48px}
.hro-i{position:absolute;right:-24px;bottom:0;height:226px;width:auto;object-fit:contain;object-position:bottom}
.sg2{display:flex;align-items:center;gap:8px;padding:16px 16px 6px}
.cells{flex:1;min-width:0;display:grid;grid-template-columns:auto auto minmax(0,1fr);gap:16px 12px}
.cells>div,.cells>button{min-width:0;padding:0;border:0;background:none;text-align:left}
.cells i{display:block;font-style:normal;font-size:13px;color:var(--l2);letter-spacing:-.02em;white-space:nowrap}
.cells b{display:flex;align-items:center;gap:3px;margin-top:4px;font-size:17px;font-weight:500;letter-spacing:-.03em;
white-space:nowrap;font-variant-numeric:tabular-nums}
.cv{margin-left:4px;color:var(--l2);font-size:20px;font-weight:300}
.tri{font-size:13px} .tri.up{color:#2ed68f} .tri.dn{color:#ff2d2d}
.muc{flex:none;display:flex;flex-direction:column;align-items:center;width:92px;padding:8px 0 10px;border:1px solid #2c2c2e;
border-radius:14px;background:#121214;color:#fff;font-size:16px}
.c2w{margin:14px 0 0;padding:0 16px;overflow-x:auto;scrollbar-width:none}
.c2w::-webkit-scrollbar{display:none}
svg.c2{display:block}
svg.c2 text{font-family:inherit}
svg.c2 .ax{fill:var(--l2);font-size:15px}
svg.c2 .lx{fill:#fff;font-size:15px}
svg.c2 .mn{fill:#fff;font-size:12.5px;font-weight:600;letter-spacing:-.03em}
svg.c2 .vv{fill:#111;font-size:13px;font-weight:600}
svg.c2 .vw{fill:#fff;font-size:13px;font-weight:600}
svg.c2 .xl{fill:var(--l2);font-size:11px;letter-spacing:-.02em}
svg.c2 g.br:focus{outline:none} svg.c2 g.br:focus rect{stroke:var(--blue);stroke-width:2.5}
.wrow{display:flex;align-items:center;gap:10px;margin:18px 16px 0}
.wcap{flex:1;display:flex;padding:6px;border:1px solid #2c2c2e;border-radius:34px;background:#121214;overflow-x:auto;scrollbar-width:none}
.wcap::-webkit-scrollbar{display:none}
.wc{flex:1;min-width:58px;padding:7px 4px 6px;border:0;border-radius:26px;background:none;text-align:center}
.wc i{display:block;font-style:normal;font-size:14px;color:#fff}
.wc b{display:block;font-size:18px;font-weight:600}
.wc b.up{color:#2ed68f} .wc b.dn{color:#ff2d2d}
.wc[aria-pressed="true"]{background:#2c2c2e}
.wc:disabled{opacity:.35}
.fb{width:60px;height:60px}
.cf{margin:22px 16px 0}
.cf-h{display:flex;align-items:center;gap:14px}
.cf-h h3,.sec2 h3{margin:0;font-size:22px;font-weight:600}
.ca{height:34px;padding:0 14px;border:1px solid #3a3a3c;border-radius:17px;background:#121214;font-size:14px}
.fcs{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.fc{display:inline-flex;align-items:center;gap:8px;height:46px;padding:0 18px;border:1px solid #3a3a3c;border-radius:23px;
background:#121214;font-size:17px;color:#fff}
.fc svg{width:20px;height:16px}
.fc em{font-style:normal;font-weight:600} .fc em.good{color:#2ed68f} .fc em.bad{color:#ff2d2d} .fc em.mid{color:var(--yel)}
.fc.on{border-color:#fff;background:#2c2c2e}
.rp{margin:18px 0 0}
.rp-h{display:flex;justify-content:space-between;align-items:baseline;font-size:20px;font-weight:500}
.rp-h b{font-size:16px;font-weight:600;color:var(--l2);font-variant-numeric:tabular-nums}
.dual2{position:relative;height:56px;margin-top:12px;border:1px solid #2c2c2e;border-radius:28px;background:#121214}
.dual2 .trk{position:absolute;left:12px;right:12px;top:13px;height:28px;border-radius:14px;background:#1c1c1e}
.dual2 .fil{position:absolute;top:13px;height:28px;border-radius:14px;background:#3a3a3c}
.dual2 input{position:absolute;left:0;width:100%;top:0;height:56px;margin:0;background:none;pointer-events:none;
-webkit-appearance:none;appearance:none}
.dual2 input::-webkit-slider-runnable-track{height:56px;background:none}
.dual2 input::-webkit-slider-thumb{pointer-events:auto;-webkit-appearance:none;width:30px;height:30px;margin-top:13px;border-radius:50%;
background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.5)}
.dual2 input::-moz-range-thumb{pointer-events:auto;width:30px;height:30px;border:0;border-radius:50%;background:#fff}
.rp-b{display:flex;justify-content:space-between;margin:8px 8px 0;font-size:20px;font-variant-numeric:tabular-nums}
.sec2{margin:28px 16px 0}
.sec2 h3{margin-bottom:12px}
.box0{padding:14px;border:1px solid #2c2c2e;border-radius:16px;background:#121214}
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
// player-page filters: home / starter = true, false or null (any); result = "W" / "L"; rest = "b2b" / "1" / "2+";
// oppSets = [{season: [teams]}] (the opponent must be in each);
// ranges = {min|fga|fg3a|fta|margin: [lo, hi]} inclusive (a game missing that stat is out); without = [{played, since, team}]
function filterLogs(logs, f) {
  f = f || {};
  return logs.filter(function (l) {
    if (f.home === true && l.home !== 1) return false;
    if (f.home === false && l.home !== 0) return false;
    if (f.starter === true && l.starter !== 1) return false;
    if (f.starter === false && l.starter !== 0) return false;
    if (f.result === "W" && !(l.margin > 0)) return false;
    if (f.result === "L" && !(l.margin < 0)) return false;
    if (f.rest === "b2b" && l.rest !== 0) return false;
    if (f.rest === "1" && l.rest !== 1) return false;
    if (f.rest === "2+" && !(l.rest >= 2)) return false;
    for (var j = 0; j < (f.oppSets || []).length; j++) {       // {season: [opponents]}: the tier chips
      var ss = f.oppSets[j][seasonOf(l.date)];
      if (!ss || ss.indexOf(l.opp) < 0) return false;
    }
    for (var k in (f.ranges || {})) {
      var v = l[k], r = f.ranges[k];
      if (v === null || v === undefined || v < r[0] || v > r[1]) return false;
    }
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
const DT = {line: null, win: "l10", home: null, starter: null, result: null, rest: null, ranges: {}, without: {},
            dvp: false, def: false, open: {}};
const RANGES = [["min", "Minutes", "Min"], ["fga", "Field goal attempts", "FGA"], ["fg3a", "3-point attempts", "3PA"],
                ["fta", "Free throw attempts", "FTA"], ["margin", "Team margin", "Margin"]];
const SEGS = [["home", "Location", [[null, "Any"], [true, "Home"], [false, "Away"]]],
              ["starter", "Role", [[null, "Any"], [true, "Starter"], [false, "Bench"]]],
              ["result", "Result", [[null, "Any"], ["W", "Win"], ["L", "Loss"]]],
              ["rest", "Rest", [[null, "Any"], ["b2b", "B2B"], ["1", "1 day"], ["2+", "2+ days"]]]];
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
  if (fresh) Object.assign(DT, {line: p.main !== null ? p.main : allLines(p)[0], win: "l10", home: null, starter: null,
                                 result: null, rest: null, ranges: {}, without: {}, dvp: false, def: false, open: {}});
  if (push !== false) history.pushState({p: id}, "", hashState());
  renderProp();
  const pg = $("#pg");
  pg.hidden = false;
  document.body.classList.add("lock");
  requestAnimationFrame(() => pg.classList.add("on"));
  if (fresh) pg.scrollTop = 0;
  // move focus into the page for keyboard and screen-reader users; on a touchscreen it only draws a ring
  if (!matchMedia("(pointer: coarse)").matches) setTimeout(() => { const b = $("#pg .bk"); if (b) b.focus({preventScroll: true}); }, 50);
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
  const bw = Math.max(28, Math.min(44, avail / n)), gap = Math.round(bw * .22);
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
      `<text x="${x + w / 2}" y="${bot + 15}" text-anchor="middle">${esc(l.opp)}</text><text class="dt" x="${x + w / 2}" y="${bot + 28}" text-anchor="middle">${d}</text></g>`);
  });
  const ly = y(line);
  out.push(`<line x1="0" x2="${W}" y1="${ly}" y2="${ly}" stroke="#fff" stroke-width="1.5" stroke-dasharray="6 5" opacity=".9"/>`);
  out.push(`<rect x="${W - 46}" y="${ly - 9}" width="44" height="18" rx="9" fill="#fff"/><text class="ll" x="${W - 24}" y="${ly + 4}" text-anchor="middle">${line}</text></svg>`);
  return out.join("");
}
const TEAMS = {ATL: ["Atlanta Hawks", "#C8102E"], BOS: ["Boston Celtics", "#007A33"], BKN: ["Brooklyn Nets", "#2a2a2a"],
  CHA: ["Charlotte Hornets", "#00788C"], CHI: ["Chicago Bulls", "#CE1141"], CLE: ["Cleveland Cavaliers", "#860038"],
  DAL: ["Dallas Mavericks", "#00538C"], DEN: ["Denver Nuggets", "#0E2240"], DET: ["Detroit Pistons", "#C8102E"],
  GSW: ["Golden State Warriors", "#1D428A"], HOU: ["Houston Rockets", "#CE1141"], IND: ["Indiana Pacers", "#002D62"],
  LAC: ["LA Clippers", "#1D428A"], LAL: ["Los Angeles Lakers", "#552583"], MEM: ["Memphis Grizzlies", "#5D76A9"],
  MIA: ["Miami Heat", "#98002E"], MIL: ["Milwaukee Bucks", "#00471B"], MIN: ["Minnesota Timberwolves", "#0C2340"],
  NOP: ["New Orleans Pelicans", "#0C2340"], NYK: ["New York Knicks", "#006BB6"], OKC: ["Oklahoma City Thunder", "#007AC1"],
  ORL: ["Orlando Magic", "#0077C0"], PHI: ["Philadelphia 76ers", "#006BB6"], PHX: ["Phoenix Suns", "#1D1160"],
  POR: ["Portland Trail Blazers", "#E03A3E"], SAC: ["Sacramento Kings", "#5A2D81"], SAS: ["San Antonio Spurs", "#2b2b2b"],
  TOR: ["Toronto Raptors", "#CE1141"], UTA: ["Utah Jazz", "#4B2C82"], WAS: ["Washington Wizards", "#002B5C"]};
const POSN = {PG: "Point Guard", SG: "Shooting Guard", SF: "Small Forward", PF: "Power Forward", C: "Center", G: "Guard",
  F: "Forward", "G-F": "Guard-Forward", "F-G": "Forward-Guard", "F-C": "Forward-Center", "C-F": "Center-Forward"};
const TAB_ORDER = ["points", "assists", "rebounds", "threes", "pts_ast", "pts_reb", "reb_ast", "pra"];
const TAB = {points: "Points", rebounds: "Rebs", assists: "Assists", threes: "3PTM", pra: "PRA", pts_reb: "P+R", pts_ast: "P+A", reb_ast: "R+A"};
const GRPN = {G: "guards", F: "forwards", C: "centers"};
const ICON = {
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>',
  share: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M21 3 3 10.5l7 2.5 2.5 7L21 3Z"/><path d="m10 13 4.5-4.5"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z"/></svg>',
  bars: '<svg viewBox="0 0 20 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M2 14h16M5 11V7M9 11V3M13 11V6M17 11V9"/></svg>',
  menu: '<svg viewBox="0 0 22 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M2 3h18M5 8h12M8 13h6"/></svg>'};
const favs = () => { try { return JSON.parse(localStorage.getItem("pickz_fav") || "[]"); } catch (e) { return []; } };
function toggleFav(pid) {
  try { const f = favs(), i = f.indexOf(pid); if (i >= 0) f.splice(i, 1); else f.push(pid); localStorage.setItem("pickz_fav", JSON.stringify(f)); } catch (e) {}
}
// tier of a rank among n teams: thirds (1 = the toughest defense)
const tierOf = (r, n) => !r || !n ? null : r <= Math.ceil(n / 3) ? "tough" : r > n - Math.ceil(n / 3) ? "soft" : "mid";
function rankCls(r, n, side) {
  const t = tierOf(r, n);
  if (!t || t === "mid") return "mid";
  return (t === "soft") === (side !== "under") ? "good" : "bad";
}
function oppSet(table, tier, n) {
  const out = [];
  Object.keys(table || {}).forEach(t => { if (tierOf(table[t], n) === tier) out.push(t); });
  return out;
}
function grade(p, side) {
  const c = p.ctx || {}, r = c.dvp_rank || c.def_rank, n = c.teams;
  if (!r || !n || n < 2) return null;
  let q = (r - 1) / (n - 1);                       // 0 = the toughest, 1 = the softest
  if (side === "under") q = 1 - q;
  return {q: q, g: q >= .8 ? "A" : q >= .6 ? "B" : q >= .4 ? "C" : q >= .2 ? "D" : "F"};
}
function gauge(gr) {
  const R = 30, C = 2 * Math.PI * R, arc = C * .75, col = !gr ? "#48484a" : gr.q >= .6 ? "#2ed68f" : gr.q >= .4 ? "#ffd60a" : "#ff3b30";
  const fill = gr ? arc * Math.max(.06, gr.q) : 0;
  return `<svg viewBox="0 0 80 80" width="74" height="74" aria-hidden="true"><g transform="rotate(135 40 40)">` +
    `<circle cx="40" cy="40" r="${R}" fill="none" stroke="#2c2c2e" stroke-width="7" stroke-linecap="round" stroke-dasharray="${arc} ${C}"/>` +
    `<circle cx="40" cy="40" r="${R}" fill="none" stroke="${col}" stroke-width="7" stroke-linecap="round" stroke-dasharray="${fill} ${C}"/></g>` +
    `<text x="40" y="49" text-anchor="middle" font-size="26" font-weight="700" fill="${col}">${gr ? gr.g : "–"}</text></svg>`;
}
function chart2(logs, market, line) {
  const n = logs.length;
  if (!n) return '<div class="empty" style="padding:40px 0"><b>No games</b>Nothing matches this window and these filters.</div>';
  const vals = logs.map(l => statValue(l, market)), mins = logs.map(l => l.min);
  const top = Math.max(line, ...vals.filter(v => v !== null), ...mins.filter(v => v !== null), 1);
  const W0 = Math.min(window.innerWidth, 520) - 32, AX = 40;          // ten games fit an iPhone's width
  const slot = Math.max(30, (W0 - AX) / n), W = Math.max(W0, AX + n * slot), H = 390, T = 12, B = 324;
  const y = v => B - v / (top * 1.04) * (B - T);
  const o = [`<svg class="c2" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(NAME[market])} and minutes by game, ${n} games, line ${line}">`];
  o.push(`<text class="ax" x="0" y="${y(top) + 6}">${Math.round(top * 10) / 10}</text><text class="ax" x="0" y="${B}">0</text>`);
  logs.forEach((l, i) => {
    const v = vals[i], m = l.min, x = AX + i * slot + 3, w = slot - 6, cx = x + w / 2;
    const res = v === null ? "none" : v > line ? "over" : v < line ? "under" : "push";
    const fill = res === "over" ? "#2ed68f" : res === "under" ? "#ff2d2d" : "#8e8e93";
    const d = iso(l.date + "T12:00:00Z").toLocaleDateString("en-US", {month: "numeric", day: "numeric", timeZone: "UTC"});
    const desc = `${d} ${l.home ? "vs" : "at"} ${l.opp}: ${v === null ? "no value" : v} ${short(market)} in ${m} minutes, ${res} ${line}`;
    let g = `<g class="br" tabindex="0" role="img" aria-label="${esc(desc)}"><title>${esc(desc)}</title>`;
    if (v !== null && v > 0) g += `<rect x="${x}" y="${y(v)}" width="${w}" height="${B - y(v)}" fill="${fill}"/>`;
    if (m) g += `<rect x="${x}" y="${y(m)}" width="${w}" height="${B - y(m)}" fill="none" stroke="#e5e5ea" stroke-width="1.6"/>` +
      `<text class="mn" x="${cx}" y="${y(m) + 18}" text-anchor="middle">${Math.round(m * 10) / 10}</text>`;
    if (v !== null) g += B - y(v) >= 22 ? `<text class="vv" x="${cx}" y="${B - 7}" text-anchor="middle">${v}</text>`
      : `<text class="vw" x="${cx}" y="${y(v) - 6}" text-anchor="middle">${v}</text>`;
    g += `<text class="xl" x="${cx}" y="${B + 22}" text-anchor="middle">${d}</text><text class="xl" x="${cx}" y="${B + 42}" text-anchor="middle">${l.home ? "" : "@"}${esc(l.opp)}</text></g>`;
    o.push(g);
  });
  o.push(`<line x1="${AX - 2}" x2="${W}" y1="${y(line)}" y2="${y(line)}" stroke="#fff" stroke-width="1.6"/>`);
  o.push(`<text class="lx" x="0" y="${y(line) - 6}">${line}</text></svg>`);
  return o.join("");
}
function renderProp() {
  const p = D.props.find(x => x.id === CUR), pg = $("#pg");
  if (!p) { pg.innerHTML = `<div class="ph"><button class="cb bk" aria-label="Back">${ICON.back}</button></div><div class="empty"><b>No longer posted</b>The books have taken this prop down.</div>`; $("#pg .bk").onclick = () => history.back(); return; }
  const g = gameOf(p.gid), line = DT.line, side = ST.side, logs = logsOf(p), c = p.ctx || {};
  const team = TEAMS[p.team] || [p.team || "", "#333"];
  const without = (D.absences[g.date + "|" + p.team] || []).map(a => ({key: String(a.pid), name: a.name || "teammate", played: a.played, since: a.since, team: p.team, status: a.status}));
  const prevS = (+D.season.slice(0, 4) - 1) + "-" + D.season.slice(2, 4);
  const rkCur = (D.ranks || {})[g.date] || {}, rkPrev = (D.ranks || {})[prevS] || {};
  const dvpT = c.group && rkCur.dvp ? tierOf(c.dvp_rank, c.teams) : null, defT = tierOf(c.def_rank, c.teams);
  const oppSets = [];
  if (DT.dvp && dvpT) { const s = {}; s[D.season] = oppSet(rkCur.dvp[c.group][p.market], dvpT, rkCur.teams);
    if (rkPrev.dvp && rkPrev.teams) s[prevS] = oppSet(rkPrev.dvp[c.group][p.market], dvpT, rkPrev.teams); oppSets.push(s); }
  if (DT.def && defT) { const s = {}; s[D.season] = oppSet(rkCur.def, defT, rkCur.teams);
    if (rkPrev.def && rkPrev.teams) s[prevS] = oppSet(rkPrev.def, defT, rkPrev.teams); oppSets.push(s); }
  const f = {home: DT.home, starter: DT.starter, result: DT.result, rest: DT.rest, ranges: DT.ranges, oppSets: oppSets,
             without: without.filter(w => DT.without[w.key])};
  const base = filterLogs(logs, f);
  const wins = [["season", D.season.slice(0, 4)], ["h2h", "H2H"], ["l5", "L5"], ["l10", "L10"], ["l20", "L20"]];
  const win = windowed(base, DT.win, D.season, p.opp);
  const s = hitSummary(win.map(l => statValue(l, p.market)), line);
  const rate = sideRate(s, side);
  const winLab = (wins.find(w => w[0] === DT.win) || ["", "L10"])[1];
  const tri = up => `<span class="tri ${up ? "up" : "dn"}">${up ? "▲" : "▼"}</span>`;
  const mkts = TAB_ORDER.filter(m => D.props.some(x => x.gid === p.gid && x.pid === p.pid && x.market === m));
  const fav = favs().indexOf(p.pid) >= 0;
  const gr = grade(p, side);
  const opp = `${p.home ? "vs" : "@"} ${esc(p.opp || "")} · ${g.state === "pregame" ? mt(g.tip).replace(" ", "") : esc(g.state === "live" ? "LIVE" : g.state === "final" ? "Final" : g.label || "")}`;
  const capsule = wins.map(([k, lab]) => {
    const w = windowed(base, k, D.season, p.opp), ss = hitSummary(w.map(l => statValue(l, p.market)), line), r = sideRate(ss, side);
    return `<button class="wc" data-win="${k}" aria-pressed="${k === DT.win}"${w.length ? "" : " disabled"}><i>${lab}</i><b class="${r === null ? "" : r >= .5 ? "up" : "dn"}">${pct(r)}</b></button>`;
  }).join("");
  // chart filter chips
  const on = (k, v) => DT[k] === v;
  const chip = (attrs, lab, active) => `<button class="fc${active ? " on" : ""}" ${attrs} aria-pressed="${!!active}">${lab}</button>`;
  const rangeOn = k => !!DT.ranges[k];
  const chips = [];
  if (c.dvp_rank) chips.push(chip('data-t="dvp"', `DvP <em class="${rankCls(c.dvp_rank, c.teams, side)}">${ord(c.dvp_rank)}</em>`, DT.dvp));
  if (c.def_rank) chips.push(chip('data-t="def"', `Def Rank <em class="${rankCls(c.def_rank, c.teams, side)}">${ord(c.def_rank)}</em>`, DT.def));
  RANGES.forEach(([k, , abbr]) => { const b = bounds(logs, k); if (b && b[0] !== b[1]) chips.push(chip(`data-r="${k}"`, `${ICON.bars}${k === "min" ? "Minutes" : abbr}`, rangeOn(k) || DT.open[k])); });
  [["home", true, "Home"], ["home", false, "Away"], ["result", "W", "Win"], ["result", "L", "Loss"], ["rest", "b2b", "B2B"]].forEach(([k, v, lab]) =>
    chips.push(chip(`data-k="${k}" data-v="${v}"`, lab, on(k, v))));
  without.forEach(w => chips.push(chip(`data-wo="${w.key}"`, "Without " + esc(w.name.split(" ").slice(-1)[0]), DT.without[w.key])));
  const panels = RANGES.filter(([k]) => DT.open[k] || rangeOn(k)).map(([k, lab]) => {
    const b = bounds(logs, k); if (!b || b[0] === b[1]) return "";
    const cur = DT.ranges[k] || b;
    return `<div class="rp" data-rk="${k}" data-lo="${b[0]}" data-hi="${b[1]}"><div class="rp-h"><span>${k === "min" ? "Minutes" : lab}</span><b class="rv">${cur[0]} – ${cur[1]}</b></div>
      <div class="dual2"><div class="trk"></div><div class="fil"></div>
      <input type="range" class="a" min="${b[0]}" max="${b[1]}" step="1" value="${cur[0]}" aria-label="${lab} minimum">
      <input type="range" class="b" min="${b[0]}" max="${b[1]}" step="1" value="${cur[1]}" aria-label="${lab} maximum"></div>
      <div class="rp-b"><span>${b[0]}</span><span>${b[1]}</span></div></div>`;
  }).join("");
  const anyF = DT.dvp || DT.def || DT.home !== null || DT.starter !== null || DT.result !== null || DT.rest !== null || Object.keys(DT.ranges).length || Object.keys(DT.without).some(k => DT.without[k]);
  // odds
  const bestNow = bestPrice(p, line, "all", side);
  const bk = [["fd", "FanDuel", "book-fd.png"], ["dk", "DraftKings", "book-dk.png"]].map(([b, name, img]) => {
    const q = p.books[b];
    if (!q) return `<div class="bkr"><img src="${img}" alt=""><span>${name}</span><span class="od na" style="grid-column:span 2">no prop posted</span></div>`;
    const r = rungAt(q, line);
    const ov = r && r[1] ? `<span class="od${bestNow && bestNow.book === b && side === "over" ? " best" : ""}">O ${american(r[1])}</span>` : '<span class="od na">—</span>';
    const un = r && r[2] ? `<span class="od${bestNow && bestNow.book === b && side === "under" ? " best" : ""}">U ${american(r[2])}</span>` : '<span class="od na">—</span>';
    return `<div class="bkr"><img src="${img}" alt=""><span>${name}${D.sources.books[b] && D.sources.books[b].stale ? ' <span class="tg tq">STALE</span>' : ""}<br><span class="ln2">${q.main === line ? "main line" : r ? "alt line" : "main " + (q.main === null ? "—" : q.main)} · ${mt(q.updated)}</span></span>${r ? ov + un : `<span class="od na" style="grid-column:span 2">not at ${line}</span>`}</div>`;
  }).join("");
  // availability
  const inj = D.injuries[g.date + "|" + p.pid] || {}, rep = D.sources.report[g.date];
  const arows = [`<div class="kv"><span>Official report</span><b>${inj.official ? esc(inj.official.status) + (inj.official.reason ? " · " + esc(inj.official.reason.replace("Injury/Illness - ", "")) : "") : rep ? (inj.listed_team ? "Not listed" : "Team not listed yet") : "Not out yet"}</b></div>`];
  if (rep) arows.push(`<div class="kv"><span>Report time</span><b>${mt((inj.official || {}).published || rep.published, true)}</b></div>`);
  (inj.news || []).forEach(n => arows.push(`<div class="kv"><span>News · ${esc(n.source)}</span><b>${esc(n.headline || n.status || "")} · ${mt(n.detected)}</b></div>`));
  if (without.length) arows.push(`<div class="kv"><span>Teammates out</span><b>${without.map(w => esc(w.name) + " (" + esc(w.status) + ")").join(", ")}</b></div>`);
  const rel = (D.related[p.id] || []).map(r => {
    const o = D.props.find(x => x.id === r.id); if (!o) return "";
    return `<button class="rc" data-rel="${esc(o.id)}"><div class="nm">${esc(o.player.split(" ").slice(-1)[0])} ${esc(short(o.market))}</div><div class="sub">${o.main === null ? "alt lines" : "O/U " + o.main}</div><div class="rr">r ${r.r > 0 ? "+" : ""}${r.r} · ${r.n} games</div></button>`;
  }).join("");
  const live = p.live && g.state !== "pregame" ? `<div class="box" role="status"><div class="live"><span class="tg ${g.state === "live" ? "tl" : "tn"}">${g.state === "live" ? "LIVE" : "FINAL"}</span>${p.live.value} ${esc(short(p.market))} in ${p.live.min} min</div><div class="note">${esc(g.label || "")}${g.score ? " · " + esc(g.away) + " " + g.score[0] + " – " + esc(g.home) + " " + g.score[1] : ""} · box score ${ago(g.updated)}</div></div>` : "";
  const logRows = win.slice().reverse().map(l => {
    const v = statValue(l, p.market), r = v === null ? "–" : v > line ? '<span class="ov">O</span>' : v < line ? '<span class="un">U</span>' : '<span class="pu">P</span>';
    return `<tr><td>${esc(l.date.slice(5).replace("-", "/"))}</td><td>${l.home ? "" : "@"}${esc(l.opp)}${l.team !== p.team ? " <span style='color:var(--l3)'>(" + esc(l.team) + ")</span>" : ""}</td><td class="r">${l.min}</td><td class="r">${l.fga ?? "–"}</td><td class="r"><b>${v === null ? "–" : v}</b></td><td class="r">${r}</td></tr>`;
  }).join("");
  pg.innerHTML = `<div class="ph"><button class="cb bk" aria-label="Back">${ICON.back}</button>
      <div class="ph-t"><b>${esc(p.player)}</b><span>${esc(team[0])}</span></div>
      <button class="cb" id="shr" aria-label="Share">${ICON.share}</button><button class="cb${fav ? " fav" : ""}" id="fav" aria-label="Favorite" aria-pressed="${fav}">${ICON.star}</button></div>
    <nav class="mt" aria-label="Markets"><div class="mt-in">${mkts.map(m => `<button data-mk="${m}" aria-pressed="${m === p.market}">${TAB[m]}</button>`).join("")}</div></nav>
    <div class="hro"><div class="hro-l"><h2>${esc(p.player)}</h2><div class="hro-s">${esc(team[0])}</div><div class="hro-s">${esc(POSN[c.pos] || c.pos || "")}</div>
      <div class="tlg" style="background:${team[1]}">${logo(p.team, "")}</div></div>
      <img class="hro-i" alt="" src="https://cdn.nba.com/headshots/nba/latest/1040x760/${p.pid}.png" onerror="this.style.visibility='hidden'"></div>
    <div class="sg2"><div class="cells">
      <div><i>${esc(winLab)} AVG</i><b>${s.avg === null ? "–" : tri(s.avg > line) + s.avg}</b></div>
      <button id="lnb"><i>LINE</i><b>${line}<span class="cv">›</span></b></button>
      <div><i>PROP</i><b>${esc(NAME[p.market])}</b></div>
      <div><i>HIT RATE</i><b>${rate === null ? "–" : tri(rate >= .5) + Math.round(rate * 100) + "%"}</b></div>
      <button id="psb"><i>POS RANK</i><b>${c.pos_rank ? ord(c.pos_rank) : "–"}<span class="cv">›</span></b></button>
      <div><i>OPPONENT</i><b>${opp}</b></div></div>
      <button class="muc" id="mub">${gauge(gr)}<span>Matchup <span class="cv">›</span></span></button></div>
    ${live}
    <div class="c2w" id="chw">${chart2(win, p.market, line)}</div>
    <div class="wrow"><div class="wcap" role="group" aria-label="Games window">${capsule}</div><button class="cb fb" id="pf" aria-label="All filters">${ICON.menu}</button></div>
    <div class="note" style="margin:8px 16px 0">${side === "under" ? "Under" : "Over"} ${line} · ${s.n} game${s.n === 1 ? "" : "s"}${s.n && s.n < 5 ? " — small sample" : ""} · white box = minutes played, fill = ${esc(short(p.market))}</div>
    <div class="cf"><div class="cf-h"><h3>Chart Filters</h3>${anyF ? '<button class="ca" id="clr">Clear All</button>' : ""}</div>
      <div class="fcs">${chips.join("")}</div>${panels}</div>
    <div class="sec2"><h3>Odds</h3><div class="box0"><div class="bks" style="margin:0;border:0">${bk}</div>${p.open ? `<div class="note">FanDuel opened ${p.open[0]} (${american(p.open[1])}) ${mt(p.open[2], true)}.</div>` : ""}</div></div>
    <div class="sec2"><h3>Availability</h3><div class="box0">${arows.join("")}<div class="note">Official = the NBA injury report. News is third-party.</div></div></div>
    ${rel ? `<div class="sec2"><h3>Related Props</h3><div class="rel" style="margin:0;padding:0">${rel}</div><div class="note">How closely the two stats moved together in past games (r from −1 to +1). History, not a prediction.</div></div>` : ""}
    ${p.flag ? `<div class="sec2"><h3>Engine</h3><div class="box0"><span class="tg tf" style="margin:0 6px 0 0">SHADOW · NOT A BET</span>${esc(p.flag.tier)} at ${p.flag.line} · ${p.flag.card === 1 ? "on the card" : "logged only" + (p.flag.why ? " (" + esc(p.flag.why.toLowerCase()) + ")" : "")}</div></div>` : ""}
    <div class="sec2"><details class="log"><summary>Game Log · ${win.length}</summary><table><thead><tr><th>Date</th><th>Opp</th><th class="r">Min</th><th class="r">FGA</th><th class="r">${esc(short(p.market))}</th><th class="r">${line}</th></tr></thead><tbody>${logRows || '<tr><td colspan="6">No games.</td></tr>'}</tbody></table></details></div>
    <div class="end"></div>`;
  const cw = $("#chw"); if (cw) cw.scrollLeft = cw.scrollWidth;
  $("#pg .bk").onclick = () => history.back();
  const keep = sel => { const e = $(sel, pg); if (e) e.focus({preventScroll: true}); };
  $("#fav", pg).onclick = () => { toggleFav(p.pid); renderProp(); keep("#fav"); };
  $("#shr", pg).onclick = () => {
    const url = location.href, title = `${p.player} ${NAME[p.market]} ${line}`;
    if (navigator.share) navigator.share({title: title, url: url}).catch(() => {});
    else if (navigator.clipboard) navigator.clipboard.writeText(url).then(() => { $("#live").textContent = "Link copied"; });
  };
  $$("[data-win]", pg).forEach(b => b.onclick = () => { DT.win = b.dataset.win; renderProp(); keep(`[data-win="${DT.win}"]`); });
  $$("[data-mk]", pg).forEach(b => b.onclick = () => { const id = p.gid + "|" + p.pid + "|" + b.dataset.mk; if (id !== p.id) { openProp(id, false); history.replaceState({p: id}, "", hashState()); } });
  $$("[data-t]", pg).forEach(b => b.onclick = () => { const k = b.dataset.t; DT[k] = !DT[k]; renderProp(); keep(`[data-t="${k}"]`); });
  $$("[data-r]", pg).forEach(b => b.onclick = () => { const k = b.dataset.r; if (DT.ranges[k]) { delete DT.ranges[k]; DT.open[k] = false; } else DT.open[k] = !DT.open[k]; renderProp(); keep(`[data-r="${k}"]`); });
  $$("[data-k]", pg).forEach(b => b.onclick = () => { const k = b.dataset.k, raw = b.dataset.v, v = raw === "true" ? true : raw === "false" ? false : raw; DT[k] = DT[k] === v ? null : v; renderProp(); keep(`[data-k="${k}"][data-v="${raw}"]`); });
  $$("[data-wo]", pg).forEach(b => b.onclick = () => { const k = b.dataset.wo; DT.without[k] = !DT.without[k]; renderProp(); keep(`[data-wo="${k}"]`); });
  $$("[data-rel]", pg).forEach(b => b.onclick = () => openProp(b.dataset.rel));
  const clr = $("#clr", pg); if (clr) clr.onclick = () => { Object.assign(DT, {home: null, starter: null, result: null, rest: null, ranges: {}, without: {}, dvp: false, def: false, open: {}}); renderProp(); };
  $("#pf", pg).onclick = () => playerFilters(p, logs, without);
  $("#lnb", pg).onclick = () => lineSheet(p);
  $("#psb", pg).onclick = () => openSheet(`<h2 id="sht">Position rank</h2><div class="note" style="font-size:15px;color:var(--l2)">${c.pos_rank
    ? `${esc(p.player)} is <b style="color:#fff">${ord(c.pos_rank)}</b> of ${c.pos_n} ${GRPN[MU_GROUP(c.pos)] || "players at his position"} in ${esc(NAME[p.market].toLowerCase())} per game (${esc(c.pos_season || "")}, 3+ games).`
    : "Not enough games to rank him yet."}</div><div class="acts"><button class="btn pri" id="ok1">Done</button></div>`, s2 => { $("#ok1", s2).onclick = closeSheet; });
  $("#mub", pg).onclick = () => matchupSheet(p, side);
  $$(".rp", pg).forEach(gp => {
    const k = gp.dataset.rk, lo = +gp.dataset.lo, hi = +gp.dataset.hi, a = $(".a", gp), b = $(".b", gp), fil = $(".fil", gp), rv = $(".rv", gp);
    // a WebKit range thumb's centre runs from half a thumb (15px) in from each end
    const paint = () => { let x = +a.value, yv = +b.value; if (x > yv) [x, yv] = [yv, x];
      fil.style.left = `calc(3px + (100% - 30px) * ${(x - lo) / (hi - lo)})`; fil.style.right = `calc(3px + (100% - 30px) * ${(hi - yv) / (hi - lo)})`;
      rv.textContent = `${x} – ${yv}`; return [x, yv]; };
    a.oninput = b.oninput = paint; paint();
    a.onchange = b.onchange = () => { const [x, yv] = paint(); if (x === lo && yv === hi) delete DT.ranges[k]; else DT.ranges[k] = [x, yv]; DT.open[k] = true; renderProp(); };
  });
}
const MU_GROUP = pos => ({PG: "G", SG: "G", G: "G", SF: "F", PF: "F", F: "F", C: "C"})[pos] || ({G: "G", F: "F", C: "C"})[(pos || "")[0]];
function lineSheet(p) {
  const lines = allLines(p);
  const rows = lines.map(l => {
    const f = rungAt(p.books.fd, l), k = rungAt(p.books.dk, l);
    const pr = (r, i) => r && r[i] ? american(r[i]) : "—";
    return `<button class="opt" data-l="${l}"><span>${l}${l === p.main ? ' <span class="tg tn">MAIN</span>' : ""}</span><span class="num" style="color:var(--l2);font-size:14px">FD ${pr(f, 1)}/${pr(f, 2)} · DK ${pr(k, 1)}/${pr(k, 2)}</span></button>`;
  }).join("");
  openSheet(`<h2 id="sht">Line</h2><div class="lc" style="margin-bottom:8px"><div class="big num" id="ls-v">${DT.line}</div><div class="stp"><button id="ls-m" aria-label="Lower the line by half a point">−</button><button id="ls-p" aria-label="Raise the line by half a point">+</button></div></div>
    <div class="note" style="margin-bottom:6px">Posted lines (over / under prices):</div>${rows}
    <div class="acts"><button class="btn pri" id="ls-ok">Done</button></div>`, s => {
    const set = v => { DT.line = Math.max(0.5, Math.round(v * 2) / 2); $("#ls-v", s).textContent = DT.line; };
    $("#ls-m", s).onclick = () => set(DT.line - .5); $("#ls-p", s).onclick = () => set(DT.line + .5);
    $$("[data-l]", s).forEach(b => b.onclick = () => { set(+b.dataset.l); closeSheet(); renderProp(); });
    $("#ls-ok", s).onclick = () => { closeSheet(); renderProp(); };
  });
}
function matchupSheet(p, side) {
  const c = p.ctx || {}, g = gameOf(p.gid), gr = grade(p, side), rows = [];
  const row = (lab, r, n, note) => `<div class="kv"><span>${lab}</span><b>${r ? `<span class="rk ${rankCls(r, n, side) === "good" ? "g" : rankCls(r, n, side) === "bad" ? "r" : "n"}">${ord(r)}</span>` : "—"}</b></div>${note ? `<div class="note" style="margin:-4px 0 6px">${note}</div>` : ""}`;
  rows.push(row(`DvP · ${esc(short(p.market))} to ${GRPN[c.group] || "his position"}`, c.dvp_rank, c.teams, c.dvp_rank ? `${esc(p.opp)} allows the ${ord(c.teams - c.dvp_rank + 1)}-most ${esc(short(p.market))} to ${GRPN[c.group]} per possession.` : (p.market === "threes" ? "Not computed for threes." : "")));
  rows.push(row("Def Rank · points allowed", c.def_rank, c.teams, ""));
  rows.push(`<div class="kv"><span>Pace</span><b>${c.pace_rank ? ord(c.pace_rank) + " fastest" : "—"}</b></div>`);
  if (g.lines) rows.push(`<div class="kv"><span>Game</span><b>${g.lines.total ? "Total " + g.lines.total : ""}${g.lines.spread_home !== undefined ? " · " + esc(g.home) + " " + (g.lines.spread_home > 0 ? "+" : "") + g.lines.spread_home : ""}</b></div>`);
  openSheet(`<h2 id="sht">Matchup vs ${esc(p.opp || "")}</h2><div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">${gauge(gr)}<div class="note" style="margin:0;font-size:14px">Grade for the ${side}: A = one of the softest matchups, F = one of the toughest. From ${esc(p.opp || "")}'s rank among ${c.teams || 0} teams this season (1st = toughest defense).</div></div>${rows.join("")}
    <div class="acts"><button class="btn pri" id="mu-ok">Done</button></div>`, s => { $("#mu-ok", s).onclick = closeSheet; });
}
// ── player filters ──
function activeFilters(without) {
  const out = [];
  SEGS.forEach(([k, , opts]) => { if (DT[k] !== null) out.push({key: k, label: opts.find(o => o[0] === DT[k])[1] + (k === "rest" ? " rest" : "")}); });
  RANGES.forEach(([k, , abbr]) => { const r = DT.ranges[k]; if (r) out.push({key: "r:" + k, label: `${abbr} ${r[0]}–${r[1]}`}); });
  without.forEach(w => { if (DT.without[w.key]) out.push({key: "w:" + w.key, label: "Without " + w.name.split(" ").slice(-1)[0]}); });
  return out;
}
function clearFilter(k) {
  if (k.startsWith("r:")) delete DT.ranges[k.slice(2)];
  else if (k.startsWith("w:")) delete DT.without[k.slice(2)];
  else DT[k] = null;
}
function bounds(logs, k) {
  const v = logs.map(l => l[k]).filter(x => x !== null && x !== undefined);
  return v.length ? [Math.floor(Math.min(...v)), Math.ceil(Math.max(...v))] : null;
}
function playerFilters(p, logs, without) {
  const dr = {home: DT.home, starter: DT.starter, result: DT.result, rest: DT.rest, ranges: Object.assign({}, DT.ranges),
              without: Object.assign({}, DT.without)};
  const count = () => windowed(filterLogs(logs, {home: dr.home, starter: dr.starter, result: dr.result, rest: dr.rest,
    ranges: dr.ranges, without: without.filter(w => dr.without[w.key])}), DT.win, D.season, p.opp).length;
  const rng = RANGES.map(([k, lab]) => {
    const b = bounds(logs, k);
    if (!b || b[0] === b[1]) return "";
    const cur = dr.ranges[k] || b;
    return `<div class="rg" data-rk="${k}" data-lo="${b[0]}" data-hi="${b[1]}"><div class="rg-h"><span>${lab}</span><b class="rv">${cur[0]} – ${cur[1]}</b></div>
      <div class="dual"><div class="trk"></div><div class="fil"></div>
      <input type="range" class="a" min="${b[0]}" max="${b[1]}" step="1" value="${cur[0]}" aria-label="${lab} minimum">
      <input type="range" class="b" min="${b[0]}" max="${b[1]}" step="1" value="${cur[1]}" aria-label="${lab} maximum"></div></div>`;
  }).join("");
  const segs = SEGS.map(([k, lab, opts]) => `<div class="sg"><span>${lab}</span><div class="seg" role="group" aria-label="${lab}">${opts.map(([v, t]) =>
    `<button data-sk="${k}" data-sv="${v === null ? "" : v}" aria-pressed="${dr[k] === v}">${t}</button>`).join("")}</div></div>`).join("");
  const wo = without.length ? `<div class="sg"><span>Teammates out tonight</span>${without.map(w =>
    `<button class="opt" data-wk="${w.key}">Without ${esc(w.name)}<span class="ck">${dr.without[w.key] ? "✓" : ""}</span></button>`).join("")}</div>` : "";
  openSheet(`<h2 id="sht">Filter ${esc(p.player.split(" ").slice(-1)[0])}'s games</h2>${rng}${segs}${wo}
    <div class="note">Every number on this page uses only the games that pass. L5 / L10 / L20 = the last games that pass.</div>
    <div class="acts"><button class="btn" id="pf-reset">Reset</button><button class="btn pri" id="pf-ok"></button></div>`, s => {
    const upd = () => { const n = count(); $("#pf-ok", s).textContent = `Show ${n} game${n === 1 ? "" : "s"}`; };
    $$(".rg", s).forEach(g => {
      const k = g.dataset.rk, lo = +g.dataset.lo, hi = +g.dataset.hi, a = $(".a", g), b = $(".b", g), fil = $(".fil", g), rv = $(".rv", g);
      const paint = () => {
        let x = +a.value, y = +b.value;
        if (x > y) { [x, y] = [y, x]; }
        fil.style.left = (100 * (x - lo) / (hi - lo)) + "%"; fil.style.right = (100 * (hi - y) / (hi - lo)) + "%";
        rv.textContent = `${x} – ${y}`;
        if (x === lo && y === hi) delete dr.ranges[k]; else dr.ranges[k] = [x, y];
        upd();
      };
      a.oninput = b.oninput = paint; paint();
    });
    $$("[data-sk]", s).forEach(b => b.onclick = () => {
      const k = b.dataset.sk, raw = b.dataset.sv, v = raw === "" ? null : raw === "true" ? true : raw === "false" ? false : raw;
      dr[k] = v; $$(`[data-sk="${k}"]`, s).forEach(x => x.setAttribute("aria-pressed", x === b)); upd();
    });
    $$("[data-wk]", s).forEach(b => b.onclick = () => { const k = b.dataset.wk; dr.without[k] = !dr.without[k]; $(".ck", b).textContent = dr.without[k] ? "✓" : ""; upd(); });
    $("#pf-reset", s).onclick = () => { Object.assign(DT, {home: null, starter: null, result: null, rest: null, ranges: {}, without: {}, dvp: false, def: false, open: {}}); closeSheet(); renderProp(); };
    $("#pf-ok", s).onclick = () => { Object.assign(DT, {home: dr.home, starter: dr.starter, result: dr.result, rest: dr.rest, ranges: dr.ranges, without: dr.without}); closeSheet(); renderProp(); };
    upd();
  });
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
