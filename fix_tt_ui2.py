"""TT card: full names, real odds + FanDuel logo, BetMGM prices in BetMGM gold — BOTH renderers.

The card is drawn twice: baked in Python, then overwritten every 60s by the browser. The Python
bets-pass added earlier is gone from the file (only the JS copy survives), so this re-applies it and
adds the UI work to both sides in one go. Fixing one and not the other is the mistake that made the
BetMGM bet invisible on the phone in the first place.

1. FULL NAMES. `.ttbnm` used `white-space:nowrap; text-overflow:ellipsis`, so a pair like
   "Krzysztof Juszczyk v Sebastian Szostok" truncates on a phone — and a name you cannot read is a
   bet you cannot place. Now wraps.

2. ODDS + FANDUEL LOGO, matching the WNBA card. fd_board carries over_odds/under_odds per match, so
   the price shown is the actual posted one for the side we are on.

3. BETMGM IN ITS OWN GOLD. So a BetMGM play is never misread as a FanDuel one at a glance. No
   book-betmgm.png exists in docs/ (only fd and dk), so the badge is an inline SVG data URI — no
   binary to commit or cache-bust, crisp at any density, cannot 404.

UNITS DIFFER AND IT MATTERS: fd_board stores AMERICAN (-120); the bmbets `book` dict stores DECIMAL
in `od`. Printing one as the other would show a plausible, wrong price.
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()
if "TTMGM_LOGO" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── shared badge ────────────────────────────────────────────────────────────────────────────
LOGO = '''
# BetMGM badge as an inline SVG data URI. docs/ ships book-fd.png and book-dk.png only; a new binary
# would need committing, serving and cache-busting. #c9a227 is BetMGM's gold, dark glyph for contrast.
TTMGM_LOGO = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'"
              "%3E%3Crect width='24' height='24' rx='6' fill='%23c9a227'/%3E%3Ctext x='12' y='16'"
              " font-size='8.5' font-weight='700' text-anchor='middle' fill='%23151b24'"
              " font-family='Arial,sans-serif'%3EMGM%3C/text%3E%3C/svg%3E")


def _tt_am(v, decimal=False):
    """Format a price as American. `decimal=True` converts first — fd_board is already American,
    bmbets stores decimal, and rendering one as the other prints a plausible wrong number."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if decimal:
        if v <= 1:
            return None
        v = round((v - 1) * 100) if v >= 2 else -round(100 / (v - 1))
    v = int(round(v))
    return ("+%d" % v) if v > 0 else str(v)


'''
anc = "def _tt_totals_card("
assert anc in s, "card anchor missing"
s = s.replace(anc, LOGO.lstrip("\n") + anc, 1)

# ── 1. FanDuel entries carry their posted price ─────────────────────────────────────────────
old = """        entries.append({"start": start, "p1": m.get("p1", "?"), "p2": m.get("p2", "?"),
                        "line": line, "side": pick["side"], "hit": hit, "real": True})"""
new = """        _od = m.get("over_odds") if pick["side"] == "over" else m.get("under_odds")
        entries.append({"start": start, "p1": m.get("p1", "?"), "p2": m.get("p2", "?"),
                        "line": line, "side": pick["side"], "hit": hit, "real": True,
                        "odds": _tt_am(_od), "book": "FanDuel"})"""
assert old in s, "fd entry anchor missing"
s = s.replace(old, new, 1)

# ── 2. re-add the bets pass (BetMGM-priced plays the FanDuel loop cannot see) ────────────────
old2 = """    for e in (tt_json or {}).get("elite_upcoming", []):
        if not e.get("side"):
            continue"""
new2 = """    # BETS PRICED AWAY FROM FANDUEL. The loop above walks fd_board, and elite_h2h is itself built
    # from fd_board, so a bet struck at a fresh BetMGM line renders nowhere — it sits in `bets`,
    # counted in the record, invisible. An EXTRA play gets noticed; a MISSING one does not.
    # `bets` is post-gate (tt_board routes refused plays to `skipped`), so this cannot loosen it.
    for b in (tt_json or {}).get("bets", []):
        _k = frozenset((_norm_tt(b.get("p1")), _norm_tt(b.get("p2"))))
        if _k in board_pairs or not b.get("play_to"):
            continue
        try:
            start = dt.datetime.fromtimestamp(int(b["ts"]), dt.timezone.utc)
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if start <= now:
            continue
        board_pairs.add(_k)
        _bk = b.get("book") or {}
        entries.append({"start": start, "p1": b.get("p1", "?"), "p2": b.get("p2", "?"),
                        "line": b["play_to"],
                        "side": "over" if str(b.get("side", "")).startswith("O") else "under",
                        "hit": b.get("raw"), "real": True,
                        "odds": _tt_am(_bk.get("od"), decimal=True), "book": "BetMGM"})

    for e in (tt_json or {}).get("elite_upcoming", []):
        if not e.get("side"):
            continue"""
assert old2 in s, "upcoming anchor missing"
s = s.replace(old2, new2, 1)

# a normaliser matching fd_tt.norm (NFKD, strip marks, lower, collapse) for the dedupe key
old3 = "    _last = lambda s: (s or \"\").split()[-1] if (s or \"\").split() else \"\""
new3 = ("    _last = lambda s: (s or \"\").split()[-1] if (s or \"\").split() else \"\"\n"
        "    # mirrors fd_tt.norm so the bets dedupe key matches the board keys; plain .lower()\n"
        "    # agrees only while every name is ASCII, and TT is full of Polish names.\n"
        "    def _norm_tt(x):\n"
        "        import unicodedata as _u\n"
        "        n = _u.normalize(\"NFKD\", str(x or \"\"))\n"
        "        n = \"\".join(c for c in n if not _u.combining(c))\n"
        "        return \" \".join(n.lower().split())")
assert old3 in s, "_last anchor missing"
s = s.replace(old3, new3, 1)

# ── 3. render the price and the right badge ─────────────────────────────────────────────────
old4 = """        if x["real"]:
            lncell, src = f'{x["line"]:g}', '<span class="fd">FanDuel · confirmed</span>'"""
new4 = """        if x["real"]:
            _bk = x.get("book") or "FanDuel"
            _mgm = _bk == "BetMGM"
            _cls = "bmgm" if _mgm else "fd"
            _o = x.get("odds")
            _price = ("" if not _o else
                      f'<span class="podds {_cls}">{_o}</span>'
                      f'<img class="bklogo" src="{TTMGM_LOGO if _mgm else "book-fd.png"}" '
                      f'alt="{"MGM" if _mgm else "FD"}">')
            lncell = f'{x["line"]:g}'
            src = f'<span class="{_cls}">{_bk} · confirmed</span>{_price}'"""
assert old4 in s, "render anchor missing"
s = s.replace(old4, new4, 1)

# ── 4. CSS (inside an f-string: every brace DOUBLED) ────────────────────────────────────────
oldc = "  .ttbnm {{ font-size:14px; color:#cdd5e0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}"
newc = ("  /* FULL NAMES (2026-07-31, user): ellipsis truncation made Polish pairs unreadable on a\n"
        "     phone, and a name you cannot read is a bet you cannot place. Wrap instead. */\n"
        "  .ttbnm {{ font-size:14px; color:#cdd5e0; white-space:normal; overflow-wrap:anywhere; line-height:1.32; }}\n"
        "  .ttbsb .bmgm {{ color:#c9a227; }}     /* BetMGM gold, so the book is never misread */\n"
        "  .podds.bmgm {{ color:#c9a227; }}")
assert oldc in s, "css anchor missing"
s = s.replace(oldc, newc, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.prettui2.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + python bake: bets pass restored, odds + FD logo, BetMGM gold, names wrap")
