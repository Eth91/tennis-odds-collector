"""72-hole matchbets where one player MISSED THE CUT never grade — they sit pending forever.

The matchup grader requires BOTH players to have 4 rounds before it will compare totals
(`if len(rs) < 4 or len(os_) < 4: return None`). That is the right guard while the tournament is
running — but it is also the state a missed cut leaves behind PERMANENTLY, so all three of this
week's 72-hole matchups (Clark vs Koivun, Si Woo Kim vs Gotterup, Cole vs Suber — each with one
player cut at 2 rounds) were unresolvable by construction. Same defect family as the withdrawn-
player birdie flags and the WNBA DNP projections: "not enough data yet" and "there will never be
more data" look identical, and the second must settle.

HOW FANDUEL ACTUALLY SETTLES IT: in a tournament matchbet, a player who completes more holes beats
one who is cut; totals only decide when both complete the same rounds. So the rule is
(rounds completed DESC, then total ASC) — never compare a 2-round score to a 4-round score.

THE GUARD THAT KEEPS IT SAFE: a cut can only be declared once the FIELD is demonstrably past the
cut boundary — someone must have a 3rd-round score (the same field-progress evidence void_dnps
uses). Mid-tournament, nobody has 3 rounds yet, so unequal counts still return None and live
matchups keep waiting exactly as before.
"""
import ast
import io
import shutil

P = "pga_grade_e3.py"
s = io.open(P, encoding="utf-8").read()

if "rounds completed DESC" in s:
    print("  = already applied")
    raise SystemExit(0)

OLD = '''        else:
            if len(rs) < 4 or len(os_) < 4:
                return None
            x, y = sum(rs[:4]), sum(os_[:4])
        if x == y:
            return ("P", 0.0)                          # two-way golf matchups push on a tie
        return ("W", odds - 1.0) if x < y else ("L", -1.0)'''

NEW = '''        else:
            if len(rs) < 4 or len(os_) < 4:
                # A MISSED CUT LOOKS LIKE "NOT FINISHED YET" — but only one of those resolves.
                # FanDuel settles a tournament matchbet by holes completed first: a player who was
                # cut loses to one who played the weekend, and totals only decide between equal
                # round counts (rounds completed DESC, then total ASC). Without this, any matchup
                # involving a cut player is unresolvable by construction and sits pending forever.
                # The cut may only be declared once the FIELD is provably past it — someone must
                # have a 3rd-round score — so live tournaments still wait exactly as before.
                _field_past_cut = any(len(v) >= 3 for v in scores.values())
                if not _field_past_cut or len(rs) == len(os_):
                    if _field_past_cut and len(rs) == len(os_) and len(rs) >= 2:
                        x, y = sum(rs), sum(os_)       # both cut: lower 36-hole total wins
                    else:
                        return None                    # still in progress, or nothing to compare
                elif len(rs) > len(os_):
                    return ("W", odds - 1.0)           # we played more golf than the opponent
                else:
                    return ("L", -1.0)
            else:
                x, y = sum(rs[:4]), sum(os_[:4])
        if x == y:
            return ("P", 0.0)                          # two-way golf matchups push on a tie
        return ("W", odds - 1.0) if x < y else ("L", -1.0)'''
assert OLD in s, "matchup grade anchor"
s = s.replace(OLD, NEW, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/pga_grade_e3.precut.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + matchbets settle on (rounds completed DESC, total ASC); cut-vs-made resolves,")
print("    both-cut compares 36-hole totals, live tournaments still wait")
