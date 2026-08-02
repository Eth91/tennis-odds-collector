"""Insert the H-P1 form shift at the end of rates(), where per-player rates are finalised."""
import ast, io, shutil
P="pga_birdies.py"; s=io.open(P,encoding="utf-8").read()
if "H-P1 FORM SHIFT" in s:
    print("  = shift already inserted"); raise SystemExit(0)

old = """        out[pl] = row
    return out, {par: min(base[par] * ctx, 0.95) for par in frate}"""
new = '''        out[pl] = row

    # ── H-P1 FORM SHIFT (2026-07-31) ────────────────────────────────────────────────────────
    # A player's residual in one round carries to the next at r=+0.152 (42,557 player-rounds /
    # 114 events, round-level conditions removed, leave-one-event-out baselines, cross-event null
    # -0.005). The baseline above already excludes live_tid, so `actual - expected` here is a
    # clean residual rather than one measured against a number containing itself.
    #
    # The field's OWN rate this week carries the conditions (wind, pins, setup) — the same
    # de-conditioning the measurement used — so expected() is the player's multiplier applied to
    # what the field actually did, not to a historical average.
    #
    # Fully guarded: any failure leaves `out` untouched. A missing fetch must never move a price.
    if live_tid and FORM_R:
        try:
            live = live_rounds(live_tid, live_tname or "")
            usable = {p: (h, b) for p, (h, b) in live.items() if h >= FORM_MIN_HOLES}
            th = sum(h for h, _ in usable.values())
            tb = sum(b for _, b in usable.values())
            if th >= FORM_MIN_HOLES * 10 and tb > 0:
                field_now = tb / th                      # conditions, straight from the field
                field_hist = sum(frate.values()) / len(frate) if frate else field_now
                n_shift = 0
                for pl, (h, b) in usable.items():
                    row = out.get(pl)
                    if not row:
                        continue
                    mult = ((sum(row.values()) / len(row)) / field_hist) if field_hist > 0 else 1.0
                    expected = mult * field_now
                    resid = (b / h) - expected
                    shift = FORM_R * resid
                    if abs(shift) < 1e-6:
                        continue
                    out[pl] = {par: max(min(v + shift, 0.95), 0.01) for par, v in row.items()}
                    n_shift += 1
                print(f"  H-P1 form: {n_shift} players shifted "
                      f"(field {field_now:.4f}/hole over {th} holes, r={FORM_R})")
        except Exception as _fe:                                    # noqa: BLE001
            print(f"  H-P1 form: skipped ({str(_fe)[:60]})")

    return out, {par: min(base[par] * ctx, 0.95) for par in frate}'''
assert old in s, "tail anchor missing"
assert s.count(old)==1, "ambiguous tail anchor"
s=s.replace(old,new,1)
ast.parse(s)
shutil.copyfile(P,"/tmp/pga_birdies.preshift.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + form shift inserted at the end of rates()")
