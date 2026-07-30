"""round_scores() returned PARTIAL stroke totals as if they were completed rounds.

ESPN's linescores[i].value is the RUNNING total for that round, not the finished score, and the
old filter accepted anything > 0. Caught live during Rocket Classic round 1:
    Wyndham Clark  value 71.0  -> 18 holes, a real round
    Ben Griffin    value 11.0  -> THREE holes played (3+4+4)
    Max Greyserman value  3.0  -> ONE hole

Consequences, both bad:
  * in-play conditioning (simulate(progress=)) treats these as finished rounds, so a player three
    holes in looks like he shot 11 and gets a near-certain win probability. This is exactly the
    feature added yesterday, and it would have produced absurd live prices on day one.
  * grading a round-1 bet mid-round settles it against a partial score.

Each round entry carries its own nested per-hole linescores, so hole count is exact — require 18.
`status.thru` is not usable here: ESPN reports it as None for every competitor in this event.
"""
import ast, io
p = "pga_field.py"
s = io.open(p, encoding="utf-8").read()
old = '''        rs = []
        for ls in c.get("linescores") or []:
            v = ls.get("value")
            if isinstance(v, (int, float)) and v > 0:
                rs.append(v)
        out[nm] = rs'''
new = '''        rs = []
        for ls in c.get("linescores") or []:
            v = ls.get("value")
            # COMPLETED ROUNDS ONLY. `value` is a RUNNING stroke total, so mid-round it is a
            # partial sum (Ben Griffin read 11.0 three holes into Rocket Classic R1). Each round
            # nests its own per-hole scores, so hole count is exact; status.thru is None here.
            holes = ls.get("linescores") or []
            if isinstance(v, (int, float)) and v > 0 and len(holes) >= 18:
                rs.append(v)
        out[nm] = rs'''
assert old in s, "round_scores anchor missing"
if "COMPLETED ROUNDS ONLY" in s:
    print("  = already guarded")
else:
    s = s.replace(old, new, 1)
    # expose partials separately so in-play can use them deliberately rather than by accident
    s = s.replace('''def status(ev=None):''', '''def partial_rounds(ev=None):
    """{player: (holes_played, strokes_so_far)} for rounds IN PROGRESS.

    Split out from round_scores deliberately: a partial round is useful to simulate() via its
    `partial=` argument, but it must never be mistaken for a finished one.
    """
    out = {}
    for c in competitors(ev):
        nm = ((c.get("athlete") or {}).get("displayName") or "").strip()
        if not nm:
            continue
        for ls in c.get("linescores") or []:
            v = ls.get("value")
            holes = ls.get("linescores") or []
            if isinstance(v, (int, float)) and v > 0 and 0 < len(holes) < 18:
                out[nm] = (len(holes), v)
    return out


def status(ev=None):''', 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + round_scores() requires 18 holes; partial_rounds() added for in-play")
