"""PING<->BOARD COHERENCE: the ⚡1G speed-pilot tier pings the phone but never reaches the
dashboard.

2026-07-28: "⚡1G S.Barker OUT -> B.Carleton pts o14.5" pinged at 22:32 and appears on
NEITHER the local nor the published board. The n1 branch appends to `alerts` (which drives
the push) and then `continue`s -- it never appends to cold_spots/_band_seen/_tmrw_seen, and
those are the only three collections folded into `watch`. So the one tier that pings without
rendering is exactly the one the standing rule forbids: if it pings, it is on the board.

Fix: collect n1 spots and fold them in like every other tier, with their own row kind so the
board can say what they are (1-game sample, stale line, not in the record).
"""
import ast
import io
import sys

# ---------------- wnba_alert.py ----------------
p = "wnba_alert.py"
s = io.open(p, encoding="utf-8").read()


def rep(old, new, tag, f=None):
    global s
    if old not in s:
        sys.exit("ANCHOR MISSING: " + tag)
    if s.count(old) != 1:
        sys.exit("ANCHOR AMBIGUOUS (%d): %s" % (s.count(old), tag))
    s = s.replace(old, new)


rep("    alerts, preds, proj_rows, cold_spots = [], [], [], []",
    "    alerts, preds, proj_rows, cold_spots = [], [], [], []\n"
    "    n1_spots = []                                    # ⚡1G speed pilots -> board (they PING)",
    "init")

rep('''                    for e in e1:
                        alerts.append((e["ev"], f"n1|{slate_date}|{n}|{e['stat']}|{e['line']:g}",''',
    '''                    for e in e1:
                        # COHERENCE (2026-07-28): this tier PINGS, so it must render. It used
                        # to exist only in `alerts` and vanished from the board entirely.
                        n1_spots.append({"player": n, "team": team, "star": out_full,
                                         "status": "OUT", "sit": 1.0, "lead": None,
                                         "conf": T.starter_label(n, team, starters, proj),
                                         "proj_min": round(proj, 1), "date": slate_date,
                                         "n1": True, **e})
                        alerts.append((e["ev"], f"n1|{slate_date}|{n}|{e['stat']}|{e['line']:g}",''',
    "collect")

rep("    watch += cold_spots                                  # ⚡COLD spots -> dashboard too",
    "    watch += n1_spots                                    # ⚡1G pilots -> dashboard (they ping)\n"
    "    watch += cold_spots                                  # ⚡COLD spots -> dashboard too",
    "watch")

rep('    _fold(cold_spots, "cold")',
    '    _fold(n1_spots, "n1", band_gate=False)               # pilots are out-of-band by nature\n'
    '    _fold(cold_spots, "cold")',
    "fold")

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("wnba_alert.py: n1 pilots now reach the board")

# ---------------- dashboard.py ----------------
p2 = "dashboard.py"
s2 = io.open(p2, encoding="utf-8").read()
OLD = 'KIND_ORD = {"q": 0, "contingent": 1, "cold": 2, "band": 3}'
if OLD not in s2:
    sys.exit("DASH ANCHOR MISSING: KIND_ORD")
s2 = s2.replace(OLD, 'KIND_ORD = {"q": 0, "contingent": 1, "n1": 2, "cold": 3, "band": 4}')

OLD2 = '''            elif kind == "cold":'''
if OLD2 not in s2:
    sys.exit("DASH ANCHOR MISSING: cold branch")
s2 = s2.replace(OLD2, '''            elif kind == "n1":
                cond = (f'<b>{html.escape("+".join(stars))}</b> out · 1-game sample '
                        f'<span class="wlin">· stale line · speed pilot, not in record</span>')
            elif kind == "cold":''', 1)

OLD3 = '            shadow = " wlshadow" if kind in ("cold", "band") else ""'
if OLD3 not in s2:
    sys.exit("DASH ANCHOR MISSING: shadow")
s2 = s2.replace(OLD3, '            shadow = " wlshadow" if kind in ("cold", "band", "n1") else ""')

ast.parse(s2)
io.open(p2, "w", encoding="utf-8").write(s2)
print("dashboard.py: n1 row kind rendered")
