"""Rewrite the PGA board panel as a plain bet card: market heading, selection, line, price, book.

The old panel spoke model, not bets. A row read

    Ben Griffin        birdies · 1.38 · edge +11.4%

and the section headers were "E1 wave meter", "E3 ruler preview — pre-G2 (n=0), NOT flagged", with
side notes about "wind +1.5 km/h/rd" and "softest openers (Mon->close drift)". None of that tells
anyone what to put on. Edge, model probability, wave shift and G2 state are diagnostics — they
belong in the logs and the evidence report, not on the card you bet from.

New shape: group every play by MARKET, and give each row exactly four things —

    ROUND 1 BIRDIES
      Ben Griffin          under 5.5              -263    FanDuel

who, what line, what price, which book. Prices are shown American because that is how FanDuel
displays them; the decimal is kept in the title attribute for anyone reconciling against the raw
board JSON.

Internal stream names (E1 wave meter vs E3 ruler) are deliberately erased — a bettor does not care
which subsystem produced a play, only what the play is. Both now merge into the same market
sections.

ONE THING DELIBERATELY KEPT: the paper/live marker in the header. Every play on this board is
currently PAPER (the G2 gate has not passed), and a card that reads like a live recommendation when
it is not is worse than a cluttered one. It is stated once, plainly, instead of being repeated in
jargon on every row.
"""
import ast
import io
import re

p = "dashboard.py"
s = io.open(p, encoding="utf-8").read()

if "_pga_market_of" in s:
    print("  = PGA panel already reformatted")
    raise SystemExit(0)

start = s.index("def _pga_panel():")
end = s.index("\n\n\n", start)
old = s[start:end]

new = '''def _pga_market_of(row):
    """(market heading, selection, line) for one board row — no model vocabulary.

    Rows arrive from several internal streams with different shapes; a bettor should not have to
    know that. Everything is normalised to: which market, who, and at what line.
    """
    stream = str(row.get("stream") or "")
    market = str(row.get("market") or "")
    runner = str(row.get("runner") or "").strip()

    m = re.search(r"Round\\s+(\\d)", market)
    rnd = m.group(1) if m else None

    if "birdies" in stream:
        mm = re.match(r"^(.*?)\\s+(over|under)\\s+([\\d.]+)$", runner, re.I)
        who, line = (mm.group(1), f"{mm.group(2).lower()} {mm.group(3)}") if mm else (runner, "")
        return (f"ROUND {rnd} BIRDIES" if rnd else "BIRDIES"), who, line

    if "rscore" in stream:
        mm = re.match(r"^(.*?)\\s+(over|under)\\s+([\\d.]+)$", runner, re.I)
        who, line = (mm.group(1), f"{mm.group(2).lower()} {mm.group(3)}") if mm else (runner, "")
        return (f"ROUND {rnd} SCORE" if rnd else "ROUND SCORE"), who, line

    if "cut" in stream:
        mm = re.match(r"^(.*?)\\s+(make|miss)$", runner, re.I)
        who = mm.group(1) if mm else runner
        line = ("to make the cut" if (mm and mm.group(2).lower() == "make")
                else "to miss the cut" if mm else "")
        return "MAKE THE CUT", who, line

    if "match" in stream:
        opp = ""
        mm = re.search(r"vs\\.?\\s+(.+)$", market)
        if mm:
            other = mm.group(1).strip()
            opp = other if _norm_name(other) != _norm_name(runner) else ""
            if not opp:
                head = re.sub(r"^.*?Matchbet\\s*(?:\\([^)]*\\))?\\s*", "", market).split(" vs ")[0]
                opp = head.strip()
        span = "72 holes" if "72" in market else (f"round {rnd}" if rnd else "")
        return "MATCHUPS", runner, (f"{span} vs {opp}".strip() if opp else span)

    if "top" in stream:
        n = re.search(r"top(\\d+)", stream)
        tie = " (incl. ties)" if "TIE" in market.upper() else ""
        return (f"TOP {n.group(1)} FINISH{tie}".upper() if n else "TOP FINISH"), runner, ""

    if "outright" in stream:
        return "OUTRIGHT WINNER", runner, ""
    return "OTHER", runner, ""


def _norm_name(x):
    return re.sub(r"[^a-z]", "", str(x or "").lower())


def _pga_panel():
    """⛳ PGA board — a plain bet card.

    Market heading, then one line per play: who, what line, what price, which book. Model
    diagnostics (edge, projected probability, wave shift, gate state) are deliberately absent;
    they live in the logs and the evidence report. Render-only — fed by pga_board.json.
    """
    f = HERE / "pga_board.json"
    if not f.exists():
        return ""
    try:
        d = json.loads(f.read_text())
    except (ValueError, OSError):
        return ""
    rec = d.get("record") or {}
    w, l, u = rec.get("w", 0), rec.get("l", 0), rec.get("units", 0.0)
    ucls = "pos" if u >= 0 else "neg"
    armed = bool((d.get("e3") or {}).get("armed"))
    status = "LIVE" if armed else "PAPER — tracking only, not live bets"
    lg = (f'<img class="glogo" src="logos/pga.png" alt="" loading="lazy" '
          f'onerror="this.style.display=\\'none\\'">'
          f'<img class="glogo" src="logos/fd.png" alt="" loading="lazy" '
          f'onerror="this.style.display=\\'none\\'">')
    head = (f'<div class="sw-title">{lg}⛳ PGA '
            f'<span>· {html.escape(d.get("event") or "")} · {status} · '
            f'{w}-{l} · <b class="{ucls}">{u:+.2f}u</b></span></div>')

    plays = []
    for o in (d.get("open") or []):          # wave-meter plays: same markets, one list
        plays.append({"stream": "E3-match", "runner": o.get("runner") or "",
                      "market": f"Matchbet {o.get('runner')} vs {o.get('opp')}",
                      "odds": o.get("odds")})
    plays += list((d.get("e3") or {}).get("rows") or [])

    groups = {}
    for r in plays:
        if not r.get("odds"):
            continue
        mkt, who, line = _pga_market_of(r)
        groups.setdefault(mkt, []).append((who, line, float(r["odds"])))

    body = ""
    ORDER = ["MATCHUPS", "MAKE THE CUT", "TOP 5 FINISH", "TOP 10 FINISH", "TOP 20 FINISH",
             "OUTRIGHT WINNER"]

    def _rank(k):
        for i, o in enumerate(ORDER):
            if k.startswith(o):
                return (i, k)
        return (len(ORDER), k)

    for mkt in sorted(groups, key=_rank):
        body += (f'<div class="pgamkt">{html.escape(mkt)}</div>')
        for who, line, od in sorted(groups[mkt], key=lambda x: x[2]):
            det = f'<span class="pgaline">{html.escape(line)}</span>' if line else ""
            body += (f'<div class="swrow"><div class="swhd">'
                     f'<b>{html.escape(who)}</b>{det}'
                     f'<span class="swusg" title="{od:.2f} decimal">'
                     f'{html.escape(_am(od))} · FanDuel</span></div></div>')
    if not groups:
        body = '<div class="swo">No plays on the board right now.</div>'
    return f'<div class="starwatch">{head}{body}</div>'
'''

s = s[:start] + new + s[end:]

# minimal CSS for the market heading + the line detail, next to the existing .swusg rule
css_anchor = "  .swusg {"
css_new = ('''  .pgamkt {{ margin:10px 0 4px; font-size:11px; letter-spacing:.08em; font-weight:700;
             color:#8b94a3; text-transform:uppercase; }}
  .pgaline {{ margin-left:8px; color:#c8cfda; font-size:12.5px; }}
'''.replace("{{", "{").replace("}}", "}") + css_anchor)
assert css_anchor in s, "css anchor missing"
s = s.replace(css_anchor, css_new, 1)

if "\nimport re\n" not in s and not re.search(r"^import re$", s, re.M):
    s = s.replace("import json\n", "import json\nimport re\n", 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + PGA panel rewritten: market headings, selection, line, American price, FanDuel")
print("  + model jargon removed (edge, wave shift, G2 state, opener drift)")
