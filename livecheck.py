import sys; sys.path.insert(0,".")
import wnba_tonight as T, wnba_slip as S
print("=== is each flagged rung still POSTED at FanDuel right now? ===")
for name, stat, line in (("Nyadiew Puoch","points",5.5), ("Bridget Carleton","points",13.5),
                         ("Laura Juskaite","points",9.5), ("Marina Mabrey","pts_ast",22.5),
                         ("Marina Mabrey","pts_ast",23.5), ("Julie Allemand","assists",5.5)):
    try:
        pp = T.posted_props(name) or {}
        rungs = sorted((pp.get(stat) or {}).keys())
        live = round(float(line),1) in (pp.get(stat) or {})
        print("  %-18s %-8s o%-6s LIVE=%-5s   posted rungs: %s" % (name, stat, line, live, rungs[:8]))
    except Exception as e:
        print("  %-18s ERROR %s" % (name, str(e)[:50]))
print()
print("=== tier rule: why is Carleton B and Puoch A? ===")
import inspect, re
src = inspect.getsource(S.tier_of)
print(src[:1100])
