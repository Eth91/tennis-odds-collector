"""DvP silently returns 0 for every COMBO market. 17 of 52 selected bets get no matchup adjustment.

THE BUG. dvp() looks up f"{stat}|{pos}" in a table keyed pts|G, reb|F, ast|C, fg3m|G. PROP_STATS
maps the singles onto those keys (points->pts, rebounds->reb, assists->ast) so they work — but the
combos map to themselves (pts_ast->pts_ast, pra->pra), and no such key exists. The dict .get()
default then returns 0.0, indistinguishable from "this defence is exactly average".

So every pra / pts_ast / pts_reb / reb_ast market has been priced with NO opponent adjustment at
all, and nothing ever said so. Measured on the graded selected universe: 17 of 52 bets, and
tonight's Marina Mabrey pts_ast is one of them. matchup_note() is dead for the same markets for the
same reason — its `c == 0` guard makes it return None every time.

THE FIX IS ARITHMETIC, NOT A NEW MODEL. The coefficient is in STAT-UNITS PER MINUTE, so it is
additive across components by construction: a defence conceding +0.010 pts/min and +0.005 ast/min
to guards concedes +0.015 pts_ast/min. The component sets already exist in wnba_tonight as
_STAT_COMPONENTS; this mirrors them rather than inventing a second mapping, because two copies of
that mapping would drift the first time a market is added.

Fixed inside wnba_dvp.dvp() — the single implementation every consumer already calls — so pricing,
the matchup note and anything downstream all get it at once.

⚠️ THIS CHANGES PRICING FOR COMBOS, so it is measured on the post-selection universe before being
left live, exactly like every other change today. It is a defect fix rather than a new hypothesis
(a feature that was supposed to apply and silently did not), but "it's a bug fix" is not a licence
to skip the backtest — a fix that costs units is still a change that costs units.
"""
import ast
import io
import shutil

P = "wnba_dvp.py"
s = io.open(P, encoding="utf-8").read()

if "_COMBO_PARTS" in s:
    print("  = already applied")
    raise SystemExit(0)

OLD = '''def dvp(team, pos, stat):
    """Opponent-adjusted DvP coefficient (stat-units per minute; + = opponent allows more)."""
    return dvp_table().get(f"{stat}|{_PG.get(pos, pos)}", {}).get(team, 0.0)'''

NEW = '''# Combo markets decompose into the base stats the table is keyed on. Mirrors
# wnba_tonight._STAT_COMPONENTS deliberately — a second, independent mapping would drift the first
# time a market is added, which is the exact failure two copies of a gate already caused here.
_COMBO_PARTS = {"pra": ("pts", "reb", "ast"), "pts_reb": ("pts", "reb"),
                "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast")}


def dvp(team, pos, stat):
    """Opponent-adjusted DvP coefficient (stat-units per minute; + = opponent allows more).

    COMBOS SUM THEIR PARTS. The table is keyed on base stats (pts|G, reb|F, ...), so a lookup for
    "pts_ast" missed and fell through to the 0.0 default — silently pricing every combo market with
    no opponent adjustment while looking exactly like an average matchup. 17 of 52 graded selected
    bets were affected. The coefficient is per-minute stat units, so addition is the correct
    composition: +0.010 pts/min and +0.005 ast/min is +0.015 pts_ast/min.
    """
    if stat in _COMBO_PARTS:
        return sum(dvp(team, pos, p) for p in _COMBO_PARTS[stat])
    return dvp_table().get(f"{stat}|{_PG.get(pos, pos)}", {}).get(team, 0.0)'''
assert OLD in s, "dvp anchor"
s = s.replace(OLD, NEW, 1)

# matchup_note builds its percentile band from the raw table, so it is dead for combos too —
# it needs the summed distribution across teams, not a missing key.
OLD2 = '''def matchup_note(team, pos, stat):
    coefs = sorted(dvp_table().get(f"{stat}|{_PG.get(pos, pos)}", {}).values())'''
NEW2 = '''def _coef_spread(pos, stat):
    """Every team's coefficient for this (stat, pos) — summed across parts for a combo, so the
    soft/tough percentile band works for combos instead of returning an empty list."""
    g = _PG.get(pos, pos)
    if stat in _COMBO_PARTS:
        teams = set()
        for p in _COMBO_PARTS[stat]:
            teams |= set(dvp_table().get(f"{p}|{g}", {}))
        return {t: sum(dvp_table().get(f"{p}|{g}", {}).get(t, 0.0)
                       for p in _COMBO_PARTS[stat]) for t in teams}
    return dvp_table().get(f"{stat}|{g}", {})


def matchup_note(team, pos, stat):
    coefs = sorted(_coef_spread(pos, stat).values())'''
assert OLD2 in s, "matchup_note anchor"
s = s.replace(OLD2, NEW2, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/wnba_dvp.precombo.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + dvp() sums components for pra / pts_ast / pts_reb / reb_ast")
print("  + matchup_note percentile band works for combos too")
