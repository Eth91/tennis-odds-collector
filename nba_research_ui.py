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
/* ── list page: measured from the user's reference (iPhone 16 Pro, 402 pt wide; 1 pt = 2.29 px) ── */
body{background:#0f0f0f;--red:#ff090c;--grn:#28da8e}
@supports (color:color(display-p3 1 0 0)){body{--red:color(display-p3 1 .035 .047);--grn:color(display-p3 .157 .855 .557)}}
/* the reference's numbers are Apple's condensed system face (SF Pro at ~66% width), which Safari reaches through font-stretch */
.cd,.oc,.mhd,.bkh,.cells,svg.c2{font-family:system-ui,-apple-system,"Roboto Condensed",sans-serif;font-stretch:66%}
.lh-r{display:flex;align-items:center;gap:8.3px;height:calc(var(--st) + 42.8px);padding:var(--st) 15.3px 0}
.cb.tx{font-size:13.2px;font-weight:400}
.mt.ml{margin-top:9px}
.sx{position:relative;flex:1;min-width:0;display:flex;align-items:center;height:42.8px;padding:0 16px;border-radius:21.4px;
border:1px solid rgba(255,255,255,.1);background:#101010;box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
.sx svg{flex:none;width:17px;height:17px;color:var(--grn)}
.sx input{position:absolute;inset:0;width:100%;height:100%;padding:0 34px 0 44px;border:0;border-radius:21.4px;background:none;
font-size:16px;outline:none;color:#fff;-webkit-appearance:none;appearance:none}
.sx input::-webkit-search-cancel-button{display:none}
.sx .ph3{flex:1;text-align:center;font-size:14.7px;color:#8e8e8e;pointer-events:none;white-space:nowrap}
.sx .ph3 b{color:#fff;font-weight:600}
.sx.has .ph3,.sx:focus-within .ph3{visibility:hidden}
.sx .clr{position:absolute;right:9px;top:11.4px;z-index:1;width:20px;height:20px;padding:0;border:0;border-radius:50%;
background:#3a3a3c;color:#000;font-size:13px;line-height:20px}
.gcs{display:flex;gap:8.7px;overflow-x:auto;margin-top:8.8px;padding:0 15.3px;scrollbar-width:none}
.gcs::-webkit-scrollbar{display:none}
.gc0,.gc{flex:none;height:46.4px;border:1px solid #333;border-radius:9.6px;background:#181818;color:#fff;padding:0;
box-shadow:inset 0 1px 0 rgba(255,255,255,.05)}
.gc0{display:flex;flex-direction:column;align-items:center;justify-content:center;width:63.4px;background:#161616;color:#9a9a9a;
font-size:8.5px;line-height:11px}
.gc0 i{font-style:normal}
.gc{display:flex;align-items:center;justify-content:space-between;width:115px;padding:0 7px 0 7px}
.gt{display:flex;flex-direction:column;gap:2px;padding-top:2px}
.gt span{display:flex;align-items:center;gap:6px;font-size:13.4px;line-height:16.5px}
.gt img{width:13px;height:13px}
.gc em{font-style:normal;font-size:8.4px;color:#9a9a9a;white-space:nowrap;padding-top:2px}
.gc em .lv{color:var(--red);font-weight:700}
.gc[aria-pressed="true"],.gc0[aria-pressed="true"]{background:#2e2e2e;border-color:#555}
.ldv{height:1px;margin-top:8.9px;background:#363636}
.lst{padding-bottom:calc(var(--sb) + 110px)}
.pr{position:relative;display:block;width:100%;height:113px;padding:0 15.3px;border:0;border-bottom:1px solid #343434;
background:none;text-align:left;color:#fff;transition:background-color .25s}
.pr:active{background:#161616;transition:none}
.av{position:absolute;left:15.3px;top:8px;width:45.4px;height:45.4px;border-radius:50%;background:#343434;overflow:hidden}
.av .hs{position:absolute;left:-9px;top:1px;width:63px;height:auto}
.who{position:absolute;left:69.5px;top:9px;right:120px}
.nm{font-size:15.4px;line-height:19px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nm .cd{margin-left:3px;font-size:12.6px;font-weight:400;color:#9a9a9a}
.lin{margin-top:.5px;font-size:15.4px;line-height:19px;font-weight:400}
.oc{position:absolute;top:11px;width:60px;text-align:center}
.oc i{display:block;font-style:normal;font-size:12.6px;line-height:19px;color:#9a9a9a}
.oc b{display:block;margin-top:1px;font-size:15.6px;line-height:19px;font-weight:400}
.oc.o{left:265.8px} .oc.e{left:329px}
.up{color:var(--grn)!important} .dn{color:var(--red)!important} .md{color:var(--yel)!important}
.bx6{position:absolute;left:15.3px;right:15.3px;top:61.3px;display:grid;grid-template-columns:repeat(6,1fr);gap:6.1px}
.bx6>div{height:41.5px;border-radius:5px;background:#222;text-align:center;padding-top:5.6px}
.bx6 i{display:block;font-style:normal;font-size:9.6px;line-height:12px;color:#fff}
.bx6 b{display:block;margin-top:1.6px;font-size:13.4px;line-height:16px;font-weight:600;color:#fff}
.bx6 b.sm{color:#8e8e8e;font-weight:500}
.lin{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mv{margin-left:6px;font-size:11px;color:#a8a8a8;vertical-align:1px}
.pl{display:inline-block;margin-left:7px;padding:1px 5px 0;border-radius:4px;background:rgba(255,255,255,.09);color:#d2d2d2;
font-size:10px;line-height:14px;font-weight:600;letter-spacing:.01em;vertical-align:2px;white-space:nowrap}
.pl.up{background:rgba(40,218,142,.15);color:var(--grn)} .pl.dn{background:rgba(255,69,58,.16);color:#ff6a60}
.oc i.df{color:var(--yel)}
.mu{color:#8e8e8e!important}
.tg{display:inline-block;margin-left:5px;padding:1px 5px 0;border-radius:4px;font-size:9.5px;font-weight:800;
letter-spacing:.04em;vertical-align:1.5px}
.tq{background:rgba(255,214,10,.18);color:var(--yel)} .to{background:rgba(255,69,58,.2);color:var(--red)}
.tp{background:rgba(48,209,88,.16);color:var(--grn)} .tl{background:var(--red);color:#fff}
.tf{background:rgba(255,159,10,.18);color:var(--org)} .tn{background:var(--g3);color:var(--l2)}
.lhd{display:flex;justify-content:space-between;padding:12px 15.3px 8px;font-size:11.5px;color:#8e8e8e;border-bottom:1px solid #343434}
.empty{padding:56px 24px;text-align:center;color:var(--l2);font-size:15px;line-height:1.4}
/* the Injuries view: prop-row look; the boxes are the teammates who took his start / minutes */
.ir .lin{font-size:13.6px;color:#b0b0b0}
.bx4{position:absolute;left:15.3px;right:15.3px;top:61.3px;display:grid;grid-template-columns:repeat(4,1fr);gap:6.1px}
.ijb{display:block;width:100%;min-width:0;height:41.5px;padding:5.6px 4px 0;border:0;border-radius:5px;background:#222;color:#fff;text-align:center}
button.ijb:active{background:#333}
.ijb i{display:block;font-family:system-ui,-apple-system,"Roboto Condensed",sans-serif;font-stretch:66%;font-style:normal;font-size:10.4px;
line-height:12px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ijb b{display:block;margin-top:1.6px;font-size:13.4px;line-height:16px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ijb b.sm{color:#8e8e8e;font-weight:500}
.ijb small{font-size:11px;font-weight:500;color:#9a9a9a}
.pr.ir0{height:62px;contain-intrinsic-size:auto 62px}
.empty b{display:block;margin-bottom:6px;color:var(--l1);font-size:18px}
.empty button{margin-top:16px}
.btn{height:46px;padding:0 20px;border:1px solid rgba(255,255,255,.15);border-radius:23px;background:none;color:#fff;font-size:16px;font-weight:600}
.btn.pri{border-color:#fff;background:#fff;color:#000}
.ban{margin:10px 15.3px 0;padding:10px 12px;border-radius:12px;background:rgba(255,159,10,.14);color:var(--org);font-size:13px;
font-weight:600}
.ban.err{background:rgba(255,69,58,.15);color:var(--red)}
.sk{height:113px;border-bottom:1px solid #343434;background:linear-gradient(90deg,#141414,#1d1d1d,#141414);
background-size:200% 100%;animation:sk 1.1s infinite}
@keyframes sk{to{background-position:-200% 0}}
@media (prefers-reduced-motion:reduce){.sk{animation:none}}
/* markets view */
.mhd,.mrw{display:grid;grid-template-columns:1fr 84px 84px;align-items:center;padding:0 15.3px;column-gap:8px}
.mhd{height:34px;border-bottom:1px solid #343434;font-size:12.6px;color:#9a9a9a}
.mhd span:not(:first-child){text-align:center}
.mrw{width:100%;min-height:62px;border:0;border-bottom:1px solid #343434;background:none;color:#fff;text-align:left}
.mrw:active{background:#161616}
.mrw .nm{font-size:14px}
.mrw .lin{margin-top:2px;font-size:12.6px;color:#9a9a9a}
.mp{display:flex;flex-direction:column;align-items:center;gap:3px;font-size:13.5px;font-variant-numeric:tabular-nums}
.mp span{display:block;min-width:70px;padding:2px 0;border-radius:6px;text-align:center}
.mp .best{background:rgba(40,218,142,.14);color:var(--grn)}
.mp .na{color:#5a5a5a}
/* floating tab bar */
.tb{position:fixed;left:15.3px;right:15.3px;bottom:max(var(--sb),10px);z-index:25;display:flex;align-items:center;
justify-content:space-between;pointer-events:none;transition:transform .35s cubic-bezier(.32,.72,0,1),opacity .25s}
.tb>*{pointer-events:auto}
.tb.away{transform:translateY(140%);opacity:0}
.glass{border:1px solid rgba(255,255,255,.2);background:rgba(36,36,36,.38);
-webkit-backdrop-filter:blur(7px) saturate(150%);backdrop-filter:blur(7px) saturate(150%);
box-shadow:0 10px 30px rgba(0,0,0,.5),inset 0 1px 1px rgba(255,255,255,.12),inset 0 -1px 1px rgba(255,255,255,.05)}
.tbc{display:flex;align-items:center;width:249.8px;height:62px;padding:0;border-radius:31px}
.tbc button{position:relative;flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;height:53px;
padding:0 0 1px;border:0;border-radius:26.5px;background:none;color:#fff;font-size:10.4px;transition:background-color .2s}
.tbc button svg{width:22px;height:22px;margin-bottom:-1.5px}
.tbc button[aria-pressed="true"]{background:rgba(255,255,255,.12)}
.tbf{position:relative;width:62.9px;height:62.9px;padding:0;border-radius:50%;color:#fff;display:flex;align-items:center;justify-content:center}
.tbf svg{width:22px;height:17px}
.tbf b{position:absolute;right:6px;top:6px;min-width:17px;height:17px;padding:0 4px;border-radius:9px;background:#fff;
color:#000;font-size:11px;font-weight:700;line-height:17px;text-align:center}
/* DvP table */
.dvt{display:grid;grid-template-columns:44px 1fr auto;align-items:center;min-height:42px;border-bottom:.5px solid var(--sep);font-size:15px}
.dvt img{width:22px;height:22px;vertical-align:-6px;margin-right:8px}
.dvt b{font-weight:600;font-variant-numeric:tabular-nums}
.dvt span:last-child{color:var(--l2);font-size:13px}
.seg{display:flex;align-items:center;height:42.4px;margin-top:10px;padding:0 3.5px;border:1px solid #2a2a2a;border-radius:21.2px;background:#101010}
.seg button{flex:1;display:inline-flex;align-items:center;justify-content:center;gap:6px;height:35px;border:0;border-radius:17.5px;background:none;
font-size:13px;font-weight:600;color:#fff}
.seg button[aria-pressed="true"]{background:#313131}
.seg button img{width:16px;height:16px} .seg button svg{width:14px;height:14px;fill:currentColor}
/* chips: the chart filters' outline pills */
.chips{display:flex;flex-wrap:wrap;gap:8.3px;margin-top:10px}
.chip{display:inline-flex;align-items:center;height:30px;padding:0 13px;border:1px solid rgba(255,255,255,.15);border-radius:15px;background:none;
color:#fff;font-size:13px;font-weight:500}
.chip[aria-pressed="true"]{border-color:rgba(255,255,255,.3);background:#2a2a2a}
/* ── bottom sheet ── */
.scrim{position:fixed;inset:0;z-index:40;background:rgba(0,0,0,.5);opacity:0;transition:opacity .34s ease;pointer-events:none}
.scrim.on{pointer-events:auto}
.scrim.on{opacity:1}
.sheet{position:fixed;left:0;right:0;bottom:0;z-index:41;max-height:86vh;overflow-y:auto;padding:8px 16px calc(var(--sb) + 16px);
border-top:1px solid #2a2a2a;border-radius:20px 20px 0 0;background:#0c0c0c;box-shadow:0 -12px 40px rgba(0,0,0,.6);
transform:translateY(100%);overscroll-behavior:contain}
.sheet.on{transform:none}
.sheet:focus{outline:none}
.grab{width:36px;height:5px;margin:0 auto 12px;border-radius:3px;background:#3a3a3a}
.sheet h2{margin:0 0 12px;font-size:20px;font-weight:700;letter-spacing:-.2px}
.sheet .kv,.sheet .opt,.sheet .dvt,.mrr{border-bottom-color:#262626}
.opt{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:48px;padding:0 4px;border:0;
border-bottom:.5px solid var(--sep);background:none;font-size:17px;text-align:left}
.opt .ck{color:var(--grn);font-weight:700}
.fl{display:block;margin:12px 0 0}
.fl span{display:block;margin:0 0 8px;font-size:13.1px;font-weight:600}
.fl select,.fl input{width:100%;height:44px;padding:0 14px;border:1px solid #2a2a2a;border-radius:12px;background:#141414;color:#fff;font-size:17px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sheet .acts{display:flex;gap:10px;margin-top:18px}
.sheet .acts .btn{flex:1}
/* ── player page ── */
.pg{position:fixed;inset:0;z-index:30;overflow-y:auto;background:var(--bg);transform:translateX(100%);
-webkit-overflow-scrolling:touch;overscroll-behavior:contain;box-shadow:-12px 0 32px rgba(0,0,0,.45)}
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
.stp button{width:44px;height:44px;border:1px solid rgba(255,255,255,.15);border-radius:22px;background:#141414;color:#fff;font-size:24px;font-weight:500;line-height:1}
.bks{margin-top:12px;border-top:.5px solid var(--sep)}
.bkr{display:grid;grid-template-columns:28px 1fr auto auto;align-items:center;gap:10px;min-height:52px;
border-bottom:.5px solid var(--sep);font-size:15px}
.bkr:last-child{border-bottom:0}
.bkr img{width:28px;height:28px;border-radius:7px}
.bkr .ln2{color:var(--l2);font-size:12px}
.bkr .od{min-width:62px;padding:6px 0;border-radius:8px;background:var(--g2);text-align:center;font-weight:700}
.bkr .od.best{background:rgba(48,209,88,.18);color:var(--grn)}
.bkr button.od{border:0;cursor:pointer}
.bkr .od[aria-pressed="true"]{box-shadow:inset 0 0 0 1px #5a5a5a}
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
svg.ch g.br:focus{outline:none} svg.ch g.br:focus-visible rect{stroke:var(--blue);stroke-width:2}
.rg{margin:16px 0 0}
.rg-h{display:flex;justify-content:space-between;align-items:baseline;font-size:13.2px;font-weight:600}
.rg-h b{font-size:12px;font-weight:500;color:#9a9a9a;font-variant-numeric:tabular-nums}
.rg .dual2{margin-top:10px}
.dual2{touch-action:pan-y;-webkit-user-select:none;user-select:none;cursor:pointer}
.sg{margin:16px 0 0}
.sg>span{display:block;margin:0 0 8px;font-size:13.1px;font-weight:600}
.sg .seg{margin:0}
/* the With / Without sheet: a teammate a row, Any / With / W/O on the right */
.mrr{display:flex;align-items:center;justify-content:space-between;gap:9px;min-height:58px;border-bottom:.5px solid var(--sep)}
.mrn{flex:1;min-width:0}
.av.mav{position:relative;left:auto;top:auto;flex:none;width:36px;height:36px}
.av.mav .hs{left:-7px;top:1px;width:50px}
.mrn b{display:block;font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mrn small{display:block;margin-top:2px;font-size:12px;color:#9a9a9a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.seg.mseg{flex:none;width:146px;height:34px;margin:0;padding:0 2.5px}
.seg.mseg button{height:27px;border-radius:13.5px;font-size:12px}
/* the Matchup page: a full page over the player's (the reference's measures, 402 pt wide) */
#mp{z-index:32}
.mpc{margin:6px 15.3px 0;padding:14px 14px 12px;border:1px solid #2a2a2a;border-radius:16px;background:linear-gradient(#171717,#111)}
.mpg{display:flex;align-items:center;gap:12px;margin-bottom:4px}
.mpg b{display:block;font-size:17px;font-weight:700} .mpg span{display:block;margin-top:2px;font-size:13px;color:#9a9a9a}
.mpc .kv{min-height:40px;font-size:14px;border-bottom-color:#262626}
.mpft{display:flex;align-items:center;gap:10px;margin-top:10px;padding-top:12px;border-top:1px solid #262626}
.mpft>div{flex:1} .mpft span{display:block;font-size:15px;color:#8e8e8e} .mpft b{display:block;margin-top:2px;font-size:17px;font-weight:500;color:#8e8e8e}
.mpft .cb{background:#1c1c1c}
.mpt{margin:40px 15.3px 0;font-size:21px;font-weight:700;letter-spacing:-.2px}
.mpf{display:flex;align-items:center;gap:9px;margin:13px 15.3px 0;font-size:15.5px;font-weight:600;white-space:nowrap}
.dd{position:relative;display:inline-flex;align-items:center;gap:9px;height:27.3px;padding:0 12px;border:1px solid rgba(255,255,255,.2);border-radius:14px;
font-size:13.8px;font-weight:500}
.dd svg{width:11px;height:7px}
.dd select{position:absolute;inset:0;width:100%;height:100%;opacity:0;font-size:16px;-webkit-appearance:none;appearance:none}
table.vs{width:100%;margin-top:10px;border-collapse:collapse;table-layout:fixed}
.vs th{height:30px;padding:0;text-align:left;font-family:system-ui,-apple-system,"Roboto Condensed",sans-serif;font-stretch:66%;font-size:12.6px;
font-weight:400;color:#9a9a9a;border-bottom:1px solid #343434}
.vs td{height:42.8px;padding:0;font-size:15.4px;border-bottom:1px solid #343434;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vs th:first-child,.vs td:first-child{padding-left:15.3px}
.vs td i{font-style:normal;font-size:12.5px;margin-right:4px;vertical-align:1px}
.vs td.cd{font-size:13px;color:#9a9a9a} .vs td.cd b{font-weight:400;color:#e6e6e6}
.vs tr[data-g]{cursor:pointer} .vs tr[data-g]:active td{background:#161616}
.vsm{display:flex;align-items:center;gap:9px;height:26.6px;margin:20px auto 0;padding:0 13px;border:1px solid rgba(255,255,255,.2);border-radius:13.3px;
background:none;color:#fff;font-size:13.8px;font-weight:500}
.vsm svg{width:11px;height:7px;transition:transform .25s} .vsm[aria-expanded="true"] svg{transform:rotate(180deg)}
.vsk{margin:12px 15.3px 0} .vsk .sk{height:34px;margin-bottom:8px}
/* the shot chart card (the reference's card, under the recent games) */
.shc{margin:30px 15.3px 0;padding:0 14px 12px;border:1px solid #2a2a2a;border-radius:16px;background:linear-gradient(#171717,#111)}
.shc:empty{display:none}
.shh{position:relative;display:flex;align-items:center;justify-content:center;height:56px;margin:0 -14px 12px;border-bottom:1px solid #2a2a2a;
font-family:system-ui,-apple-system,"Roboto Condensed",sans-serif;font-stretch:66%;font-size:18px;font-weight:500;letter-spacing:.3px}
.shh .av{position:absolute;left:14px;top:9px;width:38px;height:38px}
.shh .av .hs{left:-7px;top:1px;width:52px}
.shh .shl0{position:absolute;right:14px;top:9px;width:38px;height:38px}
.shc .seg{position:relative} .shc .seg button{position:relative;z-index:1;background:none} .shc .seg .pill2{background:#313131}
.shy{display:flex;align-items:center;gap:8px;margin:10px 0 4px} .shy .chip{height:28px;padding:0 12px}
.shy span{margin-left:auto;font-size:12.5px;color:#9a9a9a}
svg.shct{display:block;width:100%;height:auto;margin-top:6px}
.shct .shl{fill:none;stroke:#4a4a4a;stroke-width:2}
.shct text{text-anchor:middle;fill:#fff}
.shct .shv{font-size:24px;font-weight:700} .shct .shv.sm{font-size:19px}
.shct .shs{font-size:15px;fill:#cfcfcf}
.shk{display:flex;align-items:center;gap:8px;margin:8px 0 2px;font-size:11.5px;color:#9a9a9a}
.shk b{display:inline-block;width:9px;height:9px;margin-right:5px;border-radius:50%;vertical-align:-1px}
.shk b.d1{background:#28da8e} .shk b.d0{border:1.5px solid #ff453a}
.shk span:last-child{margin-left:auto}
.shmd{display:flex;gap:6px;margin-left:auto}
.shct .shz{stroke:#262626;stroke-width:1.5}
.shct .shm circle{fill:none;stroke:#ff453a;stroke-width:1.6;opacity:.7}
.shct .shk2 circle{fill:#28da8e;opacity:.85}
.shk i{flex:1;height:6px;border-radius:3px;background:linear-gradient(90deg,rgba(255,69,58,.62),#191919,rgba(40,218,142,.62))}
.shw{margin:18px 0 4px;font-size:15px;font-weight:700}
.shr span small,.shr b small{display:block;margin-top:2px;font-size:12px;font-weight:400;color:#9a9a9a}
.shr b em{font-style:normal}
.shc .shr{min-height:52px;border-bottom-color:#262626}
/* player search rows (any player), tappable box score rows */
.vpr{width:100%;text-align:left} .vpr .vgo{position:absolute;right:16px;top:20px;font-size:20px;color:#6e6e6e}
.bx tr[data-vp]{cursor:pointer} .bx tr[data-vp]:active td{background:#222}
.ir[data-vp]{cursor:pointer}
/* Lineups (beside Injuries): a card a game, each team's five as tiles, NEW for a starter outside its usual five */
.seg.ivs{margin:10px 15.3px 2px;position:relative} .seg.ivs button{position:relative;z-index:1;background:none} .seg.ivs .pill2{background:#313131}
.lug{margin:14px 15.3px 0;border:1px solid #2a2a2a;border-radius:16px;background:#121212;overflow:hidden}
.lugh{display:flex;justify-content:space-between;padding:10px 14px;font-size:11.5px;letter-spacing:.3px;color:#8e8e8e;text-transform:uppercase;border-bottom:1px solid #222}
.lut{padding:10px 12px 12px;border-bottom:1px solid #222} .lut:last-child{border-bottom:0}
.luth{display:flex;align-items:center;gap:8px;font-size:15px} .luth img{width:22px;height:22px} .luth em{margin-left:auto;font-style:normal;font-size:12px;color:#8e8e8e}
.lur{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:10px}
.lus{display:flex;flex-direction:column;align-items:center;gap:3px;min-width:0;padding:7px 2px;border:1px solid #262626;border-radius:12px;background:#181818;color:#fff}
.lus:active{background:#222} .lus.new{border-color:var(--org)}
.lus .av{position:relative;left:auto;top:auto;width:40px;height:40px}
.lus .av .hs{left:-8px;top:1px;width:56px}
.lus b{max-width:100%;font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lus i{font-style:normal;font-size:10.5px;color:#9a9a9a} .lus.new i{color:var(--org);font-weight:700}
.lum{margin-top:9px;font-size:12.5px;color:#b0b0b0;line-height:1.7}
.lum b{margin-right:6px;font-size:10.5px;letter-spacing:.3px;color:#8e8e8e;text-transform:uppercase}
.lum button{padding:0;border:0;background:none;color:#e6e6e6;font-size:12.5px} .lum .tg{margin:0 0 0 4px}
/* who guards him: the shot chart's card, the recent games' table */
.wg table.vs{margin-top:6px} .wg .vs th:first-child,.wg .vs td:first-child{padding-left:0}
.wg .vs td small{font-size:11px;color:#9a9a9a} .wg .vs tr:last-child td{border-bottom:0}
.wg .vs tr[data-vp]{cursor:pointer}
/* the Movers tab: the line from its open */
.lin .mvo{color:#9a9a9a} .lin .mv.up{color:var(--grn)} .lin .mv.dn{color:var(--red)}
/* the box score sheet: one height whatever is in it, so it never resizes while it rises; a skeleton of the box's shape */
.sheet[data-kind="box"]{height:86vh}
.sheet[data-kind="box"] .seg{position:relative}
.sheet[data-kind="box"] .seg button{position:relative;z-index:1;background:none}
.sheet[data-kind="box"] .seg .pill2{background:#313131}
.bxsk i,.bxsk b{display:block;border-radius:8px;background:linear-gradient(90deg,#141414,#1d1d1d,#141414);background-size:200% 100%;animation:sk 1.2s linear infinite}
.bxsk i:nth-child(1){width:62%;height:30px;margin:2px auto 8px} .bxsk i:nth-child(2){width:34%;height:14px;margin:0 auto 14px}
.bxsk i:nth-child(3){height:42px;border-radius:21px;margin-bottom:12px} .bxsk b{height:34px;margin-bottom:4px}
/* the box score sheet: a team's players, the name column pinned while the stats scroll sideways */
.bxh{display:flex;align-items:center;justify-content:center;gap:8px;font-size:16px}
.bxh img{width:26px;height:26px}
.bxh span{font-size:24px;font-weight:700} .bxh span.lo{color:var(--l2)}
.bxh i{font-style:normal;color:var(--l2)}
.bxs{margin:4px 0 12px;text-align:center;font-size:13px;color:var(--l2)}
.bxw{margin:12px 0 0;overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #2a2a2a;border-radius:13px;background:#141414}
table.bx{border-collapse:collapse;font-family:system-ui,-apple-system,"Roboto Condensed",sans-serif;font-stretch:66%;font-size:14.5px;
font-variant-numeric:tabular-nums;white-space:nowrap;color:#cfcfcf}
.bx th,.bx td{padding:8px 7px;text-align:right;border-bottom:.5px solid var(--sep)}
.bx th{font-size:11.5px;font-weight:500;color:#9a9a9a;letter-spacing:.2px}
.bx th:first-child,.bx td:first-child{position:sticky;left:0;z-index:1;max-width:142px;padding-left:12px;overflow:hidden;
text-overflow:ellipsis;text-align:left;background:#141414;color:#fff;font-stretch:100%;font-size:14px}
.bx th:last-child,.bx td:last-child{padding-right:12px}
.bx th,.bx td{border-bottom-color:#262626} .bx tr:last-child td{border-bottom:0}
.bx td.hi{color:#fff;font-weight:700} .bx th.hi{color:var(--grn)}
.bx tr.me td{background:#262626;color:#fff;font-weight:700}
.bx tr.bxd td{position:static;padding:12px 12px 4px;background:none;font-size:11.5px;font-weight:500;color:#9a9a9a}
.bx tr.tot td{font-weight:700;color:#fff}
.bxn{margin:10px 2px 0;font-size:13px;color:#9a9a9a;line-height:1.5}
.bxn b{margin-right:6px;font-size:11.5px;color:var(--l1)}
.sheet .acts.stk{position:sticky;bottom:calc(-16px - var(--sb));margin:0 -16px;padding:12px 16px calc(var(--sb) + 16px);background:#0c0c0c;
box-shadow:0 -1px 0 #262626}
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
/* ── player page: measured from the user's reference (iPhone 16 Pro, 402 pt wide; 1 pt = 2.29 px) ── */
.pg{background:#0f0f0f;--red:#ff090c;--grn:#28da8e}
@supports (color:color(display-p3 1 0 0)){.pg{--red:color(display-p3 1 .035 .047);--grn:color(display-p3 .157 .855 .557)}}
.ph{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:8.3px;height:calc(var(--st) + 42.8px);
padding:var(--st) 15.3px 0;pointer-events:none}
.ph>*{pointer-events:auto}
/* what scrolls under the floating header fades out behind its title, as on the reference */
.ph::before{content:"";position:absolute;left:0;right:0;top:0;bottom:-22px;z-index:-1;pointer-events:none;
background:linear-gradient(#000 0,#000 calc(100% - 34px),rgba(0,0,0,0))}
.cb{flex:none;display:inline-flex;align-items:center;justify-content:center;width:42.8px;height:42.8px;border-radius:50%;
border:1px solid rgba(255,255,255,.1);background:rgba(19,19,19,.86);color:#fff;box-shadow:0 2px 10px rgba(0,0,0,.55);
-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px)}
.cb svg{width:19px;height:19px}
.cb.fav{color:var(--yel)} .cb.fav svg{fill:var(--yel)}
.ph-t{position:absolute;left:110px;right:110px;top:var(--st);height:42.8px;display:flex;flex-direction:column;
justify-content:center;text-align:center;line-height:1.15;text-shadow:0 1px 6px rgba(0,0,0,.6)}
.ph .sp2{flex:1}
.ph-t b{display:block;font-size:14.3px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ph-t span{display:block;margin-top:2.5px;font-size:11.6px;color:#9d9d9d;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mt{height:43.7px;margin:8px 15.3px 0;border:1px solid rgba(255,255,255,.1);border-radius:22px;background:#161616;overflow:hidden;
box-shadow:inset 0 1px 0 rgba(255,255,255,.07)}
.mt-in{display:flex;align-items:center;height:100%;overflow-x:auto;padding:0 3.5px;scrollbar-width:none}
.mt-in::-webkit-scrollbar{display:none}
.mt-in{position:relative}
.mt button{position:relative;z-index:1;flex:none;width:72.48px;height:35px;padding:0;border:0;border-radius:17.5px;background:none;color:#fff;font-size:13px;
transition:color .25s}
.mt button[aria-pressed="true"]{background:#313131;color:#fff}
.hro{position:relative;height:150px;margin-top:12.5px;padding:4px 15.3px 0;border-bottom:1px solid #343434;overflow:hidden}
.hro-l{position:relative;z-index:1;max-width:60%}
.hro-l h2{margin:0;font-size:20.2px;font-weight:600;line-height:24px;letter-spacing:-.01em}
.hro-s{font-size:12.4px;line-height:17.5px;color:#9b9b9b}
.hro-s:first-of-type{margin-top:3.5px}
.tlg{position:absolute;left:0;top:89.5px;display:flex;align-items:center;justify-content:center;width:43.7px;height:43.7px;border-radius:50%}
.tlg img{width:30px;height:30px}
.hro-i{position:absolute;right:4px;bottom:0;height:143px;width:auto}
.sg2{position:relative;height:93px;padding:0 15.3px}
.cells{position:absolute;left:15.3px;top:14.1px;display:grid;grid-template-columns:73px 73.4px auto;row-gap:11.4px}
.cells>div,.cells>button{min-width:0;padding:0;border:0;background:none;text-align:left;color:#fff}
.cells i{display:block;font-style:normal;font-size:12.6px;line-height:14px;color:#a1a1a1;white-space:nowrap}
.cells b{display:flex;align-items:center;gap:1px;margin-top:3px;font-size:14.9px;font-stretch:62%;line-height:17px;font-weight:400;white-space:nowrap}
.cv{margin-left:5px;color:#a1a1a1;font-size:15px;line-height:1}
.tri{font-size:11.5px;margin-right:1px}
.cells .vs{color:#a1a1a1;font-size:14.9px;margin-right:3px} .tri.up{color:var(--grn)} .tri.dn{color:var(--red)}
.muc{position:absolute;right:15.3px;top:13.1px;display:flex;flex-direction:column;align-items:center;justify-content:center;
width:94.4px;height:79.5px;padding:0;border:1px solid #2a2a2a;border-radius:13px;background:#131313;color:#fff;font-size:11.6px}
.muc svg{margin:-4px 0 -2px}
.c2w{position:relative;margin-top:11px;padding:0 15.3px;overflow-x:auto;scrollbar-width:none}
.c2w::-webkit-scrollbar{display:none}
svg.c2{display:block}
svg.c2 .ax{fill:#9a9a9a;font-size:14.5px}
svg.c2 .lx{fill:#fff;font-size:14.9px}
svg.c2 .mn{fill:#fff;font-size:15.5px;font-weight:600}
svg.c2 .vv{fill:#0b0b0b;font-size:14.9px;font-weight:400}
svg.c2 .vw{fill:#fff;font-size:14.9px;font-weight:400}
svg.c2 .xl{fill:#9a9a9a;font-size:10.5px}
svg.c2 g.br:focus{outline:none} svg.c2 g.br:focus-visible rect{stroke:var(--blue);stroke-width:2}
.wrow{display:flex;align-items:center;gap:9.6px;margin:17.5px 15.3px 0}
.wcap{position:relative;flex:1;display:flex;height:42.4px;padding:0 3.5px;align-items:center;border:1px solid #2a2a2a;border-radius:21.2px;
background:#161616;overflow-x:auto;scrollbar-width:none}
.wcap::-webkit-scrollbar{display:none}
.wc{position:relative;z-index:1;flex:1;min-width:0;height:35px;padding:0;border:0;border-radius:17.5px;background:none;text-align:center;line-height:1.35}
.wc i{display:block;font-style:normal;font-size:10.7px;font-weight:500;color:#fff}
.wc b{display:block;font-size:11.8px;font-weight:700}
.wc b.up{color:var(--grn)} .wc b.dn{color:var(--red)}
#mtl button[aria-pressed="true"],.wc[aria-pressed="true"],.tbc button[aria-pressed="true"]{background:none}
.wc:disabled{opacity:.35}
.fb{width:42.8px;height:42.8px}
.fb svg{width:19px;height:15px}
.cf{margin:18px 15.3px 0}
.cf-h{display:flex;align-items:center;gap:10.5px;height:19.2px}
.cf-h h3{margin:0;font-size:12px;font-weight:600}
.ca{height:19.2px;padding:0 9.2px;border:1px solid #4a4a4a;border-radius:9.6px;background:#171717;font-size:8.4px}
.fcs{display:flex;flex-wrap:wrap;gap:8.3px;margin-top:17.2px}
.fc{display:inline-flex;align-items:center;gap:0;height:26.2px;padding:0 12px;border:1px solid rgba(255,255,255,.15);border-radius:13.1px;
background:#141414;font-size:12.8px;letter-spacing:-.25px;color:#fff;box-shadow:inset 0 1px 0 rgba(255,255,255,.07);
transition:background-color .22s,border-color .22s,transform .16s}
.fc svg{width:13px;height:12px;margin-right:7px}
.fc em{font-style:normal;margin-left:.3em} .fc em.good{color:var(--grn)} .fc em.bad{color:var(--red)} .fc em.mid{color:var(--yel)}
.fc.on{background:#2a2a2a;border-color:rgba(255,255,255,.2)}
.rp{margin:17.3px 0 0}
.rp-h{display:flex;justify-content:space-between;align-items:baseline;height:16px}
.rp-h span{font-size:13.2px;font-weight:600}
.rp-h b{font-size:12px;font-weight:500;color:#9a9a9a;font-variant-numeric:tabular-nums}
.dual2{position:relative;height:35px;margin-top:13.5px;border:1px solid #2a2a2a;border-radius:17.5px;background:#141414}
.dual2 .fil{position:absolute;top:4px;height:25px;border-radius:12.5px;background:linear-gradient(#3d3d3d,#333)}
.dual2 .th{position:absolute;top:3.5px;width:26px;height:26px;margin-left:-13px;border-radius:50%}
.rp-b{display:flex;justify-content:space-between;margin:2px 10px 0 13px;font-size:15px;line-height:17px;font-variant-numeric:tabular-nums}
.sec2{margin:28px 15.3px 0}
.sec2 h3{margin:0 0 10px;font-size:13.1px;font-weight:600}
.box0{padding:12px;border:1px solid #2a2a2a;border-radius:13px;background:#141414;font-size:14px}
.box0 .kv{font-size:14px;min-height:40px}
.pg details.log summary{font-size:13.1px;text-transform:none;letter-spacing:0;color:#fff}
/* books table (measured: header 31.5 pt with a 23 pt LINE pill, rows 39.7 pt, columns at 15.3 / 136.8 / 226.3 / 310.7 pt) */
.bkt{margin-top:28.3px}
.bkh,.bkr2{display:grid;grid-template-columns:121.5px 89.5px 84.4px 1fr;align-items:center;padding:0 15.3px;border-bottom:1px solid #262626}
.bkh{height:39.4px;font-size:14.3px;font-weight:500;color:#9a9a9a}
.lnp{display:inline-flex;align-items:center;justify-content:space-between;width:54.6px;height:23px;padding:0 8px 0 7.5px;
border:1px solid rgba(255,255,255,.15);border-radius:11.5px;background:#151515;color:#9a9a9a;font:inherit;
box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
.lnp svg{width:8.5px;height:6px}
.bkr2{height:39.7px;font-size:15.4px;font-weight:500}
.bkr2>button{justify-self:start;padding:6px 8px 6px 0;margin:-6px 0;border:0;background:none;color:#fff;font:inherit;font-weight:500;
font-variant-numeric:normal}
.bkr2 .bl{padding-left:4.8px}
.bkr2 .best{color:var(--grn)}
.bkr2.fr{color:#8e8e8e;font-weight:400;font-size:14px}
.bkr2.fr small{font-size:10px;color:#6e6e6e;margin-left:4px}
.bkr2.fr .bl{padding-left:4.8px;color:#8e8e8e}
svg.hc{display:block;margin-top:2px;font-family:system-ui,-apple-system,sans-serif;font-stretch:66%}
svg.hc text{fill:#8e8e8e;font-size:11px}
.ldr{font-family:system-ui,-apple-system,sans-serif;font-stretch:66%}
.lh2,.lr{display:grid;grid-template-columns:46px 56px 54px 50px 1fr 1fr;align-items:center;column-gap:5px}
.lr .mo{color:#7c7c7c;font-style:italic}
.lh2{height:30px;font-size:13px;color:#9a9a9a;border-bottom:1px solid #262626}
.lr{width:100%;height:36px;padding:0;border:0;border-bottom:1px solid #1e1e1e;background:none;color:#fff;font:inherit;font-size:15px;
text-align:left;font-variant-numeric:tabular-nums}
.lr.on{background:#1b1b1b;box-shadow:inset 3px 0 0 #fff}
.lr>span:first-child{padding-left:8px}
.lr .fv{color:#8e8e8e}
.lr .best{color:var(--grn)} .lr .na{color:#5f5f5f}
.lr .up{color:var(--grn)} .lr .dn{color:var(--red)} .lr .sm{color:#8e8e8e}
.lk{border:0;background:none;color:#9a9a9a;font:inherit;font-size:11.5px;padding:0}
.sst{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:2px 0 10px}
.sst>div{padding:9px 10px;border:1px solid #2a2a2a;border-radius:13px;background:#141414}
.sst b{display:block;font-size:17px;font-weight:700} .sst i{display:block;font-style:normal;font-size:11px;color:var(--l3)}
.hl span{color:#bdbdbd;margin-left:auto}
.cal{font-size:11.5px;font-weight:500;color:var(--l2)}
.scr{display:grid;grid-template-columns:1fr 44px 70px 50px 64px;align-items:center;column-gap:6px;padding:9px 0;
border-bottom:.5px solid var(--sep);font-size:13px}
.scr b{display:block;font-weight:600;font-size:13.5px}
.scr div>span{display:block;color:var(--l3);font-size:10.5px;line-height:1.3}
.scr.hd{padding:6px 0;font-size:11px;color:var(--l3)}
.scr .num{text-align:right}
.vd{display:inline-block;padding:2px 6px;border-radius:5px;background:var(--g3);color:var(--l2);font-style:normal;font-size:10.5px;
font-weight:700;white-space:nowrap}
.vd.g{background:rgba(48,209,88,.18);color:var(--grn)} .vd.r{background:rgba(255,69,58,.2);color:var(--red)}
.pj .pjt{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:6px}
.pj .pjt b{font-size:24px;font-weight:700}
.pj .pjt i{font-style:normal;color:#9a9a9a;font-size:12px}
.pj .pjr{font-size:12px;color:#bdbdbd}
svg.pjh{display:block;margin:2px 0 4px}
svg.pjh text{fill:#8e8e8e;font-size:10px}
.pj .kv small{color:#8e8e8e;font-weight:400}
.pj .kv.mo1 span,.pj .kv.mo1 b{color:#8e8e8e;font-weight:400}
.pjo{margin:10px 0 0;font-size:11px;color:#8e8e8e;text-transform:uppercase;letter-spacing:.04em}
.pji summary{margin-top:8px;font-size:12px;color:#9a9a9a;list-style:none}
.pji summary::-webkit-details-marker{display:none}
.pjm{color:#9a9a9a;font-size:11px;margin-left:6px} .pjb{margin-top:6px;line-height:1.5}
.hl{display:flex;align-items:center;gap:6px;margin-top:8px;font-size:12.5px;color:#bdbdbd;line-height:1.35}
.hl i{flex:none;width:8px;height:8px;border-radius:50%}
.hl b{color:#fff;font-weight:600}
.cells b.sm{color:#9a9a9a}
.wc b.sm{color:#9a9a9a;font-weight:600}
.bkr2.alt .bl,.bkr2 .na{color:#5f5f5f}
/* capsule pills that slide to the pressed button */
.pill2{position:absolute;left:0;top:0;z-index:0;border-radius:999px;background:#313131;pointer-events:none;opacity:0;
transition:transform .36s cubic-bezier(.32,.72,0,1),opacity .2s;will-change:transform}
.tbc{position:relative}
.tbc .pill2{background:rgba(255,255,255,.13)}
.tbc button{z-index:1}
/* motion: an iOS push for the player page, springy sheets, press feedback, bars that grow in */
.shade{position:fixed;inset:0;z-index:29;background:#000;opacity:0;pointer-events:none;transition:opacity .44s cubic-bezier(.32,.72,0,1)}
.shade.on{opacity:.5}
.snap{transition:none!important}
.cb,.fc,.wc,.gc,.gc0,.mt button,.tbc button,.tbf,.muc,.lnp,.chip,.seg button,.btn,.opt,.cells button{transition:transform .16s ease,background-color .22s,color .22s}
.cb:active,.fc:active,.gc:active,.gc0:active,.tbf:active,.muc:active,.lnp:active,.chip:active,.btn:active{transform:scale(.94)}
.wc:active,.mt button:active,.tbc button:active,.seg button:active,.cells button:active{transform:scale(.92)}
.opt:active{background:rgba(255,255,255,.06)}
.cb.pop svg{animation:pop .36s cubic-bezier(.3,1.6,.5,1)}
@keyframes pop{45%{transform:scale(1.32)}}
svg.c2.grow .bv,svg.c2.grow .bm{transform-box:fill-box;transform-origin:50% 100%;animation:grow .4s cubic-bezier(.2,.8,.2,1) both;
animation-delay:var(--d)}
svg.c2.grow .vv,svg.c2.grow .vw,svg.c2.grow .mn{animation:fade .3s ease both;animation-delay:calc(var(--d) + .16s)}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes fade{from{opacity:0}}
svg.c2 g.br{transition:opacity .2s}
.rp.in{animation:rpin .3s cubic-bezier(.2,.8,.2,1)}
@keyframes rpin{from{opacity:0;transform:translateY(-8px)}}
.pr{content-visibility:auto;contain-intrinsic-size:auto 113px}
@media (prefers-reduced-motion:reduce){.sheet,.pill2,.shade{transition:none!important}svg.c2.grow *{animation:none!important}}

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
// (his games for that team since the teammate's first there, the teammate out); with = [{played, team}] (both played)
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
    for (var m = 0; m < (f.with || []).length; m++) {
      var t = f.with[m];
      if (l.team !== t.team || t.played.indexOf(l.gid) < 0) return false;
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
// the over's no-vig probability from decimal over / under prices
function noVig(o, u) {
  if (!o || !u || o <= 1 || u <= 1) return null;
  var a = 1 / o, b = 1 / u;
  return a / (a + b);
}
// {p: the over's fair probability at the line (the mean no-vig of every book pricing both sides), n: books}
function fairAt(prop, line) {
  var ps = [];
  ["fd", "dk"].forEach(function (b) { var r = rungAt(prop.books[b], line), p = r ? noVig(r[1], r[2]) : null; if (p !== null) ps.push(p); });
  return ps.length ? {p: ps.reduce(function (a, b) { return a + b; }, 0) / ps.length, n: ps.length} : {p: null, n: 0};
}
// the best price on a side against the fair probability: {ev (per $1), book, price, fair} or null
function valueAt(prop, line, side) {
  var f = fairAt(prop, line).p;
  if (f === null) return null;
  var k = side === "under" ? 2 : 1, pr = side === "under" ? 1 - f : f, best = null;
  ["fd", "dk"].forEach(function (b) { var r = rungAt(prop.books[b], line); if (r && r[k] && (!best || r[k] > best.price)) best = {book: b, price: r[k]}; });
  return best ? {ev: best.price * pr - 1, book: best.book, price: best.price, fair: pr} : null;
}
// a projection's compact pmf [start, [p...]] (nba_project.compact_pmf): P(X >= m)
function pmfGe(pm, m) {
  var s = 0;
  for (var k = 0; k < pm[1].length; k++) if (pm[0] + k >= m) s += pm[1][k];
  return s;
}
// {over, under, push} at a line from the projection's pmf (a half line cannot push) — the same arithmetic as
// nba_project.Dist.probs; the pmf's 4-decimal rounding is renormalized away
function projProbs(pm, line) {
  var tot = pmfGe(pm, -1e9), k = Math.floor(line), half = line - k > 0.25;
  var over = pmfGe(pm, k + 1) / tot, push = half ? 0 : pmfGe(pm, k) / tot - over;
  return {over: over, under: Math.max(0, 1 - over - push), push: push};
}
// the M1+mkt blend (prereg): logit((1-w) logit(p_model) + w logit(p_market))
function blendP(pModel, pMkt, w) {
  var lg = function (p) { p = Math.min(Math.max(p, 1e-6), 1 - 1e-6); return Math.log(p / (1 - p)); };
  return 1 / (1 + Math.exp(-((1 - w) * lg(pModel) + w * lg(pMkt))));
}
// how unusual `hits` in `n` games are if each hits with probability p (the price's); |z| >= 1 is what gets colored
function zscore(hits, n, p) {
  if (!n || p === null || p === undefined || !(p > 0 && p < 1)) return null;
  return (hits - n * p) / Math.sqrt(n * p * (1 - p));
}
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
// line, odds (the side's best price), value (that price against the books' fair price), player; avg10 kept for old links
function sortProps(list, key, dir, logsOf, side, season) {
  var sgn = dir === "asc" ? 1 : -1;
  side = side || "over";
  var W = {hit5: "l5", hit10: "l10", hit20: "l20", h2h: "h2h", szn: "season"};
  function val(p) {
    if (key === "player") return p.player.toLowerCase();
    if (key === "line") return p.main;
    if (key === "odds") { var b = p.main === null ? null : bestPrice(p, p.main, "all", side); return b ? b.odds : null; }
    if (key === "value") { var v = p.main === null ? null : valueAt(p, p.main, side); return v ? v.ev : null; }
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
  noVig: noVig, fairAt: fairAt, valueAt: valueAt, zscore: zscore, pmfGe: pmfGe, projProbs: projProbs, blendP: blendP,
  filterProps: filterProps, sortProps: sortProps};
"""

JS_APP = r"""
(function () {
const TEAM_ID = __TEAM_ID__;
const ORDER = ["points", "rebounds", "assists", "threes", "pra", "pts_reb", "pts_ast", "reb_ast"];
const NAME = {points: "Points", rebounds: "Rebounds", assists: "Assists", threes: "3-Pointers", pra: "Pts+Reb+Ast",
              pts_reb: "Pts+Reb", pts_ast: "Pts+Ast", reb_ast: "Reb+Ast"};
const SORTS = [["value", "Value (price vs fair)"], ["hit10", "L10 hit rate"], ["hit5", "L5 hit rate"], ["hit20", "L20 hit rate"], ["h2h", "Head-to-head hit rate"],
               ["szn", "Season hit rate"], ["avgdiff", "L10 average vs line"], ["line", "Line"], ["odds", "Best price"],
               ["player", "Player name"]];
let D = null, ERR = null, LOADING = true, CUR = null;
// on a touchscreen, moving focus by script only draws a ring (and focusing a <select> can pop its picker)
const TOUCH = matchMedia("(pointer: coarse)").matches;
const ST = {date: null, gid: "all", market: "points", side: "over", q: "", sort: "hit10", dir: "desc", team: "all",
            book: "all", lmin: "", lmax: "", omin: "", omax: "", watch: "", view: "props", iv: ""};
const DT = {line: null, win: "l10", home: null, starter: null, result: null, rest: null, ranges: {}, without: {}, with: {},
            dvp: false, def: false, open: {}, more: false, fresh: null, ovs: []};
const RANGES = [["min", "Minutes", "Minutes"], ["fga", "Field goal attempts", "FGA"], ["fg3a", "3-point attempts", "3PTA"],
                ["fta", "Free throw attempts", "FTA"], ["usg", "Usage %", "Usage%"], ["pot_ast", "Potential assists", "Potential Assists"],
                ["reb_ch", "Rebound chances", "Rebound Chances"], ["margin", "Team margin", "Margin"]];
// the range chips that also draw their stat on the chart, as white outline boxes (margin can be negative, so it only filters)
const OVL = {min: "min", fga: "FGA", fg3a: "3PTA", fta: "FTA", usg: "usage %", pot_ast: "potential assists", reb_ch: "rebound chances"};
// tracking stats only on the props they bear on
const RANGE_FOR = {pot_ast: ["assists", "pra", "pts_ast", "reb_ast"], reb_ch: ["rebounds", "pra", "pts_reb", "reb_ast"]};
const forMarket = (k, m) => !RANGE_FOR[k] || RANGE_FOR[k].indexOf(m) >= 0;
const MORE_R = ["margin"];                                        // the range chips behind More
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
const logo = (t, c) => TEAM_ID[t] ? `<img class="${c || "lg"}" alt="" decoding="async" src="https://cdn.nba.com/logos/nba/${TEAM_ID[t]}/global/D/logo.svg">` : "";
const heroSrc = pid => `https://cdn.nba.com/headshots/nba/latest/1040x760/${pid}.png`;
const head = pid => `<img class="hs" alt="" loading="lazy" src="https://cdn.nba.com/headshots/nba/latest/260x190/${pid}.png" onerror="this.style.visibility='hidden'">`;
const short = m => (D.markets || {})[m] || m;
const gameOf = gid => D.games.find(g => g.gid === gid) ||
  (String(gid).startsWith("none:") ? {gid: gid, date: D.dates[0], home: gid.slice(5), away: "", state: "none", tip: null} : undefined);
const pct = r => r === null || r === undefined ? "–" : Math.round(r * 100) + "%";
const hcls = (r, n) => r === null || r === undefined || !n ? "h0" : r >= .7 ? "h5" : r >= .6 ? "h4" : r > .4 ? "h3" : r > .3 ? "h2" : "h1";
const ord = n => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");
const CHEV = '<svg viewBox="0 0 12 20" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2 2 10l8 8"/></svg>';
function logsOf(p) {
  const pl = D.players[String(p.pid)] || VPL.get(p.pid);
  if (!pl) return [];
  if (!pl._logs) pl._logs = rowsToLogs(D.log_cols, pl.logs);
  return pl._logs;
}
function hashState() {
  const h = new URLSearchParams();
  Object.keys(ST).forEach(k => { if (ST[k] !== "" && ST[k] !== null && ST[k] !== "all") h.set(k, ST[k]); });
  if (CUR) h.set("p", CUR);
  if (MUP) h.set("mu", "1");
  return "#" + h.toString();
}
function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  Object.keys(ST).forEach(k => { if (h.has(k)) ST[k] = h.get(k); });
  if (ST.view === "watch") Object.assign(ST, {view: "props", watch: "1"});    // the old Watchlist tab, now a filter
  if (["props", "markets", "injuries"].indexOf(ST.view) < 0) ST.view = "props";
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
const MKT_TABS = ["trends", "movers", "points", "assists", "rebounds", "threes", "pra", "pts_reb", "pts_ast", "reb_ast"];
const ALL_TABS = ["trends", "movers"];          // tabs that span every market
// Trends (nba_research_score.trend_side): the L10 and L20 hit rates both 1+ SD from what the price implies, the same
// way, 8+ games each. A plain 70% L10 put a third of the slate in Trends and ignored the price.
const VIEWS = [["props", "Props"], ["markets", "Markets"], ["injuries", "Injuries"]];
const unit = m => (D.markets || {})[m] || m;
// long names shorten to an initial, as on the reference ("M. Diabaté")
const nameOf = n => n.length > 13 && n.indexOf(" ") > 0 ? n[0] + ". " + n.slice(n.indexOf(" ") + 1) : n;
const r1 = v => Math.round(v * 10) / 10;
let RATES = new Map(), ROWS = new Map();
function rates(p, side) {
  side = side || ST.side;
  const k = p.id + "|" + side;
  if (!RATES.has(k)) RATES.set(k, propRates(p, logsOf(p), side, D.season));
  return RATES.get(k);
}
// the probability the price gives `side` at `line` (the books' no-vig), or null when no book prices both sides
function fairSide(p, line, side) { const f = line === null ? null : fairAt(p, line).p; return f === null ? null : side === "under" ? 1 - f : f; }
// what hit rates are colored against: the fair probability, or on a one-sided rung (an alt ladder) the best price's
// own implied chance, margin included — so 8-for-10 at -2500 (96%) reads as a miss, not a green 80%
function chanceSide(p, line, side) {
  const f = fairSide(p, line, side);
  if (f !== null || line === null) return f;
  const b = bestPrice(p, line, "all", side);
  return b ? 1 / b.odds : null;
}
const hitsOf = x => x && x.n ? Math.round(x.rate * x.n) : 0;
function mktOver(p, line) {
  for (const b of ["fd", "dk"]) { const r = rungAt(p.books[b], line); const nv = r ? noVig(r[1], r[2]) : null; if (nv !== null) return nv; }
  return null;
}
// the projection at a line for a side: {model, blend (null without a two-sided price), push}
function projAt(p, line, side) {
  const pr = p.proj, M = D.proj_meta || {};
  if (!pr || line === null) return null;
  const q = projProbs(pr.pmf, line), cond = q.over / Math.max(q.over + q.under, 1e-9);
  const mk = mktOver(p, line), bo = mk === null || M.blend_w == null ? null : blendP(cond, mk, M.blend_w);
  const pick = x => x === null ? null : side === "under" ? 1 - x : x;
  return {model: pick(cond), blend: pick(bo), push: q.push, raw: q};
}
// every hit-rate box: the rate; under 5 games grey (too few to color), otherwise colored only when it sits 1+ SD
// from what the price implies (fs; a coin flip without a price) — a -300 favorite going 7-for-10 stays white
function hbox(x, fs) {
  if (!x || !x.n) return {t: "–", c: ""};
  const h = hitsOf(x);
  if (x.n < 5) return {t: pct(x.rate), c: "sm"};
  const z = zscore(h, x.n, fs === null || fs === undefined ? .5 : fs);
  return {t: pct(x.rate), c: z >= 1 ? "up" : z <= -1 ? "dn" : ""};
}
function trend(p) {                              // {side, z} or null — mirrors nba_research_score.trend_side
  if (p.main === null) return null;
  const f = fairAt(p, p.main).p, r = rates(p, "over");
  const z = k => r[k] && r[k].n >= 8 ? zscore(hitsOf(r[k]), r[k].n, f === null ? .5 : f) : null;
  const a = z("l10"), b = z("l20");
  if (a === null || b === null) return null;
  return a >= 1 && b >= 1 ? {side: "over", z: a + b} : a <= -1 && b <= -1 ? {side: "under", z: -a - b} : null;
}
// teammates out tonight whose absence is news (they played in one of the team's last 2 games), most minutes first
function freshOut(p) { const g = gameOf(p.gid); return p.team ? (D.absences[g.date + "|" + p.team] || []).filter(a => a.fresh && a.pid !== p.pid) : []; }
function woSplit(p, a, side) {
  const sub = filterLogs(logsOf(p), {without: [{played: a.played, since: a.since, team: p.team}]});
  const s = hitSummary(sub.map(l => statValue(l, p.market)), p.main), hits = side === "under" ? s.under : s.over;
  const fs = fairSide(p, p.main, side);
  return {hits: hits, n: s.n, z: s.n >= 5 ? zscore(hits, s.n, fs === null ? .5 : fs) : null};
}
const lastName = n => { const w = String(n || "").split(" ").filter(x => !/^(jr\.?|sr\.?|ii|iii|iv)$/i.test(x)); return w[w.length - 1] || ""; };
function moveOf(p) {                              // the main line's move since the book opened it (FanDuel, else DK)
  const bk = p.books.fd && p.books.fd.main !== null ? "fd" : "dk", h = (p.hist || {})[bk];
  if (!h || !h.length || !p.books[bk] || p.books[bk].main === null) return 0;
  return Math.round((p.books[bk].main - h[0][1]) * 2) / 2;
}
// a line on the move: its main line's move since the book opened it (moveOf), or FanDuel and DraftKings posting different
// main lines; k ranks them (a half-point move outranks any gap)
function mover(p) {
  const mv = moveOf(p), fd = p.books.fd, dk = p.books.dk;
  const gap = fd && dk && fd.main !== null && dk.main !== null ? Math.abs(fd.main - dk.main) : 0;
  return mv || gap ? {mv: mv, gap: gap, k: Math.abs(mv) * 100 + gap} : null;
}
function availMarkets() {
  const m = {};
  D.props.forEach(p => { const g = gameOf(p.gid); if (g && g.date === ST.date) m[p.market] = 1; });
  return ORDER.filter(k => m[k]);
}
function filtersOn() { return ["team", "book"].filter(k => ST[k] !== "all").length + ["lmin", "lmax", "omin", "omax", "watch"].filter(k => ST[k] !== "").length + (ST.side === "under" ? 1 : 0); }
function listProps() {
  const st = Object.assign({}, ST, {market: ALL_TABS.indexOf(ST.market) >= 0 ? "all" : ST.market});
  let list = filterProps(D.props, st, gameOf, logsOf);
  if (ST.watch) { const f = favs(); list = list.filter(p => f.indexOf(p.pid) >= 0); }
  // Movers: the biggest line move since open first, then the widest FanDuel / DraftKings gap
  if (ST.market === "movers") return list.map(p => [p, mover(p)]).filter(x => x[1]).sort((a, b) => b[1].k - a[1].k).map(x => x[0]);
  // Trends: strongest first
  if (ST.market === "trends") return list.map(p => [p, trend(p)]).filter(x => x[1] && x[1].side === ST.side).sort((a, b) => b[1].z - a[1].z).map(x => x[0]);
  return sortProps(list, ST.sort, ST.dir, logsOf, ST.side, D.season);
}
function row(p) {
  const g = gameOf(p.gid), r = rates(p), c = p.ctx || {}, side = ST.side;
  const best = p.main === null ? null : bestPrice(p, p.main, ST.book, side), fs = fairSide(p, p.main, side), cs = chanceSide(p, p.main, side);
  const cell = (lab, k) => { const h = hbox(r[k], cs); return `<div><i>${lab}</i><b class="${h.c}">${h.t}</b></div>`; };
  const dv = c.dvp_rank ? `<b class="${{good: "up", bad: "dn", mid: "md"}[rankCls(c.dvp_rank, c.teams, side)]}">${ord(c.dvp_rank)}</b>` : "<b>–</b>";
  // VALUE: the price shown against the books' fair price for that side (positive only when one book beats the other)
  const ev = best && fs !== null ? best.odds * fs - 1 : null;
  const live = p.live && g.state !== "pregame" ? `<span class="tg ${g.state === "live" ? "tl" : "tn"}">${g.state === "live" ? "LIVE" : "FINAL"} ${p.live.value}</span>` : "";
  const mv = moveOf(p), out = p.main === null ? null : freshOut(p)[0];
  const wo = out ? woSplit(p, out, side) : null;
  const fd = p.books.fd, dk = p.books.dk;
  const differ = fd && dk && fd.main !== null && dk.main !== null && fd.main !== dk.main ? `DK ${dk.main}` : null;
  return `<button class="pr" data-id="${esc(p.id)}"><span class="av">${head(p.pid)}</span>
    <div class="who"><div class="nm">${esc(nameOf(p.player))}<span class="cd">${esc(p.team || "")}</span>${injTag(p)}${live}${p.flag ? '<span class="tg tf">ENGINE</span>' : ""}</div>
    <div class="lin num">${ST.market === "movers" && mv ? `<span class="mvo">${r1(p.main - mv)} →</span> ${p.main} ${esc(unit(p.market))}<span class="mv ${mv > 0 ? "up" : "dn"}">${mv > 0 ? "▲" : "▼"}${Math.abs(mv)}</span>` : (p.main === null ? "alt lines" : p.main + " " + esc(unit(p.market))) + (ST.market === "movers" ? "" : `${p.proj ? `<span class="pjm" title="model projection (mean), not a book line">proj ${(+p.proj.mean).toFixed(1)}</span>` : ""}${mv ? `<span class="mv" aria-label="line ${mv > 0 ? "up" : "down"} ${Math.abs(mv)} since open">${mv > 0 ? "▲" : "▼"}${Math.abs(mv)}</span>` : ""}${wo ? `<span class="pl ${wo.z === null ? "" : wo.z >= 1 ? "up" : wo.z <= -1 ? "dn" : ""}" title="${esc(out.name || "")} is ${esc(out.status)}: his ${side} hit rate without him">W/O ${esc(lastName(out.name).slice(0, 10))}${wo.n ? " " + wo.hits + "/" + wo.n : ""}</span>` : ""}`)}</div></div>
    <div class="oc o"><i${differ ? ' class="df" title="the books post different main lines"' : ""}>${differ || "ODDS"}</i><b class="num">${best ? american(best.odds) : "–"}</b></div>
    <div class="oc e"><i>VALUE</i><b class="num ${ev === null ? "" : ev > 0 ? "up" : "mu"}">${ev === null ? "–" : (ev > 0 ? "+" : "") + (ev * 100).toFixed(1) + "%"}</b></div>
    <div class="bx6 num" aria-label="Hit rates">${cell(D.season.slice(0, 4), "season")}${cell("H2H", "h2h")}<div><i>DvP</i>${dv}</div>${cell("L5", "l5")}${cell("L10", "l10")}${cell("L20", "l20")}</div></button>`;
}
function mrow(p) {
  const line = p.main;
  const bo = line === null ? null : bestPrice(p, line, "all", "over"), bu = line === null ? null : bestPrice(p, line, "all", "under");
  const px = b => {
    const q = p.books[b], r = q && line !== null ? rungAt(q, line) : null;
    if (!q) return '<div class="mp"><span class="na">—</span></div>';
    if (!r) { const m = rungAt(q, q.main); return m ? `<div class="mp"><span class="na">${q.main}: ${american(m[1])}</span><span class="na">${american(m[2])}</span></div>` : '<div class="mp"><span class="na">—</span></div>'; }
    return `<div class="mp"><span class="${bo && bo.book === b ? "best" : ""}">O ${american(r[1])}</span><span class="${bu && bu.book === b ? "best" : ""}">U ${american(r[2])}</span></div>`;
  };
  return `<button class="mrw" data-id="${esc(p.id)}"><div><div class="nm">${esc(nameOf(p.player))}<span class="cd">${esc(p.team || "")}</span></div><div class="lin">${line === null ? "alt lines" : line + " " + esc(unit(p.market))} · ${esc(vs(p))}</div></div>${px("fd")}${px("dk")}</button>`;
}
function banners() {
  const out = [], b = D.sources.books;
  [["fd", "FanDuel"], ["dk", "DraftKings"]].forEach(([k, n]) => {
    if (b[k] && b[k].stale) out.push(`${n} prices ${Math.round(b[k].age_min)} min old`);
  });
  if ((Date.now() - iso(D.generated_at).getTime()) / 60000 > 10) out.push("Feed delayed");
  return out.map(t => `<div class="ban" role="status">${esc(t)}</div>`).join("");
}
function topRow() {
  return `<div class="lh-r"><button class="cb tx" id="lgb" aria-haspopup="dialog" aria-label="League and data">NBA</button>
    <label class="sx${ST.q ? " has" : ""}">${ICON.search}<span class="ph3" aria-hidden="true">Search <b>Pickz</b></span><input id="q" type="search" enterkeyhint="search" aria-label="Search players or teams" autocomplete="off" autocorrect="off" spellcheck="false" value="${esc(ST.q)}"><button class="clr" id="qx" aria-label="Clear search"${ST.q ? "" : " hidden"}>×</button></label>
    <button class="cb tx" id="dvpb" aria-haspopup="dialog" aria-label="Defense vs position">DvP</button></div>`;
}
function cards() {
  const gs = D.games.filter(g => g.date === ST.date), i = D.dates.indexOf(ST.date);
  const lab = i === 0 ? "Today" : i === 1 ? "Tomorrow" : ST.date.slice(5).replace("-", "/");
  return `<button class="gc0" id="dayb" aria-haspopup="dialog"><i>${lab}</i><i>${gs.length} GAME${gs.length === 1 ? "" : "S"}</i></button>` +
    gs.map(g => `<button class="gc" data-gid="${g.gid}" aria-pressed="${g.gid === ST.gid}" aria-label="${esc(g.away)} at ${esc(g.home)}"><span class="gt"><span>${logo(g.away, "")}${esc(g.away)}</span><span>${logo(g.home, "")}${esc(g.home)}</span></span><em>${g.state === "live" ? '<span class="lv">LIVE</span>' : g.state === "final" ? "Final" : g.state === "postponed" ? "PPD" : mt(g.tip).replace(" ", "\u200a")}</em></button>`).join("");
}
// a pill under the pressed button of a capsule, moved with a transform so a tap slides it across
function slide(box, instant) {
  const pill = box && $(".pill2", box), b = box && $('[aria-pressed="true"]', box);
  if (!pill) return;
  if (!b) { pill.style.opacity = 0; return; }
  if (instant) pill.style.transition = "none";
  const w = +box.dataset.pw || b.offsetWidth;
  pill.style.width = w + "px"; pill.style.height = b.offsetHeight + "px";
  pill.style.transform = `translate(${b.offsetLeft + (b.offsetWidth - w) / 2}px,${b.offsetTop}px)`; pill.style.opacity = 1;
  if (instant) { void pill.offsetWidth; pill.style.transition = ""; }
}
function press(sel, test, root) { $$(sel, root).forEach(b => b.setAttribute("aria-pressed", test(b))); }
function render() {
  const app = $("#app");
  if (!D) {
    app.innerHTML = '<header class="lh"><div class="lh-r"><button class="cb tx">NBA</button><div class="sx"><span class="ph3">Search <b>Pickz</b></span></div><button class="cb tx">DvP</button></div></header>' +
      (LOADING ? '<main class="lst" aria-busy="true">' + '<div class="sk"></div>'.repeat(7) + "</main>"
      : '<div class="empty" role="alert"><b>Couldn\'t load props</b>' + esc(ERR) + '<br><button class="btn pri" id="retry">Try again</button></div>');
    const r = $("#retry"); if (r) r.onclick = load;
    return;
  }
  if (!ST.date || D.dates.indexOf(ST.date) < 0) ST.date = D.dates.find(d => D.props.some(p => (gameOf(p.gid) || {}).date === d)) || D.dates[0];
  const mks = availMarkets();
  if (ALL_TABS.indexOf(ST.market) < 0 && mks.length && mks.indexOf(ST.market) < 0) ST.market = mks[0];
  if (!$("#lt")) {
    app.innerHTML = `<header class="lh"><div id="lt">${topRow()}</div><nav class="mt ml" aria-label="Markets"><div class="mt-in" id="mtl"></div></nav>
      <nav class="gcs" id="gcs" aria-label="Games"></nav><div class="ldv"></div></header><div id="ban"></div><main class="lst" id="lst"></main>`;
    bindTop();
  }
  $("#mtl").innerHTML = '<span class="pill2"></span>' + MKT_TABS.filter(m => ALL_TABS.indexOf(m) >= 0 || mks.indexOf(m) >= 0).map(m => `<button data-market="${m}" aria-pressed="${m === ST.market}">${TAB[m]}</button>`).join("");
  $("#gcs").innerHTML = cards();
  $("#ban").innerHTML = banners();
  bindHead();
  slide($("#mtl"), true);
  renderList();
  tabbar();
}
function renderList() {
  renderRows();
  const q = ST.q.trim();
  if (ST.view !== "injuries" && q.length >= 2) searchPlayers(q);
}
// the players a search finds, prop or not, under the props it finds; a tap opens his prop or his player page
function searchPlayers(q) {
  const n = ++SRCH_N;
  playerIndex().then(pl => {
    const lst = $("#lst");
    if (n !== SRCH_N || ST.q.trim() !== q || ST.view === "injuries" || !lst) return;
    const k = q.toLowerCase(), hits = pl.filter(r => r[1].toLowerCase().indexOf(k) >= 0 || r[2].toLowerCase() === k).slice(0, 15);
    const old = $("#vpl", lst); if (old) old.remove();
    if (!hits.length) return;
    const box = document.createElement("div");
    box.id = "vpl";
    box.innerHTML = '<div class="lhd"><span>Players</span></div>' + hits.map(([pid, name, team, pos]) =>
      `<button class="pr ir ir0 vpr" data-vp="${pid}"><span class="av">${head(pid)}</span><div class="who"><div class="nm">${esc(nameOf(name))}<span class="cd">${esc(team)}</span></div>
        <div class="lin">${esc(POSN[pos] || pos || "")}</div></div><span class="vgo">›</span></button>`).join("");
    lst.appendChild(box);
  });
}
function renderRows() {
  const lst = $("#lst"), ml = $(".ml");
  if (ml) ml.style.display = ST.view === "injuries" ? "none" : "";
  if (ST.view === "injuries") {
    lst.innerHTML = `<div class="seg ivs" role="group" aria-label="Show"><span class="pill2"></span><button data-iv="" aria-pressed="${ST.iv !== "lu"}">Injuries</button><button data-iv="lu" aria-pressed="${ST.iv === "lu"}">Lineups</button></div>` +
      (ST.iv === "lu" ? lineupsView() : injView());
    slide($(".ivs", lst), true);
    $$("[data-iv]", lst).forEach(b => b.onclick = () => { if (ST.iv !== b.dataset.iv) { ST.iv = b.dataset.iv; save(); renderList(); } });
    return;
  }
  const onDate = D.props.filter(p => (gameOf(p.gid) || {}).date === ST.date), list = listProps();
  let body = null;
  if (!D.games.some(g => g.date === ST.date)) body = '<div class="empty"><b>No games</b></div>';
  else if (!onDate.length) body = '<div class="empty"><b>No props yet</b></div>';
  else if (ST.gid !== "all" && !onDate.some(p => p.gid === ST.gid)) body = '<div class="empty"><b>No props for this game yet</b></div>';
  else if (!list.length && ST.q.trim().length >= 2) body = '<div class="lhd"><span>No props</span></div>';
  else if (!list.length) body = ST.watch ? '<div class="empty"><b>Watchlist empty</b><button class="btn" id="reset2">Reset filters</button></div>'
    : ST.market === "trends" ? '<div class="empty"><b>No trends</b></div>'
    : ST.market === "movers" ? '<div class="empty"><b>No movers</b></div>'
    : '<div class="empty"><b>No matches</b><button class="btn" id="reset2">Reset filters</button></div>';
  if (body) { lst.innerHTML = body; const r2 = $("#reset2"); if (r2) r2.onclick = resetFilters; return; }
  if (ST.view === "markets") {
    lst.innerHTML = '<div class="mhd"><span>PLAYER</span><span>FANDUEL</span><span>DRAFTKINGS</span></div>' + list.map(mrow).join("");
    return;
  }
  // rows are built once per prop and side, then reused: re-sorting or switching tabs never re-decodes the headshots
  const frag = document.createDocumentFragment();
  if (ALL_TABS.indexOf(ST.market) >= 0) {
    const h = document.createElement("div");
    h.className = "lhd";
    h.innerHTML = `<span>${list.length} props</span><button class="lk" id="scb">Scorecard ›</button>`;
    $("#scb", h).onclick = scoreSheet;
    frag.appendChild(h);
  }
  list.forEach(p => {
    const k = p.id + "|" + ST.side + "|" + ST.book + (ST.market === "movers" ? "|mv" : "");
    let e = ROWS.get(k);
    if (!e) { const t = document.createElement("template"); t.innerHTML = row(p).trim(); e = t.content.firstChild; ROWS.set(k, e); }
    frag.appendChild(e);
  });
  lst.replaceChildren(frag);
}
// ── injuries: the slate's listed rotation players (10+ minutes a game; Out, Doubtful, Questionable), most relevant
// first. Boxes, from the games he missed for his team (nba_research.injury_report): for a starter, who started in his
// place (or by position, with no such games); then the teammates who gained the most minutes a game without him.
const INJ_C = {Out: "to", Doubtful: "to", Questionable: "tq"};
const INJ_S = {Out: "OUT", Doubtful: "DOUBT", Questionable: "Q"};
const INJ_P = {Out: 1, Doubtful: .9, Questionable: .4};          // the chance he sits, until the report has a record
const injReason = r => String(r || "").replace(/^Injury\/Illness\s*-\s*/i, "").replace(/^G League\s*-\s*/i, "G League · ").replace(/;\s*/g, " ");
const injRot = e => e.mpg !== null && e.mpg >= 10;
function injSits(status) {                       // how often players listed so have sat since 10/22 (proj_meta.availability)
  const a = ((D.proj_meta || {}).availability || {})[status];
  return status === "Out" ? 1 : a && a[1] >= 10 ? 1 - (a[0] + 1) / (a[1] + 2) : INJ_P[status] || 0;
}
// relevance: minutes a game x the chance he sits, halved when he has no game this season (the team is used to it)
const injImpact = e => (e.mpg || 0) * injSits(e.status) * (e.season === D.season ? 1 : .5);
function injList() {
  const q = ST.q.trim().toLowerCase(), out = [];
  D.games.filter(g => g.date === ST.date && (ST.gid === "all" || g.gid === ST.gid)).forEach(g => [g.away, g.home].forEach(t => {
    if (ST.team !== "all" && t !== ST.team) return;
    (((D.inj_report || {})[g.date + "|" + t] || {}).players || []).forEach(e => {
      if (!injRot(e) || !INJ_P[e.status]) return;
      const names = [e.name].concat(e.minutes.map(m => m.name), e.starts ? [e.starts.name] : []);
      if (q && t.toLowerCase() !== q && !names.some(n => n.toLowerCase().indexOf(q) >= 0)) return;
      out.push(Object.assign({team: t}, e));
    });
  }));
  return out.sort((a, b) => injImpact(b) - injImpact(a));
}
function injProp(pid) {                          // tonight's prop for a teammate in a box, points first
  return D.props.filter(p => p.pid === pid && (gameOf(p.gid) || {}).date === ST.date)
    .sort((a, b) => ORDER.indexOf(a.market) - ORDER.indexOf(b.market))[0] || null;
}
// a box: the teammate on top, what he took below (a start, from k of n games or "?" by position; or minutes a game)
function injBox(m, val, cls) {
  const p = injProp(m.pid), tag = p ? "button" : "div";
  return `<${tag} class="ijb"${p ? ` data-id="${esc(p.id)}"` : ""}><i>${esc(m.name)}</i><b class="${cls}">${val}</b></${tag}>`;
}
function injRow(e) {
  const bx = [], s = e.starts;
  if (s) bx.push(injBox(s, s.how === "games" ? `Starts <small>${s.k}/${s.n}</small>` : "Starts?", s.how === "games" ? "" : "sm"));
  e.minutes.filter(m => !s || m.pid !== s.pid).forEach(m => bx.push(injBox(m, "+" + m.gain.toFixed(1), "up")));   // one box a player
  const tags = `<span class="tg ${INJ_C[e.status]}">${INJ_S[e.status]}</span>${e.fresh ? '<span class="tg tf">NEW</span>' : ""}`;
  return `<div class="pr ir${bx.length ? "" : " ir0"}" data-vp="${e.pid}"><span class="av">${head(e.pid)}</span>
    <div class="who"><div class="nm">${esc(nameOf(e.name))}<span class="cd">${esc(e.team)}</span>${tags}</div>
    <div class="lin">${e.starter ? "Starter" : "Bench"}${e.reason ? " · " + esc(injReason(e.reason)) : ""}</div></div>
    <div class="oc o"><i>${e.season && e.season !== D.season ? "MPG " + esc(e.season.slice(2)) : "MPG"}</i><b class="num">${e.mpg.toFixed(1)}</b></div>
    <div class="oc e"><i>MISSED</i><b class="num">${e.missed}</b></div>
    ${bx.length ? `<div class="bx4">${bx.slice(0, 4).join("")}</div>` : ""}</div>`;
}
function injView() {
  if (!D.games.some(g => g.date === ST.date)) return '<div class="empty"><b>No games</b></div>';
  const rep = (D.sources.report || {})[ST.date];
  if (!rep) return '<div class="empty"><b>No injury report yet</b></div>';
  const list = injList();
  return `<div class="lhd"><span>${list.length} players</span><span>Report ${esc(mt(rep.published, true))}</span></div>` +
    (list.length ? list.map(injRow).join("") : '<div class="empty"><b>No injuries</b></div>');
}
// ── lineups (nba_research.lineups, NBA.com's daily lineups): each team's five, Confirmed or Expected; a starter outside its
// usual five (its most frequent over the last 10 games) marked NEW, a usual starter not starting listed with his report
// status, the inactive list; a tap opens the player ──
function lineupsView() {
  const gs = D.games.filter(g => g.date === ST.date && (ST.gid === "all" || g.gid === ST.gid)), L = D.lineups || {};
  if (!gs.length) return '<div class="empty"><b>No games</b></div>';
  if (!gs.some(g => L[g.date + "|" + g.home] || L[g.date + "|" + g.away])) return '<div class="empty"><b>Lineups not posted yet</b></div>';
  return gs.map(g => `<div class="lug"><div class="lugh"><span>${esc(g.away)} @ ${esc(g.home)}</span><span>${when(g)}</span></div>${[g.away, g.home].map(t => luTeam(t, L[g.date + "|" + t])).join("")}</div>`).join("");
}
function luTeam(t, e) {
  if (!e) return `<div class="lut"><div class="luth">${logo(t, "")}<b>${esc(t)}</b><span class="tg tn">NOT POSTED</span></div></div>`;
  const usual = new Set(e.usual), isNew = pid => usual.size > 0 && !usual.has(pid);
  const tiles = e.starters.map(([pid, name, pos]) => `<button class="lus${isNew(pid) ? " new" : ""}" data-vp="${pid}"><span class="av">${head(pid)}</span><b>${esc(lastName(name))}</b><i>${esc(pos)}${isNew(pid) ? " · NEW" : ""}</i></button>`).join("");
  const miss = e.missing.length ? `<div class="lum"><b>Not starting</b>${e.missing.map(([pid, name, st]) => `<button data-vp="${pid}">${esc(nameOf(name))}</button>${st ? `<span class="tg ${INJ_C[st] || "tn"}">${INJ_S[st] || esc(String(st).toUpperCase())}</span>` : ""}`).join(", ")}</div>` : "";
  const ina = e.inactive.length ? `<div class="lum"><b>Inactive</b>${e.inactive.map(([, name]) => esc(nameOf(name))).join(", ")}</div>` : "";
  const ok = e.status === "Confirmed";
  return `<div class="lut"><div class="luth">${logo(t, "")}<b>${esc(t)}</b><span class="tg ${ok ? "tp" : "tq"}">${ok ? "CONFIRMED" : "EXPECTED"}</span>${ok && e.at ? `<em>${esc(mt(e.at))}</em>` : ""}</div>
    <div class="lur">${tiles}</div>${miss}${ina}</div>`;
}
function tabbar() {
  const tb = $("#tb"), fo = filtersOn();
  if (!$(".tbc", tb)) tb.innerHTML = `<div class="tbc glass" role="group" aria-label="Views" data-pw="72"><span class="pill2"></span>${VIEWS.map(([k, l]) => `<button data-view="${k}" aria-pressed="${ST.view === k}">${ICON[k]}<span>${l}</span></button>`).join("")}</div><button class="tbf glass" id="filtb" aria-haspopup="dialog" aria-label="Sort and filter"></button>`;
  press("[data-view]", b => b.dataset.view === ST.view, tb);
  $("#filtb").innerHTML = ICON.menu + (fo ? `<b>${fo}</b>` : "");
  $$("[data-view]", tb).forEach(b => b.onclick = () => { if (ST.view === b.dataset.view) { window.scrollTo({top: 0, behavior: "smooth"}); return; } ST.view = b.dataset.view; save(); tabbar(); renderList(); window.scrollTo(0, 0); });
  $("#filtb").onclick = filterSheet;
  slide($(".tbc", tb), !tb.dataset.on); tb.dataset.on = 1;
}
function bindTop() {
  const q = $("#q"), sx = q.closest(".sx"), qx = $("#qx");
  let t = null;
  q.oninput = () => { ST.q = q.value; sx.classList.toggle("has", !!ST.q); qx.hidden = !ST.q; clearTimeout(t); t = setTimeout(() => { save(); renderList(); }, 90); };
  q.onkeydown = e => { if (e.key === "Enter") q.blur(); };
  qx.onclick = e => { e.preventDefault(); q.value = ""; q.oninput(); };
  $("#lgb").onclick = leagueSheet;
  $("#dvpb").onclick = () => dvpSheet();
}
function bindHead() {
  $$("[data-market]").forEach(b => b.onclick = () => { if (ST.market === b.dataset.market) return; ST.market = b.dataset.market; save(); press("[data-market]", x => x === b); slide($("#mtl")); renderList(); });
  $$("[data-gid]").forEach(b => b.onclick = () => { ST.gid = ST.gid === b.dataset.gid ? "all" : b.dataset.gid; save(); press("[data-gid]", x => x.dataset.gid === ST.gid); renderList(); });
  $("#dayb").onclick = daySheet;
}
function resetFilters() { Object.assign(ST, {team: "all", book: "all", lmin: "", lmax: "", omin: "", omax: "", watch: "", q: "", gid: "all"}); const q = $("#q"); if (q) { q.value = ""; q.closest(".sx").classList.remove("has"); $("#qx").hidden = true; } save(); render(); }
// ── sheets ──
let SHEET_FOCUS = null, SHEET_T = null, SHEET_N = 0;
function openSheet(html, bind) {
  SHEET_FOCUS = document.activeElement;
  const s = $("#sheet"), sc = $("#scrim");
  clearTimeout(SHEET_T);
  SHEET_N++; delete s.dataset.kind; delete s.dataset.closing; s.getAnimations().forEach(a => a.cancel());
  s.innerHTML = '<div class="grab" aria-hidden="true"></div>' + html;
  s.style.transform = "";
  s.classList.remove("on");
  s.hidden = sc.hidden = false;
  s.scrollTop = 0;
  bind(s);
  // as with the player page: lay out first, then rise as a Web Animation (the timer covers a background tab)
  const go = () => {
    if (s.hidden || s.classList.contains("on")) return;
    s.classList.add("on"); sc.classList.add("on");
    if (!REDUCED && !document.hidden) s.animate([{transform: "translateY(100%)"}, {transform: "none"}], {duration: 420, easing: EASE});
  };
  requestAnimationFrame(() => requestAnimationFrame(go)); setTimeout(go, 150);
  const f = TOUCH ? s : s.querySelector("button, select, input, [tabindex]"); if (f) f.focus({preventScroll: true});
}
function closeSheet() {
  const s = $("#sheet"), sc = $("#scrim");
  if (s.hidden || s.dataset.closing) return;
  const from = s.style.transform || "none";
  s.dataset.closing = 1;
  s.classList.remove("on"); sc.classList.remove("on"); s.style.transform = "";
  const n = SHEET_N, done = () => { if (n !== SHEET_N || !s.dataset.closing) return; delete s.dataset.closing; s.hidden = sc.hidden = true; s.innerHTML = ""; };
  // the timer also ends it where animations are held (a background tab), so a clear scrim can never be left blocking taps
  if (REDUCED || document.hidden) done();
  else { s.animate([{transform: from}, {transform: "translateY(100%)"}], {duration: 340, easing: EASE}).finished.then(done, done); SHEET_T = setTimeout(done, 400); }
  if (!TOUCH && SHEET_FOCUS && document.body.contains(SHEET_FOCUS)) SHEET_FOCUS.focus({preventScroll: true});
}
// drag a sheet down from its top (or anywhere once it is scrolled to the top) to dismiss it
function sheetDrag() {
  const s = $("#sheet");
  let y0 = null, t0 = 0, dy = 0, live = false;
  s.addEventListener("touchstart", e => {
    if (e.touches.length !== 1 || s.scrollTop > 0 || e.target.closest(".dual,.dual2,select,input")) { y0 = null; return; }
    y0 = e.touches[0].clientY; t0 = e.timeStamp; dy = 0; live = false;
  }, {passive: true});
  s.addEventListener("touchmove", e => {
    if (y0 === null) return;
    dy = e.touches[0].clientY - y0;
    if (!live && dy > 6 && s.scrollTop <= 0) { live = true; s.classList.add("drag"); }
    if (live) { e.preventDefault(); s.style.transform = `translateY(${Math.max(0, dy)}px)`; $("#scrim").style.opacity = Math.max(0, 1 - dy / 400); }
  }, {passive: false});
  const end = e => {
    if (y0 === null) return;
    y0 = null;
    if (!live) return;
    s.classList.remove("drag"); $("#scrim").style.opacity = "";
    const v = dy / Math.max(1, e.timeStamp - t0);
    if (dy > 110 || v > .45) closeSheet();
    else { const from = s.style.transform; s.style.transform = ""; if (!REDUCED) s.animate([{transform: from}, {transform: "none"}], {duration: 300, easing: EASE}); }
  };
  s.addEventListener("touchend", end); s.addEventListener("touchcancel", end);
}
function filterSheet() {
  const dr = Object.assign({}, ST), teams = {};
  D.props.forEach(p => { if ((gameOf(p.gid) || {}).date === ST.date && p.team) teams[p.team] = 1; });
  const opt = (v, lab, cur) => `<option value="${v}"${v === cur ? " selected" : ""}>${esc(lab)}</option>`;
  openSheet(`<h2 id="sht">Sort &amp; filter</h2>
    <div class="sg"><span>Side</span><div class="seg" role="group" aria-label="Side"><button data-sd="over" aria-pressed="${dr.side === "over"}">Over</button><button data-sd="under" aria-pressed="${dr.side === "under"}">Under</button></div></div>
    <div class="sg"><span>Show</span><div class="seg" role="group" aria-label="Show"><button data-wl="" aria-pressed="${!dr.watch}">All</button><button data-wl="1" aria-pressed="${!!dr.watch}">${ICON.star}Watchlist</button></div></div>
    <div class="sg"><span>Sort by</span><div class="chips">${SORTS.map(([k, lab]) => `<button class="chip" data-sort="${k}" aria-pressed="${k === dr.sort}">${lab.replace(" hit rate", "").replace("Head-to-head", "H2H")}<span class="ar">${k === dr.sort ? (dr.dir === "desc" ? " ↓" : " ↑") : ""}</span></button>`).join("")}</div></div>
    <label class="fl"><span>Team</span><select id="f-team">${opt("all", "All teams", dr.team)}${Object.keys(teams).sort().map(t => opt(t, t, dr.team)).join("")}</select></label>
    <label class="fl"><span>Sportsbook</span><select id="f-book">${opt("all", "FanDuel and DraftKings", dr.book)}${opt("fd", "FanDuel", dr.book)}${opt("dk", "DraftKings", dr.book)}</select></label>
    <div class="two"><label class="fl"><span>Line from</span><input id="f-lmin" type="number" inputmode="decimal" step="0.5" value="${esc(dr.lmin)}"></label>
    <label class="fl"><span>Line to</span><input id="f-lmax" type="number" inputmode="decimal" step="0.5" value="${esc(dr.lmax)}"></label></div>
    <div class="two"><label class="fl"><span>Odds from</span><input id="f-omin" type="number" inputmode="numeric" placeholder="-200" value="${esc(dr.omin)}"></label>
    <label class="fl"><span>Odds to</span><input id="f-omax" type="number" inputmode="numeric" placeholder="+150" value="${esc(dr.omax)}"></label></div>
    <div class="acts stk"><button class="btn" id="f-reset">Reset</button><button class="btn pri" id="f-ok"></button></div>`, s => {
    const read = () => { dr.team = $("#f-team", s).value; dr.book = $("#f-book", s).value; ["lmin", "lmax", "omin", "omax"].forEach(k => dr[k] = $("#f-" + k, s).value); };
    const upd = () => { read(); const f = favs(), n = sortProps(filterProps(D.props, Object.assign({}, dr, {market: ALL_TABS.indexOf(dr.market) >= 0 ? "all" : dr.market}), gameOf, logsOf).filter(p => !dr.watch || f.indexOf(p.pid) >= 0), dr.sort, dr.dir, logsOf, dr.side, D.season).length; $("#f-ok", s).textContent = ALL_TABS.indexOf(ST.market) >= 0 ? "Apply" : `Show ${n} prop${n === 1 ? "" : "s"}`; };
    $$("[data-sd]", s).forEach(b => b.onclick = () => { dr.side = b.dataset.sd; press("[data-sd]", x => x === b, s); upd(); });
    $$("[data-wl]", s).forEach(b => b.onclick = () => { dr.watch = b.dataset.wl; press("[data-wl]", x => x === b, s); upd(); });
    $$("[data-sort]", s).forEach(b => b.onclick = () => {
      const k = b.dataset.sort;
      if (k === dr.sort) dr.dir = dr.dir === "desc" ? "asc" : "desc"; else { dr.sort = k; dr.dir = k === "player" || k === "line" ? "asc" : "desc"; }
      press("[data-sort]", x => x.dataset.sort === dr.sort, s); $$("[data-sort] .ar", s).forEach(a => a.textContent = a.parentNode.dataset.sort === dr.sort ? (dr.dir === "desc" ? " ↓" : " ↑") : "");
    });
    $$("select,input", s).forEach(e => e.onchange = e.oninput = upd);
    $("#f-ok", s).onclick = () => { read(); Object.assign(ST, {side: dr.side, sort: dr.sort, dir: dr.dir, team: dr.team, book: dr.book, lmin: dr.lmin, lmax: dr.lmax, omin: dr.omin, omax: dr.omax, watch: dr.watch}); save(); closeSheet(); renderList(); tabbar(); };
    $("#f-reset", s).onclick = () => { Object.assign(ST, {side: "over", sort: "hit10", dir: "desc"}); closeSheet(); resetFilters(); };
    upd();
  });
}
function daySheet() {
  openSheet('<h2 id="sht">Day</h2>' + D.dates.filter(d => /^\d{4}-/.test(d)).map((d, i) => {
    const n = D.games.filter(g => g.date === d).length;
    return `<button class="opt" data-date="${d}"><span>${i === 0 ? "Today" : i === 1 ? "Tomorrow" : d} · ${n} game${n === 1 ? "" : "s"}</span><span class="ck">${d === ST.date ? "✓" : ""}</span></button>`;
  }).join(""), s => {
    $$("[data-date]", s).forEach(b => b.onclick = () => { if (ST.date !== b.dataset.date) { ST.date = b.dataset.date; ST.gid = "all"; save(); render(); } closeSheet(); });
  });
}
// what the nightly replay (nba_research_score.py) found: each of the page's signals against what the price said
function scoreSheet() {
  openSheet('<h2 id="sht">Scorecard <span class="tg tf">NOT A BET</span></h2><div class="note" style="font-size:14px">Loading…</div>', () => {});
  const s = $("#sheet"), n = SHEET_N;
  s.dataset.kind = "score";
  const fill = html => { if (SHEET_N === n && !s.hidden) { s.innerHTML = '<div class="grab" aria-hidden="true"></div><h2 id="sht">Scorecard <span class="tg tf">NOT A BET</span></h2>' + html; const d = $("#sc-ok", s); if (d) d.onclick = closeSheet; } };
  const pc = x => (x * 100).toFixed(1) + "%";
  fetch("nba_research_score.json?t=" + Date.now(), {cache: "no-store"}).then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(j => {
    if (!j.props) { fill('<div class="empty"><b>No graded games yet</b></div><div class="acts"><button class="btn pri" id="sc-ok">Done</button></div>'); return; }
    const b = j.brier || {};
    const rows = j.signals.map(x => `<div class="scr"><div><b>${esc(x.signal)}</b></div><div class="num">${x.n ? `${x.n}<span>picks</span>` : "–"}</div><div class="num">${x.n ? `${pc(x.rate)}<span>vs ${pc(x.implied)}</span>` : "–"}</div><div class="num ${x.roi > 0 ? "up" : x.roi < 0 ? "mu" : ""}">${x.n ? (x.roi > 0 ? "+" : "") + pc(x.roi) : "–"}</div><div><i class="vd ${x.verdict === "helps" ? "g" : x.verdict === "hurts" ? "r" : ""}">${esc(x.verdict)}</i></div></div>`).join("");
    fill(`<div class="sst"><div><b class="num">${j.props.toLocaleString()}</b><i>props</i></div><div><b class="num">${j.nights}</b><i>nights</i></div><div><b class="num">${esc(j.from.slice(5).replace("-", "/"))}–${esc(j.to.slice(5).replace("-", "/"))}</b><i>graded</i></div></div>
      <div class="scr hd"><div>Signal</div><div>Picks</div><div>Won vs price</div><div>Return</div><div></div></div>${rows}
      <div class="sg"><span>Accuracy · lower is better</span></div><div class="kv"><span>Price</span><b class="num">${b["price (no-vig)"]}</b></div><div class="kv"><span>L10 hit rate</span><b class="num">${b["L10 hit rate"]}</b></div><div class="kv"><span>Coin flip</span><b class="num">${b["coin flip"]}</b></div>
      <div class="acts"><button class="btn pri" id="sc-ok">Done</button></div>`);
  }).catch(e => fill(`<div class="note" style="font-size:14px">Couldn't load the scorecard (${esc(e.message || e)}).</div><div class="acts"><button class="btn pri" id="sc-ok">Done</button></div>`));
}
function leagueSheet() {
  const b = D.sources.books, bk = k => b[k] ? (b[k].stale ? `${Math.round(b[k].age_min)} min old` : "live") : "—";
  openSheet(`<h2 id="sht">Pickz</h2><div class="kv"><span>League</span><b>NBA ✓</b></div>
    <div class="kv"><span>Props updated</span><b id="upd">${ago(D.generated_at)}</b></div>
    <div class="kv"><span>FanDuel prices</span><b>${bk("fd")}</b></div><div class="kv"><span>DraftKings prices</span><b>${bk("dk")}</b></div>
    <button class="opt" id="lg-sc">Scorecard<span class="ck">›</span></button>
    ${(() => { const M = D.proj_meta || {}, c = M.coverage || {};
      return `<div class="kv"><span>Projection model</span><b>${M.error ? esc(M.error) : `${esc(M.version || "")} · ${c.projected || 0}/${c.props || 0} props${M.stale ? ' · <span class="tg tq">STALE</span>' : ""}${M.refresh_pending ? " · updating" : ""}`}</b></div>
        <div class="kv"><span>Box scores through</span><b>${esc(M.logs_through || "—")}</b></div>
        <div class="kv"><span>Picks or bets</span><b><span class="tg tf" style="margin:0">NONE · RESEARCH ONLY</span></b></div>
        <button class="opt" id="lg-pj">Model scorecard: held-out test and forward record<span class="ck">›</span></button>`; })()}
    <div class="acts"><a class="btn" href="index.html" style="display:flex;align-items:center;justify-content:center;text-decoration:none">Back to Pickz</a><button class="btn pri" id="lg-ok">Done</button></div>`, s => { $("#lg-ok", s).onclick = closeSheet; $("#lg-sc", s).onclick = scoreSheet; $("#lg-pj", s).onclick = projScoreSheet; });
}
function dvpSheet(grp, mkt) {
  const rk = (D.ranks || {})[ST.date] || {}, tbl = rk.dvp || {}, n = rk.teams || 0;
  grp = grp || "G";
  const mks = ORDER.filter(m => tbl[grp] && tbl[grp][m]);
  mkt = mkt && mks.indexOf(mkt) >= 0 ? mkt : mks.indexOf(ST.market) >= 0 ? ST.market : mks[0];
  const t = (tbl[grp] || {})[mkt] || {}, order = Object.keys(t).sort((a, b) => t[b] - t[a]);
  const rows = order.map(team => { const r = t[team], cl = {good: "up", bad: "dn", mid: "md"}[rankCls(r, n, "over")];
    return `<div class="dvt"><b class="${cl}">${ord(r)}</b><span>${logo(team, "").replace("<img ", '<img loading="lazy" ')}${esc((TEAMS[team] || [team])[0])}</span><span>${team}</span></div>`; }).join("");
  const html = `<h2 id="sht">Defense vs Position</h2>
    <div class="seg" role="group" aria-label="Position">${[["G", "Guards"], ["F", "Forwards"], ["C", "Centers"]].map(([k, l]) => `<button data-dg="${k}" aria-pressed="${k === grp}">${l}</button>`).join("")}</div>
    <div class="chips">${mks.map(m => `<button class="chip" data-dm="${m}" aria-pressed="${m === mkt}">${TAB[m]}</button>`).join("")}</div>
    ${rows || '<div class="empty"><b>No games</b></div>'}<div class="acts"><button class="btn pri" id="dv-ok">Done</button></div>`;
  const bind = s => {
    $$("[data-dg]", s).forEach(b => b.onclick = () => redraw(b.dataset.dg, mkt));
    $$("[data-dm]", s).forEach(b => b.onclick = () => redraw(grp, b.dataset.dm));
    $("#dv-ok", s).onclick = closeSheet;
  };
  const redraw = (g2, m2) => { const s = $("#sheet"), y = s.scrollTop; dvpSheet(g2, m2); s.scrollTop = y; };
  if (!$("#sheet").hidden && $("#sheet").dataset.kind === "dvp") { $("#sheet").innerHTML = '<div class="grab" aria-hidden="true"></div>' + html; bind($("#sheet")); }
  else { openSheet(html, bind); $("#sheet").dataset.kind = "dvp"; }
}
// ── player page ──
function allLines(p) {
  const s = {};
  ["fd", "dk"].forEach(b => { if (p.books[b]) p.books[b].rungs.forEach(r => s[r[0]] = 1); });
  return Object.keys(s).map(Number).sort((a, b) => a - b);
}
// ── any player's page, prop or not: docs/player/{pid}.json (nba_players), charted like a prop's with a line he sets
// (his average, to the half below), no books; reached from search, a box score row or the Injuries list ──
const VPL = new Map();
let PIDX = null, VP = new Map(), SRCH_N = 0;
function playerIndex() {
  if (!PIDX) PIDX = fetch("player/index.json").then(r => r.ok ? r.json() : null).catch(() => null).then(j => j ? j.players : []);
  return PIDX;
}
function playerLoad(pid) {
  if (VPL.has(pid)) return Promise.resolve(VPL.get(pid));
  return fetch(`player/${pid}.json`).then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(j => { VPL.set(pid, j); return j; });
}
// a prop by id, or a player page: "v|<pid>|<market>" (his next game on the slate, if any, for the opponent and ranks)
function propFor(id) {
  const real = D.props.find(x => x.id === id);
  if (real || !String(id).startsWith("v|")) return real;
  if (VP.has(id)) return VP.get(id);
  const [, pidS, market] = String(id).split("|"), pid = +pidS, v = VPL.get(pid);
  if (!v || !NAME[market]) return null;
  const g = D.games.filter(x => (x.home === v.team || x.away === v.team) && x.state !== "final" && x.state !== "postponed")
    .sort((a, b) => a.tip < b.tip ? -1 : 1)[0];
  const opp = g ? (g.home === v.team ? g.away : g.home) : null, grp = MU_GROUP(v.pos), rk = g ? (D.ranks || {})[g.date] || {} : {};
  const vp = {id: id, v: true, gid: g ? g.gid : "none:" + v.team, pid: pid, market: market, player: v.name, team: v.team, opp: opp,
    home: g ? g.home === v.team : null, books: {}, main: null, hist: {}, proj: null, flag: null, live: null, summary: null,
    ctx: {pos: v.pos, group: grp, teams: rk.teams || 0, rank_n: g && rk.n ? rk.n[opp] : null,
          dvp_rank: g && grp && rk.dvp && rk.dvp[grp] && rk.dvp[grp][market] ? rk.dvp[grp][market][opp] || null : null,
          def_rank: g && rk.def ? rk.def[opp] || null : null}};
  VP.set(id, vp);
  return vp;
}
// a player page's starting line: his average for the stat (this season with 3+ games, else his last 10), to the half below
function vLine(p) {
  const logs = logsOf(p), cur = logs.filter(l => seasonOf(l.date) === D.season), use = (cur.length >= 3 ? cur : logs.slice(-10))
    .map(l => statValue(l, p.market)).filter(x => x !== null);
  return use.length ? Math.floor(use.reduce((a, b) => a + b, 0) / use.length) + .5 : .5;
}
// open a player: his prop on the slate's date (this stat, else his first), else his player page
function openPlayer(pid, market) {
  const m = market || (NAME[ST.market] ? ST.market : "points");
  const ps = D.props.filter(p => p.pid === pid && (gameOf(p.gid) || {}).date === ST.date);
  const real = ps.find(p => p.market === m) || ps.sort((a, b) => ORDER.indexOf(a.market) - ORDER.indexOf(b.market))[0];
  const go = () => openProp(real ? real.id : `v|${pid}|${m}`);
  if (!$("#sheet").hidden) closeSheet();
  if (MUP) { history.back(); setTimeout(go, 450); } else go();
}
function openProp(id, push) {
  if (String(id).startsWith("v|") && !VPL.has(+String(id).split("|")[1])) {
    playerLoad(+String(id).split("|")[1]).then(() => openProp(id, push), () => { $("#live").textContent = "Player not found"; });
    return;
  }
  const p = propFor(id);
  if (!p) return;
  const fresh = CUR !== id, was = !!CUR;
  CUR = id;
  if (fresh) Object.assign(DT, {line: p.v ? vLine(p) : p.main !== null ? p.main : allLines(p)[0],
                                 win: windowed(logsOf(p), "season", D.season).length ? "season" : "l10", home: null, starter: null,
                                 result: null, rest: null, ranges: {}, without: {}, with: {}, dvp: false, def: false, open: {}, more: false, fresh: null, ovs: []});
  if (push !== false) history.pushState({p: id}, "", hashState());
  const pg = $("#pg");
  pg.hidden = false;                        // (off-screen until it slides in; it must lay out for the pills to measure)
  if (fresh) { renderProp(was ? undefined : "open"); pg.scrollTop = 0; }
  if (was) return;
  // the page lays out off-screen for a frame, then slides in as a Web Animation (on the compositor, no forced layout);
  // the timer covers a background tab, where no frames come
  const go = () => {
    if (!CUR || pg.classList.contains("on")) return;
    pg.classList.add("on"); $(".shade").classList.add("on");
    if (!REDUCED && !document.hidden) pg.animate([{transform: "translateX(100%)"}, {transform: "none"}], {duration: 440, easing: EASE});
  };
  requestAnimationFrame(() => requestAnimationFrame(go)); setTimeout(go, 150);
  if (!TOUCH) setTimeout(() => { const b = $("#pg .bk"); if (b) b.focus({preventScroll: true}); }, 50);
}
// an iOS push: the page slides in from the right while the list drifts a third left under a shade. Safari's edge swipe
// back animates by itself, so after one the page closes with no second slide
let EDGE_T = 0;
const EASE = "cubic-bezier(.32,.72,0,1)", REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
function closeProp(instant) {
  const pg = $("#pg"), sh = $(".shade");
  clearTimeout(PX && PX.lazy);
  const done = () => { if (!CUR && !pg.hidden) { pg.hidden = true; pg.innerHTML = ""; PX = null; } };
  pg.classList.remove("on");
  if (instant || REDUCED) { sh.classList.add("snap"); sh.classList.remove("on"); void sh.offsetWidth; sh.classList.remove("snap"); done(); }
  else { sh.classList.remove("on"); pg.animate([{transform: "none"}, {transform: "translateX(100%)"}], {duration: 380, easing: EASE}).finished.then(done, done); setTimeout(done, 440); }
  const id = CUR; CUR = null;
  const b = !TOUCH && id && document.querySelector(`.pr[data-id="${CSS.escape(id)}"]`); if (b) b.focus({preventScroll: true});
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
const TAB = {trends: "Trends", movers: "Movers", points: "Points", rebounds: "Rebs", assists: "Assists", threes: "3PTM", pra: "PRA", pts_reb: "P+R", pts_ast: "P+A", reb_ast: "R+A"};
const GRPN = {G: "guards", F: "forwards", C: "centers"};
const ICON = {
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>',
  share: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M21 3 3 10.5l7 2.5 2.5 7L21 3Z"/><path d="m10 13 4.5-4.5"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z"/></svg>',
  pm: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M8 1.5v8M4 5.5h8M4 14h8"/></svg>',
  bars: '<svg viewBox="0 0 18 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M1.5 1.5v13h15"/><path stroke-width="2.2" d="M5.5 11.5v-4M9 11.5v-7M12.5 11.5v-5M16 11.5V9"/></svg>',
  menu: '<svg viewBox="0 0 22 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M2 3h18M5 8h12M8 13h6"/></svg>',
  search: '<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="7.5" cy="7.5" r="5.5"/><path d="m12 12 4.5 4.5"/></svg>',
  props: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8.5 5.5H21M8.5 12H21M8.5 18.5H21"/><circle cx="3.6" cy="5.5" r=".6" fill="currentColor"/><circle cx="3.6" cy="12" r=".6" fill="currentColor"/><circle cx="3.6" cy="18.5" r=".6" fill="currentColor"/></svg>',
  markets: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 2.5v19h19"/><path d="m5.5 16 4-6.5 4.5 4 6-7.5"/><circle cx="9.5" cy="9.5" r="1.3" fill="currentColor"/><circle cx="14" cy="13.5" r="1.3" fill="currentColor"/><circle cx="20" cy="6" r="1.3" fill="currentColor"/></svg>',
  people: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5"/><circle cx="17" cy="9" r="2.6"/><path d="M15.8 14.2c2.6-.3 4.3 1.3 4.8 4.3"/></svg>',
  injuries: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><rect x="2.5" y="2.5" width="19" height="19" rx="5"/><path d="M10 6.5h4V10h3.5v4H14v3.5h-4V14H6.5v-4H10z"/></svg>',
  ham: '<svg viewBox="0 0 22 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M2 2.5h18M2 8h18M2 13.5h18"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 10.5v8"/><circle cx="12" cy="6.2" r=".9" fill="currentColor" stroke="none"/></svg>',
  down: '<svg viewBox="0 0 12 8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="m2 2 4 4 4-4"/></svg>'};
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
  const R = 31, C = 2 * Math.PI * R, arc = C * .75, col = !gr ? "#48484a" : gr.q >= .6 ? "#28da8e" : gr.q >= .4 ? "#ffd60a" : "#ff3b30";
  const fill = gr ? arc * Math.max(.06, gr.q) : 0;
  return `<svg viewBox="0 0 80 80" width="53" height="53" aria-hidden="true"><g transform="rotate(135 40 40)">` +
    `<circle cx="40" cy="40" r="${R}" fill="none" stroke="#1d3a2e" stroke-width="7" stroke-linecap="round" stroke-dasharray="${arc} ${C}"/>` +
    `<circle cx="40" cy="40" r="${R}" fill="none" stroke="${col}" stroke-width="7" stroke-linecap="round" stroke-dasharray="${fill} ${C}"/></g>` +
    `<text x="40" y="51" text-anchor="middle" font-size="31" font-weight="500" fill="${col}">${gr ? gr.g : "–"}</text></svg>`;
}
// ov = the log key drawn as white outline boxes over the stat bars (min / fga / fg3a / fta / usg), or null
function chart2(logs, market, line, ov, grow) {
  const n = logs.length;
  if (!n) return '<div class="empty" style="padding:40px 0"><b>No games</b>Nothing matches this window and these filters.</div>';
  const vals = logs.map(l => statValue(l, market)), ovs = ov ? logs.map(l => l[ov]) : [];
  const num = x => x !== null && x !== undefined;
  const top = Math.max(line, ...vals.filter(num), ...ovs.filter(num), 1);
  // measured from the reference: bars start 35 pt in and the plot is 144.6 pt tall; a slot is a fifth of the width until
  // there are more than 5 games (5 or fewer: 69 pt slots, 8.3 pt gaps; 10: 34 pt, 3 pt; 20 scroll sideways)
  const W0 = Math.min(window.innerWidth, 520) - 30.6, AX = 35, ne = Math.max(n, 5);
  const gap = Math.max(2.4, 8.3 - (ne - 5) * 1.06), slot = Math.max(30, (W0 - AX + gap) / ne);
  const W = Math.max(W0, AX + n * slot - gap), T = 8, B = T + 144.6, H = B + 38;
  const y = v => B - v / top * (B - T);
  const oname = ov ? OVL[ov] : "";
  const o = [`<svg class="c2${grow ? " grow" : ""}" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(NAME[market])}${ov ? " and " + oname : ""} by game, ${n} games, line ${line}">`];
  // the top label stays off when the line sits at the top: its own label is there
  o.push(`${y(line) - y(top) < 14 ? "" : `<text class="ax" x="0" y="${y(top) + 7.1}">${r1(top)}</text>`}<text class="ax" x="0" y="${B - 3.5}">0</text>`);
  logs.forEach((l, i) => {
    const v = vals[i], m = ov ? ovs[i] : null, x = AX + i * slot, w = slot - gap, cx = x + w / 2;
    const res = v === null ? "none" : v > line ? "over" : v < line ? "under" : "push";
    const fill = res === "over" ? "var(--grn)" : res === "under" ? "var(--red)" : "#8e8e93";
    const d = iso(l.date + "T12:00:00Z").toLocaleDateString("en-US", {month: "numeric", day: "numeric", timeZone: "UTC"});
    const ovTxt = ov && num(m) ? `, ${r1(m)} ${oname}` : "";
    const desc = `${d} ${l.home ? "vs" : "at"} ${l.opp}: ${v === null ? "no value" : v} ${short(market)}${ovTxt || ` in ${l.min} minutes`}, ${res} ${line}`;
    let g = `<g class="br" tabindex="0" role="button" aria-label="${esc(desc)}, box score" data-gid="${esc(l.gid)}" data-tm="${esc(l.team)}" style="--d:${Math.min(i, 19) * 14}ms"><title>${esc(desc)}</title>`;
    const hv = v !== null && v > 0 ? B - y(v) : 0;
    if (hv) g += `<rect class="bv" x="${x}" y="${y(v)}" width="${w}" height="${hv}" fill="${fill}"/>`;
    // the stat's label: inside the bar's foot when it fits, else just above the bar
    let vy = hv >= 18 ? B - 3.5 : B - hv - 4, vin = hv >= 18;
    if (num(m)) {
      const hm = B - y(m);
      g += hm > 0 ? `<rect class="bm" x="${x + .65}" y="${y(m) + .65}" width="${w - 1.3}" height="${Math.max(0, hm - .65)}" fill="none" stroke="#fff" stroke-width="1.1"/>`
        : `<line class="bm" x1="${x}" x2="${x + w}" y1="${B - .55}" y2="${B - .55}" stroke="#fff" stroke-width="1.1"/>`;
      // its label: inside the box's top when the box clears the bar by 34+, else just above the box's top
      let my = hm - hv >= 34 ? y(m) + 18 : y(m) - 5;
      if (hm < hv && hm >= 34) my = y(m) + 17;           // a tall box inside the bar: its label at its top, the stat's at the foot
      else if (hm < hv && vin) {                         // a short box would cover the stat's label at the foot:
        if (hv >= 40) {                                  // move that label to the bar's top, and this one inside its box
          vy = B - hv + 16;                              // when the box fits it (else just above, below the stat's)
          my = hm >= 16 ? y(m) + 14 : Math.max(y(m) - 5, vy + 13);
        } else if (my > B - 20) my = B - hv - 5;         // or, in a short bar, put this one above the bar
      }
      if (!vin && Math.abs(my - vy) < 13) my = Math.min(my, vy) - 13;   // both above a short bar: stack them
      g += `<text class="mn" x="${cx}" y="${my}" text-anchor="middle">${ov === "min" || ov === "usg" ? r1(m) : m}</text>`;
    }
    if (v !== null) g += `<text class="${vin ? "vv" : "vw"}" x="${cx}" y="${vy}" text-anchor="middle">${v}</text>`;
    g += `<text class="xl" x="${cx}" y="${B + 17.4}" text-anchor="middle">${d}</text><text class="xl" x="${cx}" y="${B + 30.5}" text-anchor="middle">${l.home ? "" : "@"}${esc(l.opp)}</text></g>`;
    o.push(g);
  });
  o.push(`<line x1="0" x2="${W}" y1="${y(line)}" y2="${y(line)}" stroke="#fff" stroke-width=".9"/>`);
  o.push(`<text class="lx" x="0" y="${y(line) - 5.2}">${line}</text></svg>`);
  return o.join("");
}
// every rung either book posts: the hit rate there (this window and filters), the fair price, each book's price on
// the side. Tap a rung to use it. Green = better than fair; the HIT colors follow the list's rule (hbox).
function ladder(p, win, side, cur, winLab) {
  const vals = win.map(l => statValue(l, p.market)), k = side === "under" ? 2 : 1;
  const rows = allLines(p).map(L => {
    const s = hitSummary(vals, L), hits = side === "under" ? s.under : s.over;
    const fs = fairSide(p, L, side), h = hbox({n: s.n, rate: s.n ? hits / s.n : null}, chanceSide(p, L, side));
    const px = b => { const r = rungAt(p.books[b], L); return r && r[k] ? `<span class="${fs !== null && r[k] * fs > 1 ? "best" : ""}">${american(r[k])}</span>` : '<span class="na">—</span>'; };
    const pj = projAt(p, L, side), mo = !pj ? "—" : pct(pj.model);   // model alone on every rung: one monotone column
    return `<button class="lr${L === cur ? " on" : ""}" data-ll="${L}" aria-pressed="${L === cur}"><span>${L}</span><span class="${h.c}">${h.t}</span><span class="fv">${fs === null ? "—" : american(1 / fs)}</span><span class="mo">${mo}</span>${px("fd")}${px("dk")}</button>`;
  }).join("");
  return `<div class="ldr"><div class="lh2"><span>LINE</span><span>HIT ${esc(winLab)}</span><span>FAIR</span><span>MODEL</span><span>FD</span><span>DK</span></div>${rows}</div>
`;
}
// the projection engine's card: a model estimate, kept apart from the book prices and never a pick
const STATN = {pts: "Points", reb: "Rebounds", ast: "Assists", fg3m: "3-pointers"};
function projCard(p, line, side) {
  const M = D.proj_meta || {}, pr = p.proj, unit_ = esc(short(p.market));
  const head = `<h3>Model Projection <span class="tg tf" style="margin-left:6px">MODEL ESTIMATE · NOT A BET</span>${M.stale ? ' <span class="tg tq">STALE</span>' : ""}</h3>`;
  if (M.error || !pr) return head + `<div class="box0 pj"><div class="note" style="margin:0">${esc(M.error ? "Unavailable" : "Not projected yet")}</div></div>`;
  const at = projAt(p, line, side), sd = side === "under" ? "Under" : "Over";
  // the pmf as bars, the selected line marked
  const vals = pr.pmf[1], start = pr.pmf[0], mx = Math.max(...vals), W = Math.min(window.innerWidth, 520) - 56, H = 54;
  const bw = W / vals.length, xL = (line - start + .5) * bw;
  const bars = vals.map((v, i) => { const k = start + i, h = mx ? v / mx * (H - 4) : 0, win = side === "under" ? k < line : k > line;
    return `<rect x="${(i * bw).toFixed(2)}" y="${(H - h).toFixed(2)}" width="${Math.max(bw - 1, .6).toFixed(2)}" height="${h.toFixed(2)}" fill="${win ? "#4a8f6f" : "#3a3a3c"}"/>`; }).join("");
  const svg = `<svg class="pjh" width="${W}" height="${H + 14}" viewBox="0 0 ${W} ${H + 14}" role="img" aria-label="projected ${unit_} distribution">${bars}<line x1="${xL}" x2="${xL}" y1="0" y2="${H}" stroke="#fff" stroke-width="1.2" stroke-dasharray="3 2"/><text x="0" y="${H + 12}">${start}</text><text x="${W}" y="${H + 12}" text-anchor="end">${start + vals.length - 1}</text></svg>`;
  const pl = D.proj_players && D.proj_players[String(p.pid)];
  const other = pl ? [["min", "Minutes"], ["steals", "Steals"], ["blocks", "Blocks"], ["turnovers", "Turnovers"]].filter(([k]) => pl[k])
    .map(([k, lab]) => `<div class="kv"><span>${lab}</span><b>${(+pl[k].mean).toFixed(1)} <small>(${pl[k].q10}–${pl[k].q90})</small></b></div>`).join("") : "";
  // the input breakdown: μ = minutes x per-minute rate x opponent x pace x home (x back-to-back), per component
  const I = pl && pl.inputs, f2 = x => (+x).toFixed(2), GRPN_ = {G: "guards", F: "forwards", C: "centers"};
  const xf = (lab, v) => Math.abs(v - 1) < .005 ? "" : ` × ${lab} ${f2(v)}`, ha = p.home === false ? "away" : "home";
  const brk = !I ? "" : `<div class="note pjb">Inputs (μ = minutes × per-minute rate × opponent × pace × home/away). The distribution then comes from what actually happened after similar past projections, rescaled to μ. Where projections like this one ran low or high, the mean shown above moves off μ:<br>
    Minutes: ${(+I.min).toFixed(1)} recent, pulled toward his 60-game level${xf(ha, I.min_f.home)}${xf("back-to-back", I.min_f.b2b)} → μ ${(+I.mu.min).toFixed(1)}<br>
    ${(MARKET_PARTS[p.market] || []).filter(k => I[k]).map(k => `${esc(STATN[k] || k)}: ${(+I.min).toFixed(1)} min × ${(+I[k][0]).toFixed(3)} per min (his rate, pooled with ${GRPN_[I.group] || "his position"})${xf("opponent", I[k][1])}${xf("pace", I[k][2])}${xf(ha, I[k][3])}${xf("back-to-back", I[k][4])} → μ ${(+I.mu[k]).toFixed(1)}`).join("<br>")}</div>`;
  const inj = (D.injuries[gameOf(p.gid).date + "|" + p.pid] || {}).official, av = inj && M.availability && M.availability[inj.status];
  const avail = inj ? `<div class="kv"><span>Plays tonight?</span><b>${esc(inj.status)}${av && av[1] ? ` · ${Math.round((av[0] + 1) / (av[1] + 2) * 100)}% <small>(${av[0]}/${av[1]})</small>` : ""}</b></div>` : "";
  return head + `<div class="box0 pj">
    <div class="pjt"><div><b class="num">${(+pr.mean).toFixed(1)}</b> <i>${unit_} · mean</i></div><div class="pjr num">median ${pr.q50} · 80% range ${pr.q10}–${pr.q90}</div></div>
    ${svg}
    <div class="kv"><span>${sd} ${line} · model + market</span><b>${at.blend === null ? "— <small>no two-sided price here</small>" : pct(at.blend)}</b></div>
    <div class="kv mo1"><span>${sd} ${line} · model alone</span><b>${pct(at.model)}${at.push > .001 ? ` <small>· push ${pct(at.push)}</small>` : ""}</b></div>
    <div class="kv"><span>Held-out 2024-25 vs FanDuel close</span><b class="dn">Lost</b></div>
    <div class="kv"><span>Blend with the price</span><b>Added nothing</b></div>
    ${avail}${other ? `<div class="pjo">Other stats</div>${other}` : ""}
    <button class="lk" id="pjsc" style="padding:12px 16px 6px 0;font-size:13px">Model scorecard ›</button></div>`;
}
// the projection engine's record: the pre-registered held-out test (proj_meta.backtest) and the forward record
function projScoreSheet() {
  openSheet('<h2 id="sht">Model scorecard <span class="tg tf">NOT A BET</span></h2><div class="note" style="font-size:14px">Loading…</div>', () => {});
  const s = $("#sheet"), n = SHEET_N, M = D.proj_meta || {}, B = M.backtest || {};
  const pc = x => x == null ? "–" : (x * 100).toFixed(1) + "%", f4 = x => x == null ? "–" : x.toFixed(4);
  const ci = c => c ? `${c[0] > 0 ? "+" : ""}${c[0].toFixed(4)} <small>(${c[1].toFixed(4)} to ${c[2].toFixed(4)})</small>` : "–";
  const per = Object.entries(B.periods || {}).map(([season, p]) => {
    const m = p.market;
    return `<div class="kv"><span>${esc(season)}${season === M.tuned_on ? ' <span class="tg tq">TUNING · IN-SAMPLE</span>' : ""} · ${p.n ? p.n.toLocaleString() : 0} player-games</span><b>CRPS vs recent form ${ci(p.crps_vs_b2)}</b></div>` +
      (p.label ? `<div class="kv"><span>${esc(p.label)}</span></div>` : "") +
      (m ? `<div class="kv"><span>${esc(season)} · ${m.n.toLocaleString()} FanDuel lines</span><b>log loss: model ${f4(m.model_ll)} · blend ${f4(m.blend_ll)} · close ${f4(m.close_ll)}</b></div>
            <div class="kv"><span>blend − close</span><b>${ci(m.blend_minus_close)}</b></div>` : "");
  }).join("");
  const vds = (B.verdicts || []).map(v => { const m = /^(.*):\s*(YES|NO)\b\s*(.*?)\.?$/.exec(v);
    return m ? `<div class="kv"><span>${esc(m[1])}${m[3] ? ` <small>${esc(m[3])}</small>` : ""}</span><b class="${m[2] === "YES" ? "up" : "dn"}">${m[2]}</b></div>` : `<div class="kv"><span>${esc(v)}</span></div>`; }).join("");
  const fill = html => { if (SHEET_N === n && !s.hidden) { s.innerHTML = '<div class="grab" aria-hidden="true"></div><h2 id="sht">Model scorecard <span class="tg tf">NOT A BET</span></h2>' + html; const d = $("#ps-ok", s); if (d) d.onclick = closeSheet; } };
  fetch("nba_proj_score.json?t=" + Date.now(), {cache: "no-store"}).then(r => r.ok ? r.json() : null).catch(() => null).then(j => {
    const fwd = j && j.graded ? `<div class="kv"><span>graded since ${esc(j.from || "")}</span><b>${j.graded} props</b></div>
      <div class="kv"><span>log loss</span><b>model ${f4(j.model_logloss)} · blend ${f4(j.blend_logloss)}${j.close_logloss != null ? " · close " + f4(j.close_logloss) : ""}</b></div>
      ${j.blend_minus_close ? `<div class="kv"><span>blend − close</span><b>${ci(j.blend_minus_close)}</b></div>` : ""}
      ${j.clv ? `<div class="kv"><span>CLV · close moved toward model</span><b>${pc(j.clv.mean)} · ${pc(j.clv.share_positive)} of ${j.clv.n}</b></div>` : ""}
      ${[["reliability_model", "model"], ["reliability_blend", "blend"], ["reliability_close", "close"]].filter(([k]) => j[k]).map(([k, lab]) =>
        `<div class="kv"><span>Calibration · ${lab}</span><b class="cal">${j[k].filter(b => b[0]).map(b => `${pc(b[1])}→${pc(b[2])}`).join(" · ")}</b></div>`).join("")}`
      : '<div class="empty"><b>No graded forecasts yet</b></div>';
    fill(`<div class="sg"><span>Backtest</span></div>${per || '<div class="empty"><b>No results yet</b></div>'}
      ${vds ? `<div class="sg"><span>Pre-registered verdicts</span></div>${vds}` : ""}
      <div class="sg"><span>Forward record</span></div>${fwd}
      <div class="acts"><button class="btn pri" id="ps-ok">Done</button></div>`);
  });
}
// each book's main line over time (a step per change), its open and its price now
function histChart(p) {
  const H = p.hist || {}, books = [["fd", "FanDuel", "#2d9bff"], ["dk", "DraftKings", "#62d26f"]].filter(([b]) => (H[b] || []).length);
  if (!books.length) return '<div class="empty" style="padding:16px 0"><b>No history yet</b></div>';
  const ms = t => iso(t).getTime(), end = Math.max(Date.now() - 60000, ...books.map(([b]) => ms(H[b][H[b].length - 1][0])));
  const t0 = Math.min(...books.map(([b]) => ms(H[b][0][0])));
  const vals = books.flatMap(([b]) => H[b].map(x => x[1]));
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (hi - lo < 1) { lo -= .5; hi += .5; }
  const W = Math.min(window.innerWidth, 520) - 30.6, Hh = 92, AX = 30, x = t => AX + (W - AX - 6) * (ms(t) - t0) / Math.max(1, end - t0);
  const y = v => 10 + (Hh - 22) * (hi - v) / (hi - lo);
  const o = [`<svg class="hc" width="${W}" height="${Hh}" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Main line over time">`];
  [hi, lo].forEach(v => o.push(`<text x="0" y="${y(v) + 4}">${v}</text><line x1="${AX}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#262626"/>`));
  books.forEach(([b, , col]) => {
    const h = H[b];
    let d = `M${x(h[0][0])} ${y(h[0][1])}`;
    h.slice(1).forEach(pt => { d += ` H${x(pt[0])} V${y(pt[1])}`; });
    d += ` H${AX + (W - AX - 6)}`;
    o.push(`<path d="${d}" fill="none" stroke="${col}" stroke-width="2"/>`);
    h.forEach((pt, i) => { if (!i || pt[1] !== h[i - 1][1]) o.push(`<circle cx="${x(pt[0])}" cy="${y(pt[1])}" r="2.6" fill="${col}"/>`); });
  });
  o.push(`<text x="${AX}" y="${Hh - 1}">${esc(mt(new Date(t0).toISOString(), true))}</text><text x="${W}" y="${Hh - 1}" text-anchor="end">now</text></svg>`);
  const sum = books.map(([b, name, col]) => {
    const h = H[b], a = h[0], z = h[h.length - 1], lines = h.filter((pt, i) => !i || pt[1] !== h[i - 1][1]).length - 1;
    return `<div class="hl"><i style="background:${col}"></i><b>${name}</b><span class="num">${a[1]} ${american(a[2])} → ${z[1]} ${american(z[2])}</span></div>`;
  }).join("");
  return o.join("") + sum;
}
// a bar's <title> only shows on hover, so a tap pins its game above the bar (tap it again, or the chart, to clear)
// a game's box score (docs/box/{gid}.json, nba_boxscore), opened from a chart bar: the team he played for first, his
// row and the prop's stat columns marked; the name column stays put while the stats scroll sideways
const BXC = ["MIN", "PTS", "REB", "AST", "FG", "3PT", "FT", "STL", "BLK", "TO", "PF", "+/-"];
const BX_HI = {points: ["PTS"], rebounds: ["REB"], assists: ["AST"], threes: ["3PT"], pra: ["PTS", "REB", "AST"],
               pts_reb: ["PTS", "REB"], pts_ast: ["PTS", "AST"], reb_ast: ["REB", "AST"]};
// a player row [pid, name, starter, min, pts, reb, ast, fgm, fga, fg3m, fg3a, ftm, fta, stl, blk, tov, pf, pm]; a team's
// tot [pts, reb, ast, fgm, fga, fg3m, fg3a, ftm, fta, stl, blk, tov, pf]
const bxRow = r => [r[3], r[4], r[5], r[6], r[7] + "-" + r[8], r[9] + "-" + r[10], r[11] + "-" + r[12], r[13], r[14], r[15], r[16], (r[17] > 0 ? "+" : "") + r[17]];
const bxTot = t => ["", t[0], t[1], t[2], t[3] + "-" + t[4], t[5] + "-" + t[6], t[7] + "-" + t[8], t[9], t[10], t[11], t[12], ""];
function bxTable(t, p) {
  const hi = BX_HI[p.market] || [], td = (v, i) => `<td${hi.indexOf(BXC[i]) >= 0 ? ' class="hi"' : ""}>${v}</td>`;
  const row = r => `<tr data-vp="${r[0]}"${r[0] === p.pid ? ' class="me"' : ""}><td>${esc(nameOf(r[1]))}</td>${bxRow(r).map(td).join("")}</tr>`;
  const st = t.players.filter(r => r[2]), bn = t.players.filter(r => !r[2]);
  return `<div class="bxw"><table class="bx"><thead><tr><th>${st.length ? "STARTERS" : "PLAYER"}</th>${BXC.map((c, i) => `<th${hi.indexOf(c) >= 0 ? ' class="hi"' : ""}>${c}</th>`).join("")}</tr></thead>
    <tbody>${st.map(row).join("")}${bn.length ? `<tr class="bxd"><td colspan="${BXC.length + 1}">BENCH</td></tr>${bn.map(row).join("")}` : ""}
    <tr class="tot"><td>Team</td>${bxTot(t.tot).map(td).join("")}</tr></tbody></table></div>
    ${t.dnp.length ? `<div class="bxn"><b>DNP</b>${t.dnp.map(([nm, why]) => esc(nameOf(nm)) + (why !== "DNP" ? ` <small>(${esc(injReason(why))})</small>` : "")).join(", ")}</div>` : ""}`;
}
// box scores are fetched once and kept: a finger landing on a bar starts its fetch, and the bars on screen are
// fetched while the page is idle, so a tap usually finds the box already here
const BOXC = new Map();
function boxGet(gid) {
  if (!BOXC.has(gid)) BOXC.set(gid, fetch(`box/${encodeURIComponent(gid)}.json`)
    .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .catch(e => { BOXC.delete(gid); throw e; }));
  return BOXC.get(gid);
}
let BOX_WARM = 0;
function boxWarm(logs) {
  clearTimeout(BOX_WARM);
  BOX_WARM = setTimeout(() => logs.slice(-12).reverse().forEach((l, i) => setTimeout(() => boxGet(l.gid).catch(() => {}), i * 60)), 900);
}
function boxHtml(b, cur, p) {
  const [a, h] = b.teams;
  const d = iso(b.date + "T12:00:00Z").toLocaleDateString("en-US", {weekday: "short", month: "numeric", day: "numeric", timeZone: "UTC"});
  return `<div class="bxh">${logo(a.tri, "")}<b>${esc(a.tri)}</b><span class="num${a.pts > h.pts ? "" : " lo"}">${a.pts}</span><i>–</i><span class="num${h.pts > a.pts ? "" : " lo"}">${h.pts}</span><b>${esc(h.tri)}</b>${logo(h.tri, "")}</div>
    <div class="bxs">${esc(d)} · ${esc(b.status)}</div>
    <div class="seg" role="group" aria-label="Team"><span class="pill2"></span>${b.teams.map(t => `<button data-bt="${esc(t.tri)}" aria-pressed="${t.tri === cur}">${logo(t.tri, "")}${esc(t.tri)}</button>`).join("")}</div>
    <div id="bxt">${bxTable(b.teams.find(t => t.tri === cur), p)}</div>`;
}
// The sheet rises once, at its full height, with the box in it: when the box is not here within 140 ms it rises with a
// skeleton of the same shape and the box fades in over it, so nothing changes size while it moves
function boxSheet(gid, team, p) {
  const pr = boxGet(gid), wait = new Promise(r => setTimeout(r, 140, null));
  const frame = body => `<h2 id="sht">Box Score</h2><div class="bxb">${body}</div><div class="acts stk"><button class="btn pri" id="bx-ok">Done</button></div>`;
  const bind = (s, b) => {
    $("#bx-ok", s).onclick = closeSheet;
    if (!b) return;
    let cur = b.teams.some(t => t.tri === team) ? team : b.teams[1].tri;
    const seg = $(".seg", s);
    slide(seg, true);
    $$("[data-bt]", s).forEach(btn => btn.onclick = () => {
      if (cur === btn.dataset.bt) return;
      cur = btn.dataset.bt; press("[data-bt]", x => x === btn, s); slide(seg);
      const t = $("#bxt", s);
      t.innerHTML = bxTable(b.teams.find(x => x.tri === cur), p);
      if (!REDUCED) t.animate([{opacity: .35}, {opacity: 1}], {duration: 200, easing: "ease-out"});
    });
  };
  const missing = '<div class="empty"><b>Box score not available yet</b></div>';
  const cur0 = b => b.teams.some(t => t.tri === team) ? team : b.teams[1].tri;
  Promise.race([pr, wait]).then(b => {
    if (b) { openSheet(frame(boxHtml(b, cur0(b), p)), s => bind(s, b)); $("#sheet").dataset.kind = "box"; return; }
    openSheet(frame('<div class="bxsk"><i></i><i></i><i></i>' + "<b></b>".repeat(12) + "</div>"), s => bind(s, null));
    const s = $("#sheet"), n = SHEET_N;
    s.dataset.kind = "box";
    const put = html => {
      if (SHEET_N !== n || s.hidden) return null;
      const box = $(".bxb", s);
      box.innerHTML = html;
      if (!REDUCED) box.animate([{opacity: 0}, {opacity: 1}], {duration: 220, easing: "ease-out"});
      return box;
    };
    pr.then(b2 => { if (put(boxHtml(b2, cur0(b2), p))) bind(s, b2); }, () => put(missing));
  }, () => openSheet(frame(missing), s => bind(s, null)));
}
// The page is built once per prop (header, tabs, hero, availability) and its live parts — cells, chart, window capsule,
// chips, books, game log — are redrawn in place on every change, so the photo never reloads and the scroll never jumps.
let PX = null;
function renderProp(mode) {
  const p = propFor(CUR), pg = $("#pg");
  if (!p) { PX = null; pg.innerHTML = `<div class="ph"><button class="cb bk" aria-label="Back">${ICON.back}</button></div><div class="empty"><b>No longer posted</b></div>`; $("#pg .bk").onclick = () => history.back(); return; }
  const g = gameOf(p.gid), logs = logsOf(p), c = p.ctx || {};
  const team = TEAMS[p.team] || [p.team || "", "#333"];
  const without = (D.absences[g.date + "|" + p.team] || []).map(a => ({key: String(a.pid), name: a.name || "teammate", played: a.played, since: a.since, team: p.team, status: a.status, fresh: a.fresh}));
  const mkts = p.v ? TAB_ORDER : TAB_ORDER.filter(m => D.props.some(x => x.gid === p.gid && x.pid === p.pid && x.market === m));
  const fav = favs().indexOf(p.pid) >= 0;
  const wins = [["season", D.season.slice(0, 4)], ["h2h", "H2H"], ["l5", "L5"], ["l10", "L10"], ["l20", "L20"]];
  // availability
  const rpE = p.v && (((D.inj_report || {})[g.date + "|" + p.team] || {}).players || []).find(e => e.pid === p.pid);
  const inj = D.injuries[g.date + "|" + p.pid] || (rpE ? {official: {status: rpE.status, reason: rpE.reason}, listed_team: true} : {}), rep = D.sources.report[g.date];
  const arows = [`<div class="kv"><span>Official report</span><b>${inj.official ? esc(inj.official.status) + (inj.official.reason ? " · " + esc(inj.official.reason.replace("Injury/Illness - ", "")) : "") : rep ? (inj.listed_team ? "Not listed" : "Team not listed yet") : "Not out yet"}</b></div>`];
  if (rep) arows.push(`<div class="kv"><span>Report time</span><b>${mt((inj.official || {}).published || rep.published, true)}</b></div>`);
  (inj.news || []).forEach(n => arows.push(`<div class="kv"><span>News · ${esc(n.source)}</span><b>${esc(n.headline || n.status || "")} · ${mt(n.detected)}</b></div>`));
  if (without.length) arows.push(`<div class="kv"><span>Teammates out</span><b>${without.map(w => esc(w.name) + " (" + esc(w.status) + ")").join(", ")}</b></div>`);
  const rel = (D.related[p.id] || []).map(r => {
    const o = D.props.find(x => x.id === r.id); if (!o) return "";
    return `<button class="rc" data-rel="${esc(o.id)}"><div class="nm">${esc(o.player.split(" ").slice(-1)[0])} ${esc(short(o.market))}</div><div class="sub">${o.main === null ? "alt lines" : "O/U " + o.main}</div><div class="rr">r ${r.r > 0 ? "+" : ""}${r.r} · ${r.n} games</div></button>`;
  }).join("");
  const live = p.live && g.state !== "pregame" ? `<div class="box0" style="margin:12px 15.3px 0" role="status"><div class="live"><span class="tg ${g.state === "live" ? "tl" : "tn"}">${g.state === "live" ? "LIVE" : "FINAL"}</span>${p.live.value} ${esc(short(p.market))} in ${p.live.min} min</div><div class="note">${esc(g.label || "")}${g.score ? " · " + esc(g.away) + " " + g.score[0] + " – " + esc(g.home) + " " + g.score[1] : ""} · box score ${ago(g.updated)}</div></div>` : "";
  pg.innerHTML = `<div class="ph"><button class="cb bk" aria-label="Back">${ICON.back}</button>
      <div class="ph-t"><b>${esc(p.player)}</b><span>${esc(team[0])}</span></div><span class="sp2"></span>
      <button class="cb" id="shr" aria-label="Share">${ICON.share}</button><button class="cb${fav ? " fav" : ""}" id="fav" aria-label="Favorite" aria-pressed="${fav}">${ICON.star}</button></div>
    <nav class="mt" aria-label="Markets"><div class="mt-in">${mkts.map(m => `<button data-mk="${m}" aria-pressed="${m === p.market}">${TAB[m]}</button>`).join("")}</div></nav>
    <div class="hro"><div class="hro-l"><h2>${esc(p.player)}</h2><div class="hro-s">${esc(team[0])}</div><div class="hro-s">${esc(POSN[c.pos] || c.pos || "")}</div>
      <div class="tlg" style="background:${team[1]}">${logo(p.team, "")}</div></div>
      <img class="hro-i" alt="" decoding="async" src="${heroSrc(p.pid)}" onerror="this.style.visibility='hidden'"></div>
    <div class="sg2" id="pcells"></div>
    ${live}
    <div class="c2w" id="chw"></div>
    <div class="wrow"><div class="wcap" id="wcap" role="group" aria-label="Games window"><span class="pill2"></span>${wins.map(([k, lab]) => `<button class="wc" data-win="${k}"><i>${lab}</i><b></b></button>`).join("")}</div><button class="cb fb" id="pf" aria-label="All filters">${ICON.menu}</button></div>
    <div class="sr" id="psr" role="status"></div>
    <div class="cf" id="pcf"></div>
    <div class="sec2" id="pproj"></div>
    <div class="bkt" id="pbk"></div>
    <div id="pstat"></div>
    <div class="sec2" id="plog"></div>
    <div class="end"></div>`;
  const stat = `<div class="sec2"><h3>Availability</h3><div class="box0">${arows.join("")}</div></div>
    ${rel ? `<div class="sec2"><h3>Related Props</h3><div class="rel" style="margin:0;padding:0">${rel}</div></div>` : ""}
    ${p.flag ? `<div class="sec2"><h3>Engine</h3><div class="box0"><span class="tg tf" style="margin:0 6px 0 0">SHADOW · NOT A BET</span>${esc(p.flag.tier)} at ${p.flag.line} · ${p.flag.card === 1 ? "on the card" : "logged only" + (p.flag.why ? " (" + esc(p.flag.why.toLowerCase()) + ")" : "")}</div></div>` : ""}`;
  clearTimeout(PX && PX.lazy);
  PX = {p: p, g: g, logs: logs, c: c, without: without, wins: wins, stat: stat, statDone: false};
  $("#pg .bk").onclick = () => history.back();
  $("#fav", pg).onclick = () => { toggleFav(p.pid); const f = $("#fav", pg), on = favs().indexOf(p.pid) >= 0; f.classList.toggle("fav", on); f.setAttribute("aria-pressed", on); f.classList.remove("pop"); void f.offsetWidth; f.classList.add("pop"); if (ST.watch && ST.view !== "injuries") renderList(); };
  $("#shr", pg).onclick = () => {
    const url = location.href, title = `${p.player} ${NAME[p.market]} ${DT.line}`;
    if (navigator.share) navigator.share({title: title, url: url}).catch(() => {});
    else if (navigator.clipboard) navigator.clipboard.writeText(url).then(() => { $("#live").textContent = "Link copied"; });
  };
  $$("[data-mk]", pg).forEach(b => b.onclick = () => { const id = (p.v ? "v" : p.gid) + "|" + p.pid + "|" + b.dataset.mk; if (id !== p.id) { openProp(id, false); history.replaceState({p: id}, "", hashState()); } });
  $$("[data-win]", pg).forEach(b => b.onclick = () => { if (DT.win === b.dataset.win || b.disabled) return; DT.win = b.dataset.win; updateProp(); });
  $("#pf", pg).onclick = () => playerFilters(p, logs, without);
  const cw = $("#chw");
  cw.onclick = e => { const gb = e.target.closest("g.br"); if (gb) boxSheet(gb.dataset.gid, gb.dataset.tm, p); };
  cw.onpointerdown = e => { const gb = e.target.closest("g.br"); if (gb) boxGet(gb.dataset.gid).catch(() => {}); };
  updateProp(mode || true);
}
// teammates on his team now, most minutes first: [{key, pid, name, since, played, mpg, gp, team}] (D.mates,
// nba_research.team_mates), then any teammate out tonight the roster list lacks (D.absences)
function matesAll(p, without) {
  const T = (D.mates || {})[p.team];
  if (T && !T.list) T.list = T.mates.map(m => ({key: String(m.pid), pid: m.pid, name: m.name, since: m.since, mpg: m.mpg, gp: m.gp,
    team: p.team, played: T.gids.filter((g, i) => m.on[i] === "1")}));
  const ms = (T ? T.list : []).filter(m => m.pid !== p.pid);
  return ms.concat(without.filter(a => !ms.some(m => m.key === a.key)));
}
// the chart's filters from DT; dr overrides keys (a sheet's draft). with / without: {teammate key: true}
function chartF(p, g, c, without, dr) {
  const x = Object.assign({}, DT, dr || {});
  const prevS = (+D.season.slice(0, 4) - 1) + "-" + D.season.slice(2, 4);
  const rkCur = (D.ranks || {})[g.date] || {}, rkPrev = (D.ranks || {})[prevS] || {};
  const dvpT = c.group && rkCur.dvp ? tierOf(c.dvp_rank, c.teams) : null, defT = tierOf(c.def_rank, c.teams);
  const oppSets = [];
  if (x.dvp && dvpT) { const s = {}; s[D.season] = oppSet(rkCur.dvp[c.group][p.market], dvpT, rkCur.teams);
    if (rkPrev.dvp && rkPrev.teams) s[prevS] = oppSet(rkPrev.dvp[c.group][p.market], dvpT, rkPrev.teams); oppSets.push(s); }
  if (x.def && defT) { const s = {}; s[D.season] = oppSet(rkCur.def, defT, rkCur.teams);
    if (rkPrev.def && rkPrev.teams) s[prevS] = oppSet(rkPrev.def, defT, rkPrev.teams); oppSets.push(s); }
  const ms = matesAll(p, without);
  return {home: x.home, starter: x.starter, result: x.result, rest: x.rest, ranges: x.ranges, oppSets: oppSets,
          with: ms.filter(m => x.with[m.key]), without: ms.filter(m => x.without[m.key])};
}
function updateProp(mode) {
  if (!PX) return;
  const first = !!mode && mode !== "rest", opening = mode === "open", rest = mode === "rest";
  const {p, g, logs, c, without, wins} = PX, pg = $("#pg"), line = DT.line, side = ST.side;
  const f = chartF(p, g, c, without);
  const base = filterLogs(logs, f);
  const win = windowed(base, DT.win, D.season, p.opp);
  const s = hitSummary(win.map(l => statValue(l, p.market)), line);
  const rate = sideRate(s, side);
  const winLab = (wins.find(w => w[0] === DT.win) || ["", "L10"])[1];
  const tri = up => `<span class="tri ${up ? "up" : "dn"}">${up ? "▲" : "▼"}</span>`;
  const fs = chanceSide(p, line, side), hr = hbox({n: s.n, rate: rate}, fs);
  const gr = grade(p, side);
  const opp = g.state === "none" ? "No game" : `<span class="vs">${p.home ? "vs" : "@"}</span>${esc(p.opp || "")}\u200a·\u200a${g.state === "pregame" ? mt(g.tip).replace(" ", "") : esc(g.state === "live" ? "LIVE" : g.state === "final" ? "Final" : g.label || "")}`;
  const ovOn = k => !!(DT.open[k] || DT.ranges[k]);
  const ov = DT.ovs.slice().reverse().find(ovOn) || Object.keys(OVL).find(ovOn) || null;
  // cells
  if (!rest) $("#pcells").innerHTML = `<div class="cells">
      <div><i>${esc(winLab)} AVG</i><b>${s.avg === null ? "–" : tri(s.avg > line) + r1(s.avg)}</b></div>
      <button id="lnb"><i>LINE</i><b>${line}<span class="cv">›</span></b></button>
      <div><i>PROP</i><b>${esc(NAME[p.market])}</b></div>
      <div><i>HIT RATE</i><b class="${hr.c === "sm" ? "sm" : ""}">${hr.c === "up" ? tri(true) : hr.c === "dn" ? tri(false) : ""}${hr.t}</b></div>
      <button id="psb"><i>POS RANK</i><b>${c.pos_rank ? ord(c.pos_rank) : "–"}<span class="cv">›</span></b></button>
      <div><i>OPPONENT</i><b>${opp}</b></div></div>
      <button class="muc" id="mub">${gauge(gr)}<span>Matchup <span class="cv">›</span></span></button>`;
  // chart
  if (!rest) {
  const cw = $("#chw"), sl = cw.scrollLeft, atEnd = first || sl + cw.clientWidth >= cw.scrollWidth - 4;
  cw.innerHTML = chart2(win, p.market, line, ov, !first);
  cw.scrollLeft = atEnd ? cw.scrollWidth : sl;
  boxWarm(win);
  // window capsule
  wins.forEach(([k]) => {
    const w = windowed(base, k, D.season, p.opp), ss = hitSummary(w.map(l => statValue(l, p.market)), line), r = sideRate(ss, side);
    const b = $(`[data-win="${k}"]`, pg), v = $("b", b), h = hbox({n: ss.n, rate: r}, fs);
    b.setAttribute("aria-pressed", k === DT.win); b.disabled = !w.length;
    v.textContent = h.t; v.className = h.c;
  });
  slide($("#wcap"), first);
  $("#psr").textContent = `${side === "under" ? "Under" : "Over"} ${line}: ${rate === null ? "no games" : Math.round(rate * 100) + "% of " + s.n + " games"}.${ov ? " White boxes = " + OVL[ov] + "." : ""}`;
  }
  // chart filter chips: DvP, Def Rank, Minutes, More (more: FGA, Home, Away, 3PA, FTA, Margin, Win, Loss, B2B, Without …)
  const on = (k, v) => DT[k] === v;
  const chip = (attrs, lab, active) => `<button class="fc${active ? " on" : ""}" ${attrs} aria-pressed="${!!active}">${lab}</button>`;
  const rangeOn = k => !!DT.ranges[k];
  const chips = [];
  const rchip = k => { if (!forMarket(k, p.market)) return; const b = bounds(logs, k), abbr = RANGES.find(r => r[0] === k)[2]; if (b && b[0] !== b[1]) chips.push(chip(`data-r="${k}"`, `${OVL[k] ? ICON.bars : ICON.pm}${abbr}`, rangeOn(k) || DT.open[k])); };
  const tchip = (k, v, lab) => chips.push(chip(`data-k="${k}" data-v="${v}"`, lab, on(k, v)));
  ["min", "fga", "fg3a", "fta", "usg", "pot_ast", "reb_ch"].forEach(rchip);   // the adjustable filters first
  if (logs.some(l => l.starter === 1)) tchip("starter", true, "Starter");     // only the games he started
  if (c.dvp_rank) chips.push(chip('data-t="dvp"', `DvP <em class="${rankCls(c.dvp_rank, c.teams, side)}">${ord(c.dvp_rank)}</em>`, DT.dvp));
  if (c.def_rank) chips.push(chip('data-t="def"', `Def Rank <em class="${rankCls(c.def_rank, c.teams, side)}">${ord(c.def_rank)}</em>`, DT.def));
  const wchip = w => chips.push(chip(`data-wo="${w.key}"`, (w.fresh ? "W/O " : "Without ") + esc(lastName(w.name)), DT.without[w.key]));
  without.filter(w => w.fresh).forEach(wchip);                 // tonight's news: up front
  // the With / Without filters set in the teammates sheet show as chips that are on (a tap clears one)
  const ms = matesAll(p, without), fresh = k => without.some(w => w.fresh && w.key === k);
  ms.filter(m => DT.with[m.key]).forEach(m => chips.push(chip(`data-mw="${m.key}"`, "With " + esc(lastName(m.name)), true)));
  ms.filter(m => DT.without[m.key] && !fresh(m.key)).forEach(m => chips.push(chip(`data-mo="${m.key}"`, "W/O " + esc(lastName(m.name)), true)));
  if (ms.length) chips.push(chip('id="mts" aria-haspopup="dialog"', `${ICON.people}With / Without`, false));
  const extra = DT.home !== null || DT.result !== null || DT.rest !== null || MORE_R.some(k => rangeOn(k) || DT.open[k]);
  const more = DT.more || extra;
  if (more) {
    tchip("home", true, "Home"); tchip("home", false, "Away"); rchip("margin");
    tchip("result", "W", "Win"); tchip("result", "L", "Loss"); tchip("rest", "b2b", "B2B");
  }
  chips.push(`<button class="fc" id="more" aria-expanded="${more}">${more ? "Less" : "More"}</button>`);
  const panels = RANGES.filter(([k]) => (DT.open[k] || rangeOn(k)) && forMarket(k, p.market)).map(([k, lab]) => {
    const b = bounds(logs, k); if (!b || b[0] === b[1]) return "";
    const cur = DT.ranges[k] || b;
    return `<div class="rp${DT.fresh === k ? " in" : ""}" data-rk="${k}" data-lo="${b[0]}" data-hi="${b[1]}"><div class="rp-h"><span>${RANGES.find(r => r[0] === k)[2]}</span><b class="rv"${DT.ranges[k] ? "" : " hidden"}>${cur[0]} – ${cur[1]}</b></div>
      <div class="dual2"><div class="fil"></div>${thumbs(lab, b)}</div>
      <div class="rp-b"><span>${b[0]}</span><span>${b[1]}</span></div></div>`;
  }).join("");
  DT.fresh = null;
  const anyF = DT.dvp || DT.def || DT.home !== null || DT.starter !== null || DT.result !== null || DT.rest !== null || Object.keys(DT.ranges).length ||
    Object.keys(DT.without).some(k => DT.without[k]) || Object.keys(DT.with).some(k => DT.with[k]) || Object.keys(DT.open).some(k => DT.open[k]);
  if (!rest) $("#pcf").innerHTML = `<div class="cf-h"><h3>Chart Filters</h3><button class="ca" id="clr"${anyF ? "" : " hidden"}>Clear All</button></div>
      <div class="fcs">${chips.join("")}</div>${panels}`;
  if (opening) { PX.lazy = setTimeout(() => { if (PX && PX.p === p) updateProp("rest"); }, 470); bindLive(p, logs, without); return; }
  if (!PX.statDone) { $("#pstat").innerHTML = PX.stat; PX.statDone = true; $$("[data-rel]", pg).forEach(b => b.onclick = () => openProp(b.dataset.rel)); }
  if (p.v) { $("#pproj").innerHTML = ""; $("#pbk").innerHTML = ""; }      // a player page: no line posted, no books
  else {
  // books
  const fair = fairAt(p, line);
  const beats = (sd, price) => fair.p !== null && price * (sd === "over" ? fair.p : 1 - fair.p) > 1;
  const bk = [["fd", "FanDuel"], ["dk", "DraftKings"]].map(([b, name]) => {
    const q = p.books[b];
    if (!q) return `<div class="bkr2"><span>${name}</span><span class="na">—</span><span class="na">—</span><span class="na">—</span></div>`;
    const here = rungAt(q, line), r = here || rungAt(q, q.main), l = here ? line : q.main;
    const px = (sd, i) => r && r[i] ? `<button class="${here && beats(sd, r[i]) ? "best" : ""}" data-ps="${sd}" data-pl="${l}" aria-pressed="${!!here && side === sd}" aria-label="${sd === "over" ? "Over" : "Under"} ${l}, ${name} ${american(r[i])}">${american(r[i])}</button>` : '<span class="na">—</span>';
    return `<div class="bkr2${here ? "" : " alt"}"><span>${name}${D.sources.books[b] && D.sources.books[b].stale ? ' <span class="tg tq">STALE</span>' : ""}</span><button class="bl" data-pl="${l}" aria-label="Use line ${l}">${l === null ? "—" : l}</button>${px("over", 1)}${px("under", 2)}</div>`;
  }).join("");
  const fr = fair.p === null ? "" : `<div class="bkr2 fr"><span>Fair${fair.n === 1 ? " <small>1 book</small>" : ""}</span><span class="bl">${line}</span><span>${american(1 / fair.p)}</span><span>${american(1 / (1 - fair.p))}</span></div>`;
  $("#pproj").innerHTML = projCard(p, line, side);
  $("#pbk").innerHTML = `<div class="bkh"><span>BOOKS</span><button class="lnp" id="lnp" aria-haspopup="dialog" aria-label="Line ${line}">LINE${ICON.down}</button><span>OVER</span><span>UNDER</span></div>${bk}${fr}
    <div class="sec2"><h3>Alt Lines · ${side === "under" ? "Under" : "Over"}</h3>${ladder(p, win, side, line, (wins.find(w => w[0] === DT.win) || ["", "L10"])[1])}</div>
    <div class="sec2"><h3>Line Movement</h3>${histChart(p)}</div>`;
  }
  // game log
  const logRows = win.slice().reverse().map(l => {
    const v = statValue(l, p.market), r = v === null ? "–" : v > line ? '<span class="ov">O</span>' : v < line ? '<span class="un">U</span>' : '<span class="pu">P</span>';
    return `<tr><td>${esc(l.date.slice(5).replace("-", "/"))}</td><td>${l.home ? "" : "@"}${esc(l.opp)}${l.team !== p.team ? " <span style='color:var(--l3)'>(" + esc(l.team) + ")</span>" : ""}</td><td class="r">${l.min}</td><td class="r">${l.fga ?? "–"}</td><td class="r"><b>${v === null ? "–" : v}</b></td><td class="r">${r}</td></tr>`;
  }).join("");
  const lg = $("#plog"), wasOpen = !!$("details", lg) && $("details", lg).open;
  lg.innerHTML = `<details class="log"${wasOpen ? " open" : ""}><summary>Game Log · ${win.length}</summary><table><thead><tr><th>Date</th><th>Opp</th><th class="r">Min</th><th class="r">FGA</th><th class="r">${esc(short(p.market))}</th><th class="r">${line}</th></tr></thead><tbody>${logRows || '<tr><td colspan="6">No games.</td></tr>'}</tbody></table></details>`;
  bindLive(p, logs, without);
}
function bindLive(p, logs, without) {
  const pg = $("#pg"), c = p.ctx || {};
  const keep = sel => { const e = !TOUCH && $(sel, pg); if (e) e.focus({preventScroll: true}); };
  $$("[data-t]", pg).forEach(b => b.onclick = () => { const k = b.dataset.t; DT[k] = !DT[k]; updateProp(); keep(`[data-t="${k}"]`); });
  $$("[data-r]", pg).forEach(b => b.onclick = () => {
    const k = b.dataset.r;
    DT.ovs = DT.ovs.filter(x => x !== k);
    if (DT.ranges[k] || DT.open[k]) { delete DT.ranges[k]; DT.open[k] = false; } else { DT.open[k] = true; DT.fresh = k; if (OVL[k]) DT.ovs.push(k); }
    updateProp(); keep(`[data-r="${k}"]`);
  });
  $$("[data-k]", pg).forEach(b => b.onclick = () => { const k = b.dataset.k, raw = b.dataset.v, v = raw === "true" ? true : raw === "false" ? false : raw; DT[k] = DT[k] === v ? null : v; updateProp(); keep(`[data-k="${k}"][data-v="${raw}"]`); });
  $$("[data-wo]", pg).forEach(b => b.onclick = () => { const k = b.dataset.wo; DT.without[k] = !DT.without[k]; if (DT.without[k]) delete DT.with[k]; updateProp(); keep(`[data-wo="${k}"]`); });
  $$("[data-mw]", pg).forEach(b => b.onclick = () => { delete DT.with[b.dataset.mw]; updateProp(); });
  $$("[data-mo]", pg).forEach(b => b.onclick = () => { delete DT.without[b.dataset.mo]; updateProp(); });
  const mts = $("#mts", pg); if (mts) mts.onclick = () => mateSheet(p, logs, without);
  $$("[data-ps]", pg).forEach(b => b.onclick = () => {
    const l = +b.dataset.pl, sd = b.dataset.ps;
    if (ST.side === sd && DT.line === l) return;
    DT.line = l;
    if (ST.side !== sd) { ST.side = sd; save(); renderList(); tabbar(); }
    updateProp(); keep(`[data-ps="${sd}"]`);
  });
  $$(".bl", pg).forEach(b => b.onclick = () => { const l = +b.dataset.pl; if (DT.line !== l) { DT.line = l; updateProp(); } });
  $$("[data-ll]", pg).forEach(b => b.onclick = () => { const l = +b.dataset.ll; if (DT.line !== l) { DT.line = l; updateProp(); keep(`[data-ll="${l}"]`); } });
  const clr = $("#clr", pg); if (clr) clr.onclick = () => { Object.assign(DT, {home: null, starter: null, result: null, rest: null, ranges: {}, without: {}, with: {}, dvp: false, def: false, open: {}, ovs: []}); updateProp(); };
  $("#more", pg).onclick = () => { DT.more = $("#more", pg).getAttribute("aria-expanded") !== "true"; if (!DT.more) { MORE_R.forEach(k => { DT.open[k] = false; delete DT.ranges[k]; }); DT.ovs = DT.ovs.filter(k => MORE_R.indexOf(k) < 0); Object.assign(DT, {home: null, result: null, rest: null}); } updateProp(); keep("#more"); };
  $("#lnb", pg).onclick = () => lineSheet(p);
  const lnp = $("#lnp", pg); if (lnp) lnp.onclick = () => lineSheet(p);
  $("#psb", pg).onclick = () => openSheet(`<h2 id="sht">Position rank</h2>${c.pos_rank
    ? `<div class="kv"><span>Rank</span><b>${ord(c.pos_rank)} of ${c.pos_n}</b></div><div class="kv"><span>Group</span><b>${esc((GRPN[MU_GROUP(c.pos)] || "position").replace(/^./, x => x.toUpperCase()))}</b></div><div class="kv"><span>Stat</span><b>${esc(NAME[p.market])} per game</b></div><div class="kv"><span>Season</span><b>${esc(c.pos_season || "")}</b></div>`
    : '<div class="empty"><b>Not ranked yet</b></div>'}<div class="acts"><button class="btn pri" id="ok1">Done</button></div>`, s2 => { $("#ok1", s2).onclick = closeSheet; });
  $("#mub", pg).onclick = () => { if (p.opp) openMatchup(p); };
  const pjsc = $("#pjsc", pg); if (pjsc) pjsc.onclick = projScoreSheet;
  $$(".rp", pg).forEach(gp => {
    const k = gp.dataset.rk, lo = +gp.dataset.lo, hi = +gp.dataset.hi, fil = $(".fil", gp), rv = $(".rv", gp);
    dualRange($(".dual2", gp), lo, hi, DT.ranges[k] || [lo, hi], 13, (v, fl, fr) => {
      fil.style.left = `calc(4px + (100% - 26px) * ${fl})`; fil.style.right = `calc(4px + (100% - 26px) * ${fr})`;
      rv.textContent = `${v[0]} – ${v[1]}`; rv.hidden = v[0] === lo && v[1] === hi;
    }, (v, i) => {
      if (v[0] === lo && v[1] === hi) delete DT.ranges[k]; else DT.ranges[k] = v.slice();
      DT.open[k] = true; updateProp(); keep(`.rp[data-rk="${k}"] .th.${i ? "b" : "a"}`);
    });
  });
}
// two thumbs (role=slider) for a dual-range control
const thumbs = (lab, b) => ["a", "b"].map((c, i) => `<span class="th ${c}" role="slider" tabindex="0" aria-label="${lab} ${i ? "maximum" : "minimum"}" aria-valuemin="${b[0]}" aria-valuemax="${b[1]}"></span>`).join("");
// Dual range on pointer events. Two stacked <input type=range> can't be dragged in iOS Safari (it ignores pointer-events on the
// thumb), so the track takes the touch and moves the nearer thumb: a sideways drag or a tap moves it, a vertical swipe still
// scrolls (touch-action: pan-y; the browser then cancels the pointer and the values stay). inset = px from each end to a
// thumb's centre at lo / hi. paint(v, leftFrac, rightFrac) runs on every move; done(v, thumb) once per drag, tap or key press.
function dualRange(el, lo, hi, cur, inset, paint, done) {
  const v = cur.slice(), th = $$(".th", el), span = hi - lo;
  const show = () => { th.forEach((t, i) => { t.style.left = `calc(${inset}px + (100% - ${2 * inset}px) * ${(v[i] - lo) / span})`; t.setAttribute("aria-valuenow", v[i]); });
                       paint(v, (v[0] - lo) / span, (hi - v[1]) / span); };
  const set = (i, x) => { x = Math.max(lo, Math.min(hi, x)); v[i] = i ? Math.max(x, v[0]) : Math.min(x, v[1]); show(); };
  const at = cx => { const r = el.getBoundingClientRect(), f = (cx - r.left - el.clientLeft - inset) / (el.clientWidth - 2 * inset);
                     return lo + Math.round(Math.max(0, Math.min(1, f)) * span); };
  // when the thumbs sit together the drag direction decides which one moves
  const pick = x => x < v[0] ? 0 : x > v[1] ? 1 : v[0] === v[1] ? -1 : x - v[0] <= v[1] - x ? 0 : 1;
  let drag = null, was = null, x0 = 0, moved = false;
  el.onpointerdown = e => { drag = pick(at(e.clientX)); was = v.slice(); x0 = e.clientX; moved = false; };
  el.onpointermove = e => {
    if (drag === null || (!moved && Math.abs(e.clientX - x0) < 4)) return;
    if (!moved) { moved = true; try { el.setPointerCapture(e.pointerId); } catch (_) {} }
    const x = at(e.clientX);
    if (drag < 0) { if (x === v[0]) return; drag = x < v[0] ? 0 : 1; }
    set(drag, x);
  };
  el.onpointerup = e => {
    if (drag === null) return;
    if (!moved && drag >= 0) set(drag, at(e.clientX));             // a tap moves the nearer thumb there
    const i = drag; drag = null;
    if (v.join() !== was.join()) done(v, i);
  };
  el.onpointercancel = () => { if (drag === null) return; drag = null; v[0] = was[0]; v[1] = was[1]; show(); };
  th.forEach((t, i) => t.onkeydown = e => {
    const d = {ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -5, PageUp: 5}[e.key];
    const x = e.key === "Home" ? lo : e.key === "End" ? hi : d ? v[i] + d : null;
    if (x === null) return;
    e.preventDefault(); set(i, x); done(v, i);
  });
  show();
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
    ${rows}
    <div class="acts"><button class="btn pri" id="ls-ok">Done</button></div>`, s => {
    const set = v => { DT.line = Math.max(0.5, Math.round(v * 2) / 2); $("#ls-v", s).textContent = DT.line; };
    $("#ls-m", s).onclick = () => set(DT.line - .5); $("#ls-p", s).onclick = () => set(DT.line + .5);
    $$("[data-l]", s).forEach(b => b.onclick = () => { set(+b.dataset.l); closeSheet(); updateProp(); });
    $("#ls-ok", s).onclick = () => { closeSheet(); updateProp(); };
  });
}
// ── the Matchup page (from the gauge): the grade and its parts, then "<OPP> Team Defense": the opponent's recent games
// against players of a position group, each with his result, closing line and over price (docs/vs/{TEAM}.json, nba_vs);
// a row opens that game's box score ──
let MUP = null;
const VS_GRP = [["G", "Guards"], ["F", "Forwards"], ["C", "Centers"]];
const initialName = n => { const i = String(n || "").indexOf(" "); return i > 0 ? n[0] + ". " + n.slice(i + 1) : n || ""; };
function openMatchup(p, push) {
  if (!p) return;
  MUP = {p: p, grp: VS_GRP.some(g => g[0] === (p.ctx || {}).group) ? p.ctx.group : "G", mkt: p.market, more: false, rows: null,
         shView: "player", shSeason: null, shMode: "shots"};
  if (push !== false) history.pushState({p: p.id, mu: 1}, "", hashState());
  const mp = $("#mp");
  mp.hidden = false;
  renderMatchup();
  mp.scrollTop = 0;
  fetch(`vs/${encodeURIComponent(p.opp || "")}.json`).then(r => r.ok ? r.json() : null).catch(() => null)
    .then(j => { if (MUP && MUP.p === p) { MUP.rows = j && j.rows || []; vsTable(); } });
  const go = () => {
    if (!MUP || mp.classList.contains("on")) return;
    mp.classList.add("on");
    if (!REDUCED && !document.hidden) mp.animate([{transform: "translateX(100%)"}, {transform: "none"}], {duration: 440, easing: EASE});
  };
  requestAnimationFrame(() => requestAnimationFrame(go)); setTimeout(go, 150);
}
function closeMatchup(instant) {
  const mp = $("#mp"), done = () => { if (!MUP && !mp.hidden) { mp.hidden = true; mp.innerHTML = ""; } };
  MUP = null;
  mp.classList.remove("on");
  if (instant || REDUCED) done();
  else { mp.animate([{transform: "none"}, {transform: "translateX(100%)"}], {duration: 380, easing: EASE}).finished.then(done, done); setTimeout(done, 440); }
}
function renderMatchup() {
  const p = MUP.p, c = p.ctx || {}, g = gameOf(p.gid), side = ST.side, gr = grade(p, side), mp = $("#mp");
  const rk = (r, n) => r ? `<span class="rk ${rankCls(r, n, side) === "good" ? "g" : rankCls(r, n, side) === "bad" ? "r" : "n"}">${ord(r)}</span>` : "—";
  const dd = (k, opts, cur) => `<label class="dd"><span>${esc((opts.find(o => o[0] === cur) || opts[0])[1])}</span>${ICON.down}
    <select data-dd="${k}" aria-label="${k === "grp" ? "Position" : "Stat"}">${opts.map(([v, t]) => `<option value="${v}"${v === cur ? " selected" : ""}>${esc(t)}</option>`).join("")}</select></label>`;
  mp.innerHTML = `<div class="ph"><button class="cb bk" aria-label="Back">${ICON.back}</button>
      <div class="ph-t"><b>${esc(p.player)} vs ${esc(p.opp || "")}</b><span>Matchup</span></div><span class="sp2"></span>
      <button class="cb" id="mps" aria-label="Search">${ICON.search}</button><button class="cb" id="mpm" aria-label="Menu">${ICON.ham}</button></div>
    <div class="mpc">
      <div class="mpg">${gauge(gr)}<div><b>${gr ? "Grade " + gr.g : "Not graded yet"}</b><span>${esc(NAME[p.market])} · ${side === "under" ? "Under" : "Over"} ${DT.line === null ? "" : DT.line}</span></div></div>
      <div class="kv"><span>DvP · ${esc(short(p.market))} to ${GRPN[c.group] || "his position"}</span><b>${rk(c.dvp_rank, c.teams)}</b></div>
      <div class="kv"><span>Def Rank · points allowed</span><b>${rk(c.def_rank, c.teams)}</b></div>
      <div class="kv"><span>Pace</span><b>${c.pace_rank ? ord(c.pace_rank) + " fastest" : "—"}</b></div>
      ${g.lines ? `<div class="kv"><span>Game</span><b>${g.lines.total ? "Total " + g.lines.total : ""}${g.lines.spread_home !== undefined ? " · " + esc(g.home) + " " + (g.lines.spread_home > 0 ? "+" : "") + g.lines.spread_home : ""}</b></div>` : ""}
      <div class="mpft"><div><span>Regular Season</span><b>${esc(D.season.slice(0, 4))}</b></div>
        <button class="cb" id="mpi" aria-label="How the ranks are built">${ICON.info}</button><button class="cb" id="mpsh" aria-label="Share">${ICON.share}</button></div>
    </div>
    <h2 class="mpt">${esc(p.opp || "")} Team Defense</h2>
    <div class="mpf"><span>Recent Games vs</span>${dd("grp", VS_GRP, MUP.grp)}${dd("mkt", TAB_ORDER.map(m => [m, NAME[m]]), MUP.mkt)}</div>
    <div id="vst"></div>
    <div class="shc wg" id="wgd"></div>
    <div class="shc" id="shc"></div>`;
  $(".bk", mp).onclick = () => history.back();
  $("#mps", mp).onclick = () => { history.go(-2); setTimeout(() => { if (ST.view !== "props") { ST.view = "props"; save(); tabbar(); renderList(); } const q = $("#q"); if (q) q.focus(); }, 480); };
  $("#mpm", mp).onclick = leagueSheet;
  $("#mpsh", mp).onclick = () => { const url = location.href; if (navigator.share) navigator.share({title: `${p.player} vs ${p.opp}`, url: url}).catch(() => {}); else if (navigator.clipboard) navigator.clipboard.writeText(url).then(() => { $("#live").textContent = "Link copied"; }); };
  $("#mpi", mp).onclick = () => openSheet(`<h2 id="sht">Ranks</h2>
    <div class="kv"><span>Teams ranked</span><b>${c.teams || "—"}</b></div>
    <div class="kv"><span>${esc(p.opp || "")} games this season</span><b>${c.rank_n != null ? c.rank_n : c.opp_games || 0}</b></div>
    <div class="kv"><span>Last season's weight</span><b>${c.rank_n != null ? Math.round(15 / (15 + c.rank_n) * 100) + "%" : "—"}</b></div>
    <div class="kv"><span>1st</span><b>the toughest</b></div>
    <div class="acts"><button class="btn pri" id="mpi-ok">Done</button></div>`, s => { $("#mpi-ok", s).onclick = closeSheet; });
  guardCard();
  shotLoad(D.season).then(j => {                       // this season once the opponent has 10 games, else last season
    if (!MUP || MUP.p !== p) return;
    const t = j && j.teams[p.opp];
    MUP.shSeason = t && t.gp >= 10 ? D.season : prevSeason(D.season);
    shotCard();
  });
  $$("[data-dd]", mp).forEach(sel => sel.onchange = () => {
    MUP[sel.dataset.dd] = sel.value; MUP.more = false;
    $("span", sel.parentNode).textContent = sel.options[sel.selectedIndex].text;
    vsTable();
  });
  vsTable();
}
function vsTable() {
  const el = $("#vst");
  if (!el || !MUP) return;
  if (!MUP.rows) { el.innerHTML = '<div class="vsk">' + '<div class="sk"></div>'.repeat(5) + "</div>"; return; }
  const all = MUP.rows.filter(r => r[5] === MUP.grp), rows = all.slice(0, MUP.more ? 10 : 5), mk = MUP.mkt;
  if (!rows.length) { el.innerHTML = '<div class="empty"><b>No games</b></div>'; return; }
  const tr = r => {
    const v = statValue({pts: r[7], reb: r[8], ast: r[9], fg3m: r[10]}, mk), ln = (r[11] || {})[mk];
    const res = !ln ? "" : v > ln[0] ? '<i class="up">▲</i>' : v < ln[0] ? '<i class="dn">▼</i>' : "";
    const d = r[0].slice(5).split("-").map(Number).join("/");
    return `<tr data-g="${esc(r[1])}" data-t="${esc(r[2])}" data-pid="${r[3]}"><td>${esc(initialName(r[4]))}</td><td>${res}${v === null ? "–" : v}</td>
      <td>${ln ? ln[0] : "–"}</td><td>${ln ? american(ln[1]) : "–"}</td><td class="cd"><b>${esc(r[2])}</b> ${d}</td></tr>`;
  };
  el.innerHTML = `<table class="vs"><colgroup><col style="width:35.5%"><col style="width:16%"><col style="width:15.5%"><col style="width:16%"><col></colgroup>
    <thead><tr><th>PLAYER</th><th>RESULT</th><th>LINE</th><th>ODDS</th><th>DATE</th></tr></thead><tbody>${rows.map(tr).join("")}</tbody></table>
    ${all.length > 5 ? `<button class="vsm" id="vsm" aria-expanded="${MUP.more}">${MUP.more ? "Less Results" : "More Results"}${ICON.down}</button>` : ""}`;
  const m = $("#vsm", el); if (m) m.onclick = () => { MUP.more = !MUP.more; vsTable(); };
  $$("tr[data-g]", el).forEach(t => { t.onclick = () => boxSheet(t.dataset.g, t.dataset.t, {market: mk, pid: +t.dataset.pid});
    t.onpointerdown = () => boxGet(t.dataset.g).catch(() => {}); });
}
// ── the shot chart (docs/shots/{season}.json, nba_shots): the six zones on a half court, the player's shooting or
// what the opponent allows, each zone shaded against the league's FG% there (green = better for the shooter); then the
// zones where the opponent gives up the most points a game over the league's average, beside how often he shoots there
const SHOTS = new Map();
function shotLoad(season) {
  if (!SHOTS.has(season)) SHOTS.set(season, fetch(`shots/${encodeURIComponent(season)}.json`).then(r => r.ok ? r.json() : null).catch(() => null));
  return SHOTS.get(season);
}
const prevSeason = s => (+s.slice(0, 4) - 1) + "-" + s.slice(2, 4);
const SH_Z = ["Restricted Area", "Paint", "Mid-Range", "Left Corner 3", "Right Corner 3", "Above the Break 3"];
const SH_PTS = [2, 2, 2, 3, 3, 3];
// a half court to scale, basket at the top (court units: 10 a foot, the NBA's shot coordinates)
const SH_R3 = 237.5, SH_CX = 220, SH_CY = Math.sqrt(SH_R3 * SH_R3 - SH_CX * SH_CX), SH_B = -47.5, SH_BOT = 300;
const SH_PATH = [
  "M0,-40A40,40 0 1 1 0,40A40,40 0 1 1 0,-40Z",
  `M-80,${SH_B}H80V142.5H-80Z M0,-40A40,40 0 1 0 0,40A40,40 0 1 0 0,-40Z`,
  `M-${SH_CX},${SH_B}V${SH_CY}A${SH_R3},${SH_R3} 0 0 0 ${SH_CX},${SH_CY}V${SH_B}Z M-80,${SH_B}V142.5H80V${SH_B}Z`,
  `M-250,${SH_B}H-${SH_CX}V${SH_CY}H-250Z`,
  `M${SH_CX},${SH_B}H250V${SH_CY}H${SH_CX}Z`,
  `M-250,${SH_CY}H-${SH_CX}A${SH_R3},${SH_R3} 0 0 0 ${SH_CX},${SH_CY}H250V${SH_BOT}H-250Z`];
const SH_LAB = [[0, 6], [0, 104], [0, 186], [-235, 40], [235, 40], [0, 268]];
// each player's shots, for the dots (docs/shots/p/{pid}.json, nba_shots): {s: {season: [x, y, made, ...]}}
const SHOTP = new Map();
function shotDots(pid) {
  if (!SHOTP.has(pid)) SHOTP.set(pid, fetch(`shots/p/${pid}.json`).then(r => r.ok ? r.json() : null).catch(() => null));
  return SHOTP.get(pid);
}
const pctOf = z => z && z[1] ? z[0] / z[1] : null;
function shFill(d) {                                   // d = FG% minus the league's, in points: green above, red below
  if (d === null) return "#191919";
  const a = Math.min(1, Math.abs(d) / 12);
  return d >= 0 ? `rgba(40,218,142,${(.12 + .5 * a).toFixed(3)})` : `rgba(255,69,58,${(.12 + .5 * a).toFixed(3)})`;
}
function shotCard() {
  const el = $("#shc");
  if (!el || !MUP || !MUP.shSeason) return;
  const p = MUP.p, season = MUP.shSeason;
  const dotsOn = MUP.shView !== "def" && MUP.shMode !== "zones";
  Promise.all([shotLoad(season), dotsOn ? shotDots(p.pid) : null]).then(([j, dots]) => {
    if (!MUP || MUP.p !== p || MUP.shSeason !== season) return;
    const t = j && j.teams[p.opp], me = j && j.players[String(p.pid)];
    if (!j || !t) { el.innerHTML = '<div class="shh">SHOT CHART</div><div class="empty"><b>No shot data</b></div>'; return; }
    const lg = j.league.map(pctOf), opp = t.opp, def = MUP.shView === "def";
    // ranks among the teams by the FG% they allow in each zone: 1st = the lowest (the toughest), as the other ranks
    const all = Object.values(j.teams), rk = k => 1 + all.filter(x => pctOf(x.opp[k]) < pctOf(opp[k])).length;
    const zs = SH_Z.map((_, k) => {
      const z = def ? opp[k] : me && me[k], f = pctOf(z);
      return {f: f, d: f === null || lg[k] === null ? null : (f - lg[k]) * 100, sub: def ? (opp[k][1] ? ord(rk(k)) : "") : z && z[1] ? `${z[0]}/${z[1]}` : ""};
    });
    const lines = '<g class="shl"><path d="M-250,-47.5H250"/><path d="M-80,-47.5V142.5H80V-47.5"/><path d="M-60,142.5A60,60 0 0 0 60,142.5"/>' +
      `<path d="M-${SH_CX},-47.5V${SH_CY}A${SH_R3},${SH_R3} 0 0 0 ${SH_CX},${SH_CY}V-47.5"/><path d="M-30,-7.5H30"/><circle cx="0" cy="0" r="7.5"/>` +
      '<path d="M-40,0A40,40 0 0 0 40,0"/></g>';
    // the dots: every shot he took, made (green) over missed (red rings); the zones keep only their faint lines
    const pts = dotsOn && dots && dots.s[season] || [];
    const dotSvg = () => { const miss = [], make = [];
      for (let i = 0; i + 2 < pts.length; i += 3) (pts[i + 2] ? make : miss).push(`<circle cx="${pts[i]}" cy="${pts[i + 1]}" r="4.6"/>`);
      return `<g class="shm">${miss.join("")}</g><g class="shk2">${make.join("")}</g>`; };
    const court = `<svg class="shct" viewBox="-252 -50 504 352" role="img" aria-label="${def ? esc(p.opp) + " defense" : esc(p.player)} ${dotsOn ? "shots" : "by zone"}, ${esc(season)}"><defs><clipPath id="shclip"><rect x="-250" y="-47.5" width="500" height="347.5"/></clipPath></defs>` +
      (dotsOn ? `<rect x="-250" y="-47.5" width="500" height="347.5" fill="#131313"/>${SH_PATH.map(d => `<path d="${d}" fill="none" class="shz" fill-rule="evenodd"/>`).join("")}${lines}<g clip-path="url(#shclip)">${dotSvg()}</g>`
      : zs.map((z, k) => `<path d="${SH_PATH[k]}" fill="${shFill(z.d)}" fill-rule="evenodd"/>`).join("") + lines +
        zs.map((z, k) => `<text x="${SH_LAB[k][0]}" y="${SH_LAB[k][1]}" class="shv${k === 3 || k === 4 ? " sm" : ""}">${z.f === null ? "–" : Math.round(z.f * 100) + "%"}</text>` +
          (z.sub ? `<text x="${SH_LAB[k][0]}" y="${SH_LAB[k][1] + (k === 3 || k === 4 ? 19 : 23)}" class="shs">${esc(z.sub)}</text>` : "")).join("")) + "</svg>";
    const made = (() => { let m = 0; for (let i = 2; i < pts.length; i += 3) m += pts[i]; return m; })(), att = pts.length / 3;
    // where the opponent gets scored on: points a game it allows in each zone over the league's average for a team
    const games = all.reduce((a, x) => a + x.gp, 0) || 1, mine = me ? me.reduce((a, z) => a + z[1], 0) : 0;
    const rows = SH_Z.map((nm, k) => ({nm: nm, k: k, d: t.gp ? opp[k][0] * SH_PTS[k] / t.gp - j.league[k][0] * SH_PTS[k] / games : null}))
      .filter(r => r.d !== null).sort((a, b) => b.d - a.d);
    const last = lastName(p.player);
    el.innerHTML = `<div class="shh"><span class="av">${head(p.pid)}</span><b>SHOT CHART</b>${logo(p.opp, "shl0")}</div>
      <div class="seg" role="group" aria-label="View"><span class="pill2"></span><button data-shv="player" aria-pressed="${!def}">${esc(last)}</button><button data-shv="def" aria-pressed="${def}">${esc(p.opp)} Defense</button></div>
      <div class="shy" role="group" aria-label="Season">${[D.season, prevSeason(D.season)].map(s => `<button class="chip" data-shs="${s}" aria-pressed="${s === season}">${s.slice(0, 4)}</button>`).join("")}
        ${def ? `<span>${t.gp} games</span>` : `<span class="shmd" role="group" aria-label="Show">${[["shots", "Shots"], ["zones", "Zones"]].map(([k, l]) => `<button class="chip" data-shm="${k}" aria-pressed="${(MUP.shMode || "shots") === k}">${l}</button>`).join("")}</span>`}</div>
      ${court}
      ${dotsOn ? `<div class="shk"><span><b class="d1"></b>Made ${made}</span><span><b class="d0"></b>Missed ${att - made}</span><span>${att ? Math.round(made / att * 100) + "% of " + att : "No shots"}</span></div>`
        : `<div class="shk"><span>Below league avg</span><i></i><span>Above</span></div>`}
      <h3 class="shw">Where ${esc(p.opp)} gets scored on</h3>
      ${rows.map(r => { const z = me && me[r.k];
        return `<div class="kv shr"><span>${r.nm}<small>${esc(last)}: ${z && z[1] ? Math.round(z[1] / mine * 100) + "% of shots · " + Math.round(z[0] / z[1] * 100) + "%" : "no shots"}</small></span>
          <b><em class="${r.d > 0 ? "up" : "dn"}">${r.d > 0 ? "+" : ""}${r.d.toFixed(1)} pts/g</em><small>${opp[r.k][1] ? Math.round(pctOf(opp[r.k]) * 100) + "% allowed · " + ord(rk(r.k)) : "–"}</small></b></div>`; }).join("")}`;
    const seg = $(".seg", el);
    slide(seg, true);
    $$("[data-shv]", el).forEach(b => b.onclick = () => { if (MUP.shView !== b.dataset.shv) { MUP.shView = b.dataset.shv; shotCard(); } });
    $$("[data-shs]", el).forEach(b => b.onclick = () => { if (MUP.shSeason !== b.dataset.shs) { MUP.shSeason = b.dataset.shs; shotCard(); } });
    $$("[data-shm]", el).forEach(b => b.onclick = () => { if ((MUP.shMode || "shots") !== b.dataset.shm) { MUP.shMode = b.dataset.shm; shotCard(); } });
  });
}
// ── who guards him (docs/matchups/{pid}.json, nba_defmatch: NBA.com's tracking matchups): the opponent's players now
// (the player index) who have guarded him, most possessions first; possessions, points, FG and 3PT in them; the season
// with the most possessions against them first; a row opens the defender ──
const MATCHC = new Map();
function matchLoad(pid) {
  if (!MATCHC.has(pid)) MATCHC.set(pid, fetch(`matchups/${pid}.json`).then(r => r.ok ? r.json() : null).catch(() => null));
  return MATCHC.get(pid);
}
function guardCard() {
  const el = $("#wgd");
  if (!el || !MUP) return;
  const p = MUP.p;
  Promise.all([matchLoad(p.pid), playerIndex()]).then(([m, pl]) => {
    if (!MUP || MUP.p !== p) return;
    const roster = new Set(pl.filter(r => r[2] === p.opp).map(r => r[0])), s = (m && m.s) || {};
    const vs = season => (s[season] || []).filter(r => roster.has(r[0]));
    const poss = season => vs(season).reduce((a, r) => a + r[3], 0);
    if (!MUP.gSeason) MUP.gSeason = poss(D.season) >= poss(prevSeason(D.season)) ? D.season : prevSeason(D.season);
    const rows = vs(MUP.gSeason), pc = (m_, a) => a ? Math.round(m_ / a * 100) + "%" : "–";
    const head_ = `<div class="shh"><span class="av">${head(p.pid)}</span><b>WHO GUARDS HIM</b>${logo(p.opp, "shl0")}</div>
      <div class="shy" role="group" aria-label="Season">${[D.season, prevSeason(D.season)].map(x => `<button class="chip" data-gs="${x}" aria-pressed="${x === MUP.gSeason}">${x.slice(0, 4)}</button>`).join("")}
        <span>${rows.length ? Math.round(poss(MUP.gSeason)) + " possessions" : ""}</span></div>`;
    el.innerHTML = head_ + (rows.length ? `<table class="vs"><colgroup><col style="width:38%"><col style="width:14%"><col style="width:12%"><col style="width:20%"><col></colgroup>
      <thead><tr><th>DEFENDER</th><th>POSS</th><th>PTS</th><th>FG</th><th>3PT</th></tr></thead>
      <tbody>${rows.slice(0, 8).map(r => `<tr data-vp="${r[0]}"><td>${esc(initialName(r[1]))}</td><td>${Math.round(r[3])}</td><td>${Math.round(r[4])}</td>
        <td>${Math.round(r[5])}/${Math.round(r[6])} <small>${pc(r[5], r[6])}</small></td><td>${Math.round(r[7])}/${Math.round(r[8])}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty"><b>No matchups vs ${esc(p.opp || "")} yet</b></div>`);
    $$("[data-gs]", el).forEach(b => b.onclick = () => { if (MUP.gSeason !== b.dataset.gs) { MUP.gSeason = b.dataset.gs; guardCard(); } });
    $$("tr[data-vp]", el).forEach(t => t.onclick = () => openPlayer(+t.dataset.vp));
  });
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
// the With / Without rows: each teammate (out tonight tagged), his games beside and without him, Any / With / W/O
function mateRows(p, logs, without, dr) {
  const rep = ((D.inj_report || {})[gameOf(p.gid).date + "|" + p.team] || {}).players || [], mine = logs.filter(l => l.team === p.team);
  return matesAll(p, without).map(m => {
    const e = rep.find(x => x.pid === +m.key), v = dr.with[m.key] ? "w" : dr.without[m.key] ? "o" : "";
    const nw = mine.filter(l => m.played.indexOf(l.gid) >= 0).length, no = mine.filter(l => l.date >= m.since && m.played.indexOf(l.gid) < 0).length;
    return `<div class="mrr"><span class="av mav">${head(+m.key)}</span><div class="mrn"><b>${esc(m.name)}${e && INJ_C[e.status] ? `<span class="tg ${INJ_C[e.status]}">${INJ_S[e.status]}</span>` : ""}</b>
      <small>${m.mpg != null ? (+m.mpg).toFixed(1) + " MPG · " : ""}${nw} with · ${no} w/o</small></div>
      <div class="seg mseg" role="group" aria-label="${esc(m.name)}">${[["", "Any"], ["w", "With"], ["o", "W/O"]].map(([k, t]) =>
        `<button data-mk2="${m.key}" data-mv="${k}" aria-pressed="${v === k}">${t}</button>`).join("")}</div></div>`;
  }).join("");
}
function bindMates(s, dr, upd) {
  $$("[data-mk2]", s).forEach(b => b.onclick = () => {
    const k = b.dataset.mk2, v = b.dataset.mv;
    delete dr.with[k]; delete dr.without[k];
    if (v === "w") dr.with[k] = true; else if (v === "o") dr.without[k] = true;
    $$(`[data-mk2="${k}"]`, s).forEach(x => x.setAttribute("aria-pressed", x === b)); upd();
  });
}
function mateSheet(p, logs, without) {
  const dr = {with: Object.assign({}, DT.with), without: Object.assign({}, DT.without)};
  const count = () => windowed(filterLogs(logs, chartF(p, gameOf(p.gid), p.ctx || {}, without, dr)), DT.win, D.season, p.opp).length;
  openSheet(`<h2 id="sht">With / Without</h2>${mateRows(p, logs, without, dr)}
    <div class="acts stk"><button class="btn" id="ms-reset">Reset</button><button class="btn pri" id="ms-ok"></button></div>`, s => {
    const upd = () => { const n = count(); $("#ms-ok", s).textContent = `Show ${n} game${n === 1 ? "" : "s"}`; };
    bindMates(s, dr, upd);
    $("#ms-reset", s).onclick = () => { DT.with = {}; DT.without = {}; closeSheet(); updateProp(); };
    $("#ms-ok", s).onclick = () => { DT.with = dr.with; DT.without = dr.without; closeSheet(); updateProp(); };
    upd();
  });
}
function playerFilters(p, logs, without) {
  const dr = {home: DT.home, starter: DT.starter, result: DT.result, rest: DT.rest, ranges: Object.assign({}, DT.ranges),
              without: Object.assign({}, DT.without), with: Object.assign({}, DT.with)};
  const count = () => windowed(filterLogs(logs, chartF(p, gameOf(p.gid), p.ctx || {}, without, dr)), DT.win, D.season, p.opp).length;
  const rng = RANGES.filter(([k]) => forMarket(k, p.market)).map(([k, lab]) => {
    const b = bounds(logs, k);
    if (!b || b[0] === b[1]) return "";
    const cur = dr.ranges[k] || b;
    return `<div class="rg" data-rk="${k}" data-lo="${b[0]}" data-hi="${b[1]}"><div class="rg-h"><span>${lab}</span><b class="rv">${cur[0]} – ${cur[1]}</b></div>
      <div class="dual2"><div class="fil"></div>${thumbs(lab, b)}</div><div class="rp-b"><span>${b[0]}</span><span>${b[1]}</span></div></div>`;
  }).join("");
  const segs = SEGS.map(([k, lab, opts]) => `<div class="sg"><span>${lab}</span><div class="seg" role="group" aria-label="${lab}">${opts.map(([v, t]) =>
    `<button data-sk="${k}" data-sv="${v === null ? "" : v}" aria-pressed="${dr[k] === v}">${t}</button>`).join("")}</div></div>`).join("");
  const mr = mateRows(p, logs, without, dr), wo = mr ? `<div class="sg"><span>With / Without</span></div>${mr}` : "";
  openSheet(`<h2 id="sht">Filter ${esc(p.player.split(" ").slice(-1)[0])}'s games</h2>${rng}${segs}${wo}
    <div class="acts stk"><button class="btn" id="pf-reset">Reset</button><button class="btn pri" id="pf-ok"></button></div>`, s => {
    const upd = () => { const n = count(); $("#pf-ok", s).textContent = `Show ${n} game${n === 1 ? "" : "s"}`; };
    $$(".rg", s).forEach(g => {
      const k = g.dataset.rk, lo = +g.dataset.lo, hi = +g.dataset.hi, fil = $(".fil", g), rv = $(".rv", g);
      dualRange($(".dual2", g), lo, hi, dr.ranges[k] || [lo, hi], 13, (v, fl, fr) => {
        fil.style.left = `calc(4px + (100% - 26px) * ${fl})`; fil.style.right = `calc(4px + (100% - 26px) * ${fr})`;
        rv.textContent = `${v[0]} – ${v[1]}`;
        if (v[0] === lo && v[1] === hi) delete dr.ranges[k]; else dr.ranges[k] = v.slice();
        upd();
      }, () => {});
    });
    $$("[data-sk]", s).forEach(b => b.onclick = () => {
      const k = b.dataset.sk, raw = b.dataset.sv, v = raw === "" ? null : raw === "true" ? true : raw === "false" ? false : raw;
      dr[k] = v; $$(`[data-sk="${k}"]`, s).forEach(x => x.setAttribute("aria-pressed", x === b)); upd();
    });
    bindMates(s, dr, upd);
    $("#pf-reset", s).onclick = () => { Object.assign(DT, {home: null, starter: null, result: null, rest: null, ranges: {}, without: {}, with: {}, dvp: false, def: false, open: {}, ovs: []}); closeSheet(); updateProp(); };
    $("#pf-ok", s).onclick = () => { Object.assign(DT, {home: dr.home, starter: dr.starter, result: dr.result, rest: dr.rest, ranges: dr.ranges, without: dr.without, with: dr.with}); closeSheet(); updateProp(); };
    upd();
  });
}
// ── data ──
function load() {
  if (!D) { LOADING = true; render(); }
  fetch("nba_props.json?t=" + Date.now(), {cache: "no-store"}).then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(j => {
      const first = !D; D = j; ERR = null; LOADING = false; RATES = new Map(); ROWS = new Map(); VP = new Map();
      const y = window.scrollY;
      render(); if (!first) window.scrollTo(0, y);
      if (CUR) { const pg = $("#pg"), py = pg.scrollTop; renderProp(); pg.scrollTop = py; }
      $("#live").textContent = "Props updated";
      if (first && HASH_P) { history.replaceState(null, "", hashState()); openProp(HASH_P); }
    })
    .catch(e => { LOADING = false; ERR = e.message || String(e); if (!D) render(); else { const u = $("#upd"); if (u) u.textContent = "Refresh failed"; } });
}
const HASH_P = readHash();
history.scrollRestoration = "manual";     // Back must not make Safari re-scroll the list
{ const m = location.search.match(/[?&]st=(\d+)/); if (m) document.documentElement.style.setProperty("--st", m[1] + "px"); }
// Safari's edge swipe already animates the page away: after one, close without a second slide
document.addEventListener("touchstart", e => { if (e.touches[0].clientX < 24 || e.touches[0].clientX > innerWidth - 24) EDGE_T = e.timeStamp; }, {passive: true});
window.addEventListener("popstate", e => {
  const h = new URLSearchParams(location.hash.slice(1)), p = h.get("p"), swiped = e.timeStamp - EDGE_T < 1500;
  if (!$("#sheet").hidden) closeSheet();
  if (MUP && !h.get("mu")) closeMatchup(swiped);
  if (p && p !== CUR) openProp(p, false); else if (!p && CUR) closeProp(swiped);
  if (h.get("mu") && !MUP && CUR) openMatchup(propFor(CUR), false);
});
document.addEventListener("keydown", e => { if (e.key === "Escape") { if (!$("#sheet").hidden) closeSheet(); else if (MUP || CUR) history.back(); } });
document.addEventListener("DOMContentLoaded", () => {
  $("#scrim").onclick = closeSheet;
  sheetDrag();
  $("#app").addEventListener("click", e => {
    const b = e.target.closest(".pr[data-id],.mrw[data-id],.ijb[data-id]");
    if (b) { openProp(b.dataset.id); return; }
    const v = e.target.closest("[data-vp]"); if (v) openPlayer(+v.dataset.vp);
  });
  $("#sheet").addEventListener("click", e => { const v = e.target.closest(".bx tr[data-vp]"); if (v && +v.dataset.vp !== (PX && PX.p.pid)) openPlayer(+v.dataset.vp); });
  // the big headshot starts loading and decoding the moment a finger lands on a row, so it is ready when the page slides in
  const warm = new Set();
  $("#app").addEventListener("pointerdown", e => {
    const b = e.target.closest(".pr[data-id],.mrw[data-id],.ijb[data-id]"), pid = b && b.dataset.id.split("|")[1];
    if (!pid || warm.has(pid)) return;
    warm.add(pid); const im = new Image(); im.src = heroSrc(pid); if (im.decode) im.decode().catch(() => {});
  }, {passive: true});
  load();
  setInterval(load, 120000);
  setInterval(() => { const u = $("#upd"); if (u && D) u.textContent = ago(D.generated_at); }, 30000);
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
<nav id="tb" class="tb" aria-label="Views"></nav>
<div class="shade" aria-hidden="true"></div>
<div id="pg" class="pg" role="dialog" aria-modal="true" aria-label="Prop details" hidden></div>
<div id="mp" class="pg" role="dialog" aria-modal="true" aria-label="Matchup" hidden></div>
<div id="scrim" class="scrim" hidden></div>
<div id="sheet" class="sheet" role="dialog" aria-modal="true" aria-labelledby="sht" tabindex="-1" hidden></div>
<div id="live" class="sr" role="status" aria-live="polite"></div>
<script>__CORE__</script>
<script>__APP__</script>
</body>
</html>
"""


def page():
    return (PAGE.replace("__CSS__", CSS).replace("__CORE__", JS_CORE)
            .replace("__APP__", JS_APP.replace("__TEAM_ID__", json.dumps(TEAM_ID))))
