"""A traded-in player's WOWY split is measured against games she played AGAINST that team.

`wowy_multi` splits a beneficiary's games on whether the out-player appears in the same `game_id`.
A game_id identifies a GAME, not a SIDE — so two players who faced each other share it. For a player
traded in mid-season that is the only way she ever shares a game_id with her new teammates, and the
result is a split that is exactly backwards:

    Maria Conde     vs Morrow    n_with=1   n_without=27
    Laura Juskaite  vs Morrow    n_with=1   n_without=27
    Julie Allemand  vs Morrow    n_with=1   n_without=21

The single "with" game is 2026-06-19 — the night Morrow's old team PLAYED Toronto. She has never
taken the floor as a Toronto teammate. So "Conde without Morrow" is not a lineup state at all; it is
"every game Conde has ever played", compared against one game where Morrow was the opponent.

AND THE FALLBACK ACTIVELY PREFERS IT. When a multi-out combo is too thin, the alert path falls back
to `max(cands, key=n_without)` — the split with the most games. A traded player's bogus split has
the MOST games by construction, because nearly every game qualifies as "without". So the corrupt
split systematically beats the real teammate's split. That is how tonight's Conde flag ended up
carrying `d_min = -1.3`, which is Morrow's number, on a premise that never existed.

SCOPE, MEASURED: 5 of 170 flags with an out-basis are affected, ALL of them dated 2026-08-02, all
via Aneesah Morrow, and NONE are graded. The settled record is untouched — this fix cannot move a
single historical number. It changes tonight's board, which is the point.

THE TEST IS `matchup` EQUALITY. In a shared game, teammates both record the same opponent;
opponents record each other's team. Verified as a perfect discriminator on real data:

    Allemand vs Conde   (real teammates)   22 shared, 22 same-matchup,  0 opposite
    Allemand vs Mabrey  (real teammates)   21 shared, 21 same-matchup,  0 opposite
    Allemand vs Morrow  (traded in)         1 shared,  0 same-matchup,  1 opposite

It needs no roster history and no trade feed, and it handles both directions for free: games before
a trade-in and after a trade-out both stop counting as shared lineup states, because they were not.

⚠️ FALLS BACK, NEVER DROPS. If either side is missing `matchup` the old game_id test is used for
that game. A missing discriminator must not silently reclassify a real teammate as an opponent —
that would inflate `n_without` for legitimate pairs and quietly corrupt the splits that DO work.
"""
import ast
import io
import shutil

P = "wnba_wowy.py"
s = io.open(P, encoding="utf-8").read()

if "same-side" in s:
    print("  = already applied")
    raise SystemExit(0)

OLD = '''    present = set()
    for tl in teammate_logs:
        present |= {g["game_id"] for g in tl}'''

NEW = '''    # SAME-SIDE ONLY. A game_id identifies a GAME, not a SIDE, so two players who faced each other
    # share one. For a player traded in mid-season that is the ONLY way she ever shares a game_id
    # with her new teammates, which made her "with" set a single game played AGAINST them and her
    # "without" set the beneficiary's entire season. Teammates record the same opponent in a shared
    # game; opponents record each other's team — verified a perfect discriminator (22/22 and 21/21
    # for real TOR pairs, 0/1 for Morrow, who has never played a game FOR Toronto).
    own = {g["game_id"]: g.get("matchup") for g in player_log}
    present = set()
    for tl in teammate_logs:
        for g in tl:
            gid = g["game_id"]
            if gid not in own:
                continue
            mine, theirs = own[gid], g.get("matchup")
            # Missing discriminator -> keep the old behaviour for that game. Treating an unknown
            # as "opponent" would reclassify real teammates and corrupt the splits that work.
            if mine is None or theirs is None or mine == theirs:
                present.add(gid)'''
assert OLD in s, "present-set anchor"
s = s.replace(OLD, NEW, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/wnba_wowy.presameside.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + wowy_multi counts a teammate's game only when they were on the SAME SIDE")
