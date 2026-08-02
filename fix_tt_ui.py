"""TT card UI: full names, real odds with the FanDuel logo, and BetMGM prices in BetMGM gold.

Three changes, each applied to BOTH renderers — the Python bake AND the client JS that overwrites it
every 60s. Fixing one and not the other is the mistake that made the BetMGM bet invisible on the
phone earlier tonight, and it is the fifth time today two copies of one rule have drifted.

1. FULL NAMES. `.ttbnm` had `white-space:nowrap; overflow:hidden; text-overflow:ellipsis`, so on a
   phone "Krzysztof Juszczyk v Sebastian Szostok" truncates to the point of being unreadable — and
   a name you cannot read is a bet you cannot place. Now wraps onto a second line.

2. ODDS + FANDUEL LOGO, matching the WNBA card: `<span class="podds fd">-120</span>` plus
   book-fd.png. fd_board already carries over_odds/under_odds per match, AMERICAN, so the number
   shown is the actual posted price for the side we are on — not a derived one.

3. BETMGM PRICES IN BETMGM GOLD. A bet taken at a fresh BetMGM line now shows its price in the
   book's own gold with a matching badge, so FanDuel and BetMGM plays are never confused at a
   glance. There is no book-betmgm.png in docs/ (only fd and dk), so the badge is an inline SVG
   data URI — no binary asset to ship, and it stays crisp at any density.

Odds units differ by source and that matters: fd_board stores AMERICAN (-120), while the bmbets
`book` dict stores DECIMAL in `od`. Rendering one as the other would print a plausible, wrong price.
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "TTMGM_LOGO" in s:
    print("  = TT card UI already updated")
    raise SystemExit(0)

# ── shared asset: a gold BetMGM badge as an inline SVG (no PNG exists in docs/) ──────────────
LOGO_CONST = '''
# BetMGM badge as an inline SVG data URI. docs/ ships book-fd.png and book-dk.png only, and a new
# binary would have to be committed, served and cache-busted; a data URI stays crisp at any pixel
# density and cannot 404. Gold #c9a227 is BetMGM's brand tone, dark glyph for contrast on it.
TTMGM_LOGO = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'"
              "%3E%3Crect width='24' height='24' rx='6' fill='%23c9a227'/%3E%3Ctext x='12' y='16'"
              "font-size='8.5' font-weight='700' text-anchor='middle' fill='%23151b24'"
              " font-family='Arial,sans-serif'%3EMGM%3C/text%3E%3C/svg%3E")


'''
anchor = "def _tt_totals_card("
assert anchor in s, "tt card anchor missing"
s = s.replace(anchor, LOGO_CONST.lstrip("\n") + anchor, 1)

# ── 1. carry odds through the FanDuel loop ──────────────────────────────────────────────────
old_fd = """        entries.append({"start": start, "p1": m.get("p1", "?"), "p2": m.get("p2", "?"),
                        "line": line, "side": pick["side"], "hit": hit, "real": True})"""
new_fd = """        # the ACTUAL posted price for the side we are on (fd_board stores AMERICAN)
        _od = m.get("over_odds") if pick["side"] == "over" else m.get("under_odds")
        entries.append({"start": start, "p1": m.get("p1", "?"), "p2": m.get("p2", "?"),
                        "line": line, "side": pick["side"], "hit": hit, "real": True,
                        "odds": _od, "book": "FanDuel"})"""
assert old_fd in s, "fd entry anchor missing"
s = s.replace(old_fd, new_fd, 1)

# ── 2. carry odds through the bets (BetMGM) loop ────────────────────────────────────────────
old_bm = """        entries.append({"start": start, "p1": b.get("p1", "?"), "p2": b.get("p2", "?"),
                        "line": b["play_to"], "side": "over" if zone.startswith("O") else "under",
                        "hit": b.get("raw"), "real": True,
                        "book": "BetMGM" if not (b.get("book") or {}) else "BetMGM"})"""
new_bm = """        # bmbets stores DECIMAL in `od`; convert so the card never prints a decimal as American
        _bk = b.get("book") or {}
        _od = None
        try:
            _d = float(_bk.get("od")) if _bk.get("od") else None
            if _d and _d > 1:
                _od = round((_d - 1) * 100) if _d >= 2 else -round(100 / (_d - 1))
        except (TypeError, ValueError):
            _od = None
        entries.append({"start": start, "p1": b.get("p1", "?"), "p2": b.get("p2", "?"),
                        "line": b["play_to"], "side": "over" if zone.startswith("O") else "under",
                        "hit": b.get("raw"), "real": True, "odds": _od, "book": "BetMGM"})"""
assert old_bm in s, "bets entry anchor missing"
s = s.replace(old_bm, new_bm, 1)

# ── 3. render odds + the right logo ─────────────────────────────────────────────────────────
old_src = """        if x["real"]:
            _bk = x.get("book") or "FanDuel"
            lncell, src = f'{x["line"]:g}', f'<span class="fd">{_bk} · confirmed</span>'"""
new_src = """        if x["real"]:
            _bk = x.get("book") or "FanDuel"
            _mgm = _bk == "BetMGM"
            _o = x.get("odds")
            _otxt = ("" if _o is None else
                     (f'<span class="podds {"bmgm" if _mgm else "fd"}">'
                      f'{("+" + str(int(_o))) if int(_o) > 0 else int(_o)}</span>'
                      f'<img class="bklogo" src="{TTMGM_LOGO if _mgm else "book-fd.png"}" '
                      f'alt="{"MGM" if _mgm else "FD"}">'))
            lncell = f'{x["line"]:g}'
            src = (f'<span class="{"bmgm" if _mgm else "fd"}">{_bk} · confirmed</span>{_otxt}')"""
assert old_src in s, "source-render anchor missing"
s = s.replace(old_src, new_src, 1)

# ── 4. CSS — inside an f-string, so every brace is DOUBLED ──────────────────────────────────
old_css = "  .ttbnm {{ font-size:14px; color:#cdd5e0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}"
new_css = ("  /* FULL NAMES (2026-07-31, user): ellipsis truncation made Polish pairs unreadable on a\n"
           "     phone, and a name you cannot read is a bet you cannot place. Wrap instead. */\n"
           "  .ttbnm {{ font-size:14px; color:#cdd5e0; white-space:normal; overflow-wrap:anywhere;\n"
           "            line-height:1.3; }}\n"
           "  .ttbsb .bmgm {{ color:#c9a227; }}   /* BetMGM gold, so a book is never misread */\n"
           "  .podds.bmgm {{ color:#c9a227; }}")
assert old_css in s, "ttbnm css anchor missing"
s = s.replace(old_css, new_css, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.prettui.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + python bake: full names, FD odds+logo, BetMGM odds in gold")
