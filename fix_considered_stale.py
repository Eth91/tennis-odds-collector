"""The also-considered panel can contradict the card. Exclude anything currently selected.

wnba_capped_legs.csv is append-only, so a row written BEFORE the correlation-cap fix ("DiLeo lost
the points pool to Carleton") survives after the fix reversed that decision. The board then shows
DiLeo as the carded bet AND as a rejected play in the same panel.

A rejected-plays panel that lists a play we are actually betting is worse than no panel: it makes
the board disagree with itself, which is the exact failure the coherence rule exists to prevent.

Fix: drop any also-considered row whose (player, stat) is in the CURRENT selection. The breadcrumb
stays on disk for the audit trail; it just stops being rendered once it is contradicted.
"""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "_sel_now" in s:
    print("  = already filtered"); raise SystemExit(0)

old = """        if not seen:
            return ""
        out = \"\""""
new = """        # A play we are CURRENTLY betting must never render as "not bet". wnba_capped_legs.csv is
        # append-only, so a decision reversed later in the day (the correlation-cap fix flipping
        # Carleton/DiLeo) leaves a stale row that would otherwise contradict the card.
        _sel_now = set()
        try:
            import wnba_slip as _S2
            _k, _ = _S2.current_selection([r for r in rows
                                           if (r.get("side") or "over") == "over"])
            _sel_now = {(r.get("player"), r.get("stat")) for r in _k}
        except Exception:                                            # noqa: BLE001
            pass
        for _k2 in [k for k in seen if (seen[k].get("player"), seen[k].get("stat")) in _sel_now]:
            seen.pop(_k2, None)

        if not seen:
            return ""
        out = \"\""""
assert old in s, "anchor missing"
assert s.count(old)==1, "ambiguous anchor"
s=s.replace(old,new,1)
ast.parse(s)
shutil.copyfile(P,"/tmp/dashboard.prestale.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + also-considered drops anything currently selected")
