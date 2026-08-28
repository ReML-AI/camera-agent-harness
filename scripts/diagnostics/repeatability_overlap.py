"""Within-condition repeatability: does the T/M contrast exceed run-to-run variability?

The reported T/M overlap is a single execution of each condition, so it cannot by itself
separate an effect of delivered visual context from ordinary generation variability. This
derives the baseline the manuscript reports.

    sbatch scripts/run_diagnostic.sbatch scripts/diagnostics/repeatability_overlap.py

Requires a second focal pass from scripts/run_repeatability.sbatch.

compute_symmetric_overlap is invoked ONE SESSION AT A TIME on purpose: passing all nine at
once pools moments and yields moment-weighted directional rates, not the unweighted session
mean the manuscript reports.

R_Q = mean(O(T1,T2), O(M1,M2))            within-condition
C_Q = mean over all four cross pairings   cross-condition
Reported per session, then mean and sample SD, plus whether Session 4's zero visual
uptake and Session 8's fabricated identifiers recur.
"""
import json, sys
from pathlib import Path
from statistics import mean, stdev
sys.path.insert(0, ".")
from scripts.metrics.definitions import compute_symmetric_overlap

S = [f"session_{i:03d}" for i in range(1, 10)]

def load(sid, repeat):
    name = "moments_multimodal_repeat.json" if repeat else "moments_multimodal.json"
    d = json.loads(Path(f"data/sessions/{sid}/processed/{name}").read_text())
    return {c: d[c]["moments"] for c in ("T", "M")}

runs = {sid: {1: load(sid, False), 2: load(sid, True)} for sid in S}

def ov(sid, a, ra, b, rb):
    r = compute_symmetric_overlap(a, b, [sid],
                                  {sid: runs[sid][ra][a]}, {sid: runs[sid][rb][b]},
                                  paper_mode=False)
    return r.value if r.value is not None else float("nan")

print(f"{'session':12s} {'O(T1,T2)':>9s} {'O(M1,M2)':>9s} {'R_Q':>7s} {'C_Q':>7s} {'R-C':>7s}")
RQ, CQ = [], []
for sid in S:
    tt = ov(sid, "T", 1, "T", 2)
    mm = ov(sid, "M", 1, "M", 2)
    rq = mean([tt, mm])
    cq = mean([ov(sid, "T", 1, "M", 1), ov(sid, "T", 1, "M", 2),
               ov(sid, "T", 2, "M", 1), ov(sid, "T", 2, "M", 2)])
    RQ.append(rq); CQ.append(cq)
    print(f"{sid:12s} {100*tt:9.1f} {100*mm:9.1f} {100*rq:7.1f} {100*cq:7.1f} {100*(rq-cq):7.1f}")

print(f"\nR_Q  mean {100*mean(RQ):.1f}  SD {100*stdev(RQ):.1f}")
print(f"C_Q  mean {100*mean(CQ):.1f}  SD {100*stdev(CQ):.1f}")
d = [a-b for a, b in zip(RQ, CQ)]
print(f"R-C  mean {100*mean(d):.2f}  SD {100*stdev(d):.2f}  "
      f"range {100*min(d):.2f} to {100*max(d):.2f}")

# Session is the unit: the four cross-pairings are not independent observations.
from math import sqrt
n = len(d)
md, sd = mean(d), stdev(d)
tstat = md / (sd / sqrt(n))
pos = sum(1 for x in d if x > 0)
print(f"paired t({n-1}) = {tstat:.2f}   positive in {pos}/{n} sessions")
half = 2.306 * sd / sqrt(n)          # t_.975,8
print(f"95% CI for mean difference: {100*(md-half):.2f} to {100*(md+half):.2f} pp")

print("\n=== do the unusual behaviours recur? ===")
for sid, label in (("session_004", "zero visual uptake"), ("session_008", "fabricated ids")):
    for r in (1, 2):
        ms = runs[sid][r]["M"]
        vis = sum(1 for m in ms
                  for e in (m.get("resolved_evidence") or [])
                  if e.get("modality") in ("visual_scene", "visual_attention"))
        ids = sum(len(m.get("evidence_ids") or []) for m in ms)
        res = sum(len(m.get("resolved_evidence") or []) for m in ms)
        print(f"  {sid} run{r} ({label}): M moments={len(ms)} visual_citations={vis} "
              f"cited_ids={ids} resolved={res} unresolved={ids-res}")
