import wnba_wowy as W
ps = W.players()
want = ("allemand", "rice", "sykes", "morrow")
for n, d in sorted(ps.items()):
    if any(w in n.lower() for w in want):
        print("  %-26s team=%-5s pos=%-4s id=%s" % (n, d.get("team"), d.get("pos"), d.get("id")))
