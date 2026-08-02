"""Record what peer_gate KILLS, so the gate can eventually be judged. Capture only, no behaviour change.

THE PROBLEM. When peer_stat_gate fires, wnba_alert `continue`s: no ping, no ledger row, no trace.
The suppressed bet simply never existed. So there is no way to ask the only question that matters
about a filter — "were the bets it killed actually losers?" — without reconstructing it from game
logs, which is approximate and, more importantly, is not what the model saw.

That gap is not academic. Reconstructing it on the 52-bet graded universe suggested the bets
matching the gate's pattern went 9-4 for +33.6% ROI, i.e. the gate may be suppressing WINNERS. I
cannot assert that, precisely because the reconstruction is a guess at what the live gate did. This
makes the real answer recoverable.

A SEPARATE TABLE, NOT A COLUMN ON `predictions`. Suppressed bets must never enter the prediction
ledger: that ledger IS the pre-registered universe for the frozen v1.2 SPRT, and adding rows the
model refused to bet would silently redefine what is being tested. `gated` is written alongside,
graded independently, and can be compared to the kept bets without either contaminating the other.

WHAT IS STORED is everything needed to score the decision later: the bet, the price, and the gate's
own numbers (peer, rate_with, rate_without, breakeven, gap). Storing the DECISION rather than
re-deriving it is the entire point — a rate recomputed next month from a longer game log is not the
rate the gate acted on.

Fully guarded: a failure in the capture must never cost a suppression. The gate still fires and the
bet is still suppressed whether or not the row lands.
"""
import ast
import io
import shutil

# ── 1. the table + writer ────────────────────────────────────────────────────────────────────────
L = "wnba_ledger.py"
s = io.open(L, encoding="utf-8").read()
if "def log_gated" in s:
    print("  = log_gated already present")
else:
    FN = '''

GATED_SCHEMA = """
CREATE TABLE IF NOT EXISTS gated(
    pred_date TEXT, player TEXT, team TEXT, opp TEXT, stat TEXT, line REAL,
    odds REAL, side TEXT, gate TEXT,
    peer TEXT, rate_with REAL, rate_without REAL, breakeven REAL, gap REAL,
    n_with INTEGER, n_without INTEGER,
    proj_hit REAL, ev REAL, confidence TEXT, decided_at TEXT,
    result TEXT, actual REAL, graded INTEGER DEFAULT 0,
    PRIMARY KEY(pred_date, player, stat, line, gate));
"""


def log_gated(rows):
    """Persist bets a gate SUPPRESSED, with the gate's own numbers at decision time.

    Deliberately a separate table from `predictions`. That ledger is the pre-registered universe
    for the frozen v1.2 SPRT; adding rows the model refused to bet would silently redefine the
    test. These grade independently and are compared to it, never merged into it.

    The gate's numbers are STORED rather than recomputed later on purpose — a with-peer rate
    re-derived next month from a longer game log is not the rate the gate actually acted on.
    """
    if not rows:
        return 0
    con = _con()
    con.executescript(GATED_SCHEMA)
    cols = ("pred_date", "player", "team", "opp", "stat", "line", "odds", "side", "gate",
            "peer", "rate_with", "rate_without", "breakeven", "gap", "n_with", "n_without",
            "proj_hit", "ev", "confidence", "decided_at")
    q = ("INSERT OR REPLACE INTO gated(%s) VALUES (%s)"
         % (",".join(cols), ",".join("?" * len(cols))))
    n = 0
    for r in rows:
        try:
            con.execute(q, tuple(r.get(c) for c in cols))
            n += 1
        except Exception:                                        # noqa: BLE001
            continue
    con.commit()
    con.close()
    return n
'''
    anchor = "\n\ndef log_predictions("
    assert anchor in s, "log_predictions anchor"
    s = s.replace(anchor, FN + "\ndef log_predictions(", 1)
    ast.parse(s)
    shutil.copyfile(L, "/tmp/wnba_ledger.pregate.py")
    io.open(L, "w", encoding="utf-8").write(s)
    print("  + wnba_ledger.log_gated() + gated table")

# ── 2. capture at the suppression point ─────────────────────────────────────────────────────────
A = "wnba_alert.py"
s = io.open(A, encoding="utf-8").read()
if "_gated_rows" in s:
    print("  = alert already captures gate decisions")
    raise SystemExit(0)

OLD = """                    if _hit:
                        print(f"peer-gate SUPPRESSED {n} {e['stat']} o{e['line']:g}: "
                              f"{_hit['peer']} plays — {_hit['rate_with']*100:.0f}% with vs "
                              f"{_hit['rate_without']*100:.0f}% without "
                              f"(breakeven {_hit['breakeven']*100:.0f}%)", flush=True)
                        continue"""
NEW = """                    if _hit:
                        print(f"peer-gate SUPPRESSED {n} {e['stat']} o{e['line']:g}: "
                              f"{_hit['peer']} plays — {_hit['rate_with']*100:.0f}% with vs "
                              f"{_hit['rate_without']*100:.0f}% without "
                              f"(breakeven {_hit['breakeven']*100:.0f}%)", flush=True)
                        # CAPTURE WHAT THE GATE KILLED. Until now a suppressed bet left no trace
                        # at all — no ping, no row — so the only question that matters about a
                        # filter ("were the bets it killed actually losers?") could not be asked
                        # without reconstructing it, which is a guess at what the live gate did.
                        # Separate table: these must never enter `predictions`, which IS the
                        # pre-registered universe for the frozen v1.2 SPRT.
                        try:
                            _gated_rows.append({
                                "pred_date": slate_date, "player": n, "team": team,
                                "opp": matchups_by[slate_date].get(team, ""),
                                "stat": e["stat"], "line": e["line"], "odds": e["dec"],
                                "side": e["side"], "gate": "peer_stat",
                                "peer": _hit.get("peer"),
                                "rate_with": _hit.get("rate_with"),
                                "rate_without": _hit.get("rate_without"),
                                "breakeven": _hit.get("breakeven"),
                                "gap": (None if _hit.get("rate_without") is None
                                        or _hit.get("rate_with") is None
                                        else _hit["rate_without"] - _hit["rate_with"]),
                                "n_with": _hit.get("n_with"), "n_without": _hit.get("n_without"),
                                "proj_hit": round(e["hit"], 3), "ev": round(e["ev"], 3),
                                "confidence": conf, "decided_at": now_iso})
                        except Exception:                          # noqa: BLE001
                            pass                                   # never cost a suppression
                        continue"""
assert OLD in s, "suppression anchor"
s = s.replace(OLD, NEW, 1)

# initialise the accumulator beside the others
OLD2 = "    alerts, preds, proj_rows, cold_spots = [], [], [], []"
NEW2 = ("    alerts, preds, proj_rows, cold_spots = [], [], [], []\n"
        "    _gated_rows = []          # bets a gate SUPPRESSED — separate table, never `predictions`\n"
        "    now_iso = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()")
assert OLD2 in s, "accumulator anchor"
s = s.replace(OLD2, NEW2, 1)

# flush next to the prediction write
OLD3 = "    bet_preds = [p for p in preds if p.get(\"bettable\", 1)]"
NEW3 = ("    try:\n"
        "        import wnba_ledger as _WL\n"
        "        if _gated_rows:\n"
        "            _ng = _WL.log_gated(_gated_rows)\n"
        "            print(\"gate-log: %d suppressed bet(s) recorded\" % _ng, flush=True)\n"
        "    except Exception as _ge:                                   # noqa: BLE001\n"
        "        print(\"gate-log skipped: %s\" % str(_ge)[:80], flush=True)\n"
        "    bet_preds = [p for p in preds if p.get(\"bettable\", 1)]")
assert OLD3 in s, "flush anchor"
s = s.replace(OLD3, NEW3, 1)

ast.parse(s)
shutil.copyfile(A, "/tmp/wnba_alert.pregate.py")
io.open(A, "w", encoding="utf-8").write(s)
print("  + wnba_alert captures every peer-gate suppression into the `gated` table")
