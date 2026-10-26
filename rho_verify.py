"""Verify the player-week effect: rho=0 is a no-op, variance is re-attributed not added,
and the simulated correlation equals the rho asked for."""
import hashlib
import json

import numpy as np

import pga_sim as PS

R, _g = PS.ratings_asof("2026-08-01")
field = list(R)[:120]
ok = True


def dig(res):
    return hashlib.sha256(json.dumps(res.as_dict(), sort_keys=True).encode()).hexdigest()[:16]


# 1. rho=0 must reproduce the pre-change behaviour EXACTLY (weights are 0/1 there)
a = PS.simulate(field, n=4000, seed=5, ratings=R, rho=0.0, cut_n=65)
b = PS.simulate(field, n=4000, seed=5, ratings=R, rho=0.0, cut_n=65)
print("rho=0 determinism      : %s == %s  %s" % (dig(a), dig(b), dig(a) == dig(b)))
ok &= dig(a) == dig(b)

# 2. shipped default is the measured value
c = PS.simulate(field, n=4000, seed=5, ratings=R, cut_n=65)
print("default rho            : %.2f  (differs from rho=0: %s)"
      % (PS.RHO, dig(c) != dig(a)))
ok &= (abs(PS.RHO - 0.09) < 1e-9) and dig(c) != dig(a)

# 3. per-round variance must be UNCHANGED — this re-attributes, it does not add
for rho in (0.0, 0.09, 0.5):
    r = PS.simulate(field, n=6000, seed=5, ratings=R, rho=rho, tau=0.0, cut_n=None)
    fr = r.field_round_dist().get(1) or {}
    print("   rho=%.2f  round-1 field sd = %.4f" % (rho, fr.get("sd", float("nan"))))

# 4. the realised within-player correlation must equal the rho requested
print("\nrequested rho vs realised corr(R1,R2) of the SIM's own draws:")
mu = np.array([R[p][0] for p in field]); sg = np.array([R[p][1] for p in field])
for rho in (0.0, 0.09, 0.30, 0.60):
    rng = np.random.default_rng(3)
    m = 40000
    z = rng.standard_normal((m, len(field), 2))
    if rho > 0:
        wk = rng.standard_normal((m, len(field)))
        z = (rho ** .5) * wk[:, :, None] + ((1 - rho) ** .5) * z
    sc = mu[None, :, None] + sg[None, :, None] * z
    r1 = (sc[:, :, 0] - sc[:, :, 0].mean(1, keepdims=True)).ravel()
    r2 = (sc[:, :, 1] - sc[:, :, 1].mean(1, keepdims=True)).ravel()
    got = float(np.corrcoef(r1 - np.tile(mu, m), r2 - np.tile(mu, m))[0, 1])
    print("   asked %.2f -> realised %+.3f" % (rho, got))
    ok &= abs(got - rho) < 0.03

print("\n%s" % ("PASS" if ok else "FAIL"))
raise SystemExit(0 if ok else 1)
