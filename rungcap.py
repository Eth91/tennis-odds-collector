import json, sys; sys.path.insert(0,".")
import wnba_tonight as T
print("=== exercise the exact capture expression on tonight's flags ===")
for n, stat in (("Bridget Carleton","points"), ("Julie Allemand","assists"), ("Marina Mabrey","pts_ast")):
    try:
        lad = json.dumps({str(k): v for k, v in ((T.posted_props(n) or {}).get(stat) or {}).items()})
    except Exception as e:
        lad = "ERROR %s" % e
    print("   %-18s %-8s -> %s" % (n, stat, lad[:120]))
print("\n=== and prove a stored ladder is re-usable for the ladder-up test ===")
lad = json.loads(json.dumps({str(k): v for k, v in
                             ((T.posted_props("Bridget Carleton") or {}).get("points") or {}).items()}))
proj = 18.4
print("   proj %.1f -> rungs it clears, with price and breakeven:" % proj)
for k, v in sorted(lad.items(), key=lambda x: float(x[0])):
    ln = float(k); ov = v[0] if isinstance(v,(list,tuple)) else None
    if ov and ln < proj:
        print("     o%-6s @%-7s breakeven %.1f%%  headroom %.1f" % (ln, ov, 100/ov, proj-ln))
