#!/usr/bin/env python3
"""Executable readiness criteria for the nine-session run.

Every check reads a produced artifact and either passes or fails. Nothing here asks for a
judgement call, because "the pipeline looks healthy" is exactly the assumption that let a
no-op ranking, a 2.4x delivery overstatement and a wrong session duration reach a paper
claim. A criterion that cannot fail is not a criterion.

    python scripts/diagnostics/readiness_gate.py session_001 [session_002 ...]

Exit status is 0 only when every check passes for every session.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.utils.session_paths import (  # noqa: E402
    metrics_dir,
    prerequisites_dir,
    processed_dir,
    raw_dir,
)


class Gate:
    def __init__(self):
        self.rows = []

    def check(self, name, ok, detail=""):
        self.rows.append((name, bool(ok), detail))
        return bool(ok)

    def report(self, session):
        failed = [row for row in self.rows if not row[1]]
        print(f"\n=== {session}: {len(self.rows) - len(failed)}/{len(self.rows)} passed ===")
        for name, ok, detail in self.rows:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        return not failed


def gate_session(session):
    g = Gate()
    metrics = json.loads((metrics_dir(session) / "paper_metrics.json").read_text())
    windows = json.loads((processed_dir(session) / "multimodal_windows.json").read_text())
    runs = json.loads((processed_dir(session) / "moments_multimodal.json").read_text())

    # 1. Delivery is measured over what the model saw.
    delivery = windows.get("focal_delivery", {})
    delivered_ids = set(delivery.get("delivered_window_ids") or ())
    funnel = metrics["harness_delivery_failure_funnel"]
    inv = funnel.get("withholding_partition_invariant", {})
    g.check("funnel partition is exhaustive",
            inv.get("delivered_plus_reason_counts_equals_denominator") is True)
    g.check("funnel reasons are mutually exclusive",
            inv.get("reasons_are_mutually_exclusive") is True)

    # 2. Funnel stages must not increase along the path: a later stage cannot deliver more
    #    than an earlier one made available.
    ordered = ("eligible_union", "stage3_assigned", "selected_camera_signal",
               "strict_asd_gate_passed", "delivered")
    for signal, stages in funnel["signals"].items():
        values = [stages[s]["numerator"] for s in ordered if s in stages]
        g.check(f"{signal}: funnel is monotone non-increasing",
                all(a >= b for a, b in zip(values, values[1:])), str(values))

    # 3. Every citation resolves, and against delivered evidence only.
    prov = metrics["provenance_integrity"]
    counts = prov.get("counts", {})
    cited = counts.get("citation_count", 0)
    resolved = counts.get("delivered_resolved_citation_count", 0)
    undelivered_count = counts.get("undelivered_citation_count", 0)
    g.check("citations are audited against delivered evidence", cited > 0,
            f"{resolved}/{cited} resolved to delivered evidence")
    # Reported, never gated: the model fabricating ids is a measurement, not a run failure.
    g.check("undelivered citation rate is measurable", cited > 0,
            f"{undelivered_count}/{cited} cited but never delivered"
            + (f" ({undelivered_count / cited:.1%})" if cited else ""))
    g.check("resolved plus undelivered accounts for every citation",
            resolved + undelivered_count == cited,
            f"{resolved}+{undelivered_count} vs {cited}")
    # The audit's verdict matters, but not every violation code is a pipeline defect.
    # citation_temporal_rule_failed means the focal model cited evidence outside the
    # interval it itself reported for that moment -- a property of the model's output that
    # the harness correctly detects and the paper reports. Requiring zero would demand
    # perfect model behaviour and fail every session forever. Every other code is a real
    # breach: something was not delivered, did not resolve, or did not match.
    # Citing evidence that was never delivered is the model fabricating an id -- evidence
    # ids are sequential, so it can extrapolate plausible ones it never received. Detecting
    # that is precisely what this audit is for, so it is a REPORTED RATE, not a gate
    # failure. A missing stored resolution for an id that was never delivered is the same
    # event seen twice; one for a DELIVERED id would be a real pipeline defect.
    MODEL_BEHAVIOUR_CODES = {
        "citation_temporal_rule_failed",
        "citation_not_delivered_to_condition",
    }
    breaches = {}
    for condition, block in (prov.get("conditions") or {}).items():
        for moment in block.get("moment_results") or ():
            undelivered = set(moment.get("undelivered_evidence_ids") or ())
            for code in moment.get("violation_codes") or ():
                if code in MODEL_BEHAVIOUR_CODES:
                    continue
                if code == "citation_missing_stored_resolution":
                    unexplained = [
                        i for i in (moment.get("missing_stored_resolution_ids") or ())
                        if i not in undelivered
                    ]
                    if not unexplained:
                        continue
                breaches.setdefault(code, 0)
                breaches[code] += 1
    g.check("no provenance breaches beyond model citation timing",
            not breaches,
            ", ".join(f"{k}x{v}" for k, v in sorted(breaches.items())) or "none")

    # Reported, never gated: the rate is a result about the model, not a pass condition.
    # temporally_invalid now counts only citations whose timing could actually be evaluated;
    # undelivered ones sit in their own bucket. Subtracting undelivered here as well double
    # -corrected and produced a negative rate (-57/144 on session_008).
    mistimed = counts.get("temporally_invalid_citation_count", 0)
    not_evaluable = counts.get("citation_timing_not_evaluable_count", 0)
    delivered_cited = cited - not_evaluable
    g.check("citation timing rate is measurable", delivered_cited > 0,
            f"{mistimed}/{delivered_cited} delivered citations fall outside the moment's "
            f"own interval" + (f" ({mistimed / delivered_cited:.1%})" if delivered_cited else ""))

    # 4. The focal model was told the truth about the session it was analysing. The truth
    #    is the manifest's synchronized span, NOT the maximum over assembled windows:
    #    windows exist only where a flag landed, so comparing the prompt against that
    #    maximum compares a flagged-derived number with itself and both can be short
    #    together whenever the tail carries no flag.
    manifest = json.loads(
        (prerequisites_dir(session) / "session_manifest.json").read_text()
    )
    true_end = float(manifest["session_end_seconds"])
    g.check("assembled artifact records the manifest session span",
            abs(float(windows.get("session_end_seconds", -1)) - true_end) < 0.5,
            f"artifact {windows.get('session_end_seconds')} vs manifest {true_end}")
    for condition in ("T", "M"):
        # An absent span is a failure, not a skip. Guarded by `is not None`, this check
        # silently vanished from the report for every run: the focal artifact never
        # recorded the span at all, so the one criterion guarding against telling the
        # model the wrong session length never executed once.
        prompt_duration = runs[condition].get("session_duration_seconds")
        g.check(f"{condition}: prompt states the true session span",
                prompt_duration is not None
                and abs(float(prompt_duration) - true_end) < 0.5,
                f"prompt {prompt_duration} vs manifest {true_end}")

    # 5. Table 3 ordering must hold by construction: Union is a ceiling over Best Cam,
    #    and Selected is a subset of Union.
    for signal, row in metrics["table3"].items():
        if not isinstance(row, dict):
            continue
        vals = {k: (row.get(k) or {}).get("value") for k in ("best_cam", "union", "selected")}
        if all(isinstance(v, float) for v in vals.values()):
            g.check(f"{signal}: union >= best_cam", vals["union"] >= vals["best_cam"] - 1e-9,
                    f"{vals['union']:.4f} vs {vals['best_cam']:.4f}")
            g.check(f"{signal}: union >= selected", vals["union"] >= vals["selected"] - 1e-9,
                    f"{vals['union']:.4f} vs {vals['selected']:.4f}")

    # 6. Delivered windows must actually be the ones scored.
    g.check("delivered window set is non-empty", bool(delivered_ids), str(len(delivered_ids)))
    g.check("delivered windows are a subset of assembled",
            delivered_ids <= {w["window_id"] for w in windows["windows"]})

    # 7. The attention gate must actually gate, and must leave attention usable. The gate
    #    first shipped as a no-op: it reported 1,666 candidates with 0 in every outcome
    #    bucket, and the assembler filtered on a field the records did not carry. Both an
    #    impossible partition and a gate that admits everything are failures here.
    gaze_path = raw_dir(session) / "gaze_tracks.json"
    if gaze_path.exists():
        gate = json.loads(gaze_path.read_text()).get("exact_frame_gate", {})
        cand = gate.get("candidate_record_count", 0)
        parts = [gate.get(k, 0) for k in
                 ("delivered_record_count", "non_positive_record_count",
                  "missing_join_record_count")]
        g.check("attention gate outcomes partition the candidates",
                cand > 0 and sum(parts) == cand, f"{'+'.join(map(str, parts))} vs {cand}")
        g.check("attention gate delivers a usable population",
                parts[0] > 0, f"delivered {parts[0]}/{cand}")

    # 8. Attention that reached a window must be gate-positive, with no verdict-less record.
    attention_seen = 0
    ungated = 0
    for window in windows["windows"]:
        attention = (window.get("context") or {}).get("visual_attention") or {}
        for record in attention.get("records") or ():
            if isinstance(record, dict):
                attention_seen += 1
                if record.get("exact_frame_gate") != "exact_frame_asd_positive":
                    ungated += 1
    g.check("every delivered attention record carries a positive gate verdict",
            attention_seen > 0 and ungated == 0,
            f"{attention_seen} delivered, {ungated} ungated")

    # 9. The cohort coverage metrics must be computable from THIS session's windows.
    #    Stage 19 requires the canonical 30/15 population; the assembler emits a 30/30
    #    slide and keeps only flagged windows, so these three metrics would come back
    #    unavailable -- and only after all nine sessions had already run. Calling the real
    #    producer here front-loads that failure to the session that caused it, and cannot
    #    drift from the Stage-19 geometry the way a reimplementation would.
    from scripts.metrics.definitions import (  # noqa: E402
        compute_attention_context_coverage,
        compute_scene_context_coverage,
        compute_transcript_context_coverage,
    )

    ends = {session: max(w["end_seconds"] for w in windows["windows"])}
    by_session = {session: windows["windows"]}
    for name, producer in (
        ("transcript", compute_transcript_context_coverage),
        ("scene", compute_scene_context_coverage),
        ("attention", compute_attention_context_coverage),
    ):
        # The producer raises on a malformed window rather than reporting unavailable, so
        # a crash here is a gate failure, not a gate outage.
        try:
            result = producer([session], ends, by_session)
        except Exception as error:  # noqa: BLE001 - any failure means not computable
            g.check(f"cohort {name} coverage is computable", False,
                    f"{type(error).__name__}: {error}")
            continue
        reasons = {unit.unavailable_reason for unit in result.units
                   if getattr(unit, "unavailable_reason", None)}
        g.check(f"cohort {name} coverage is computable",
                result.status != "unavailable" and not reasons,
                "; ".join(sorted(reasons)) or result.status)

    # 10. No metric may silently report a fabricated value.
    unavailable = [k for k, v in metrics.items()
                   if isinstance(v, dict) and v.get("status") == "unavailable"]
    g.check("no metric is silently unavailable without a reason",
            all(metrics[k].get("unavailable_reason") for k in unavailable),
            ",".join(unavailable) or "none unavailable")

    return g.report(session)


def main():
    sessions = sys.argv[1:] or ["session_001"]
    results = [gate_session(s) for s in sessions]
    print(f"\nREADY: {all(results)}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
