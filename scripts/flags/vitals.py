"""Deterministic configured vital-threshold flag records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from scripts.core.errors import ContractError

from .models import FlagArtifact, FlagRecord, FlagSource


@dataclass(frozen=True)
class VitalThresholds:
    low: float
    high: float
    critical_low: float
    critical_high: float

    def __post_init__(self) -> None:
        if not self.critical_low <= self.low <= self.high <= self.critical_high:
            raise ContractError(
                "vital thresholds must satisfy critical_low <= low <= high <= critical_high"
            )


class VitalThresholdFlagger:
    def __init__(
        self,
        thresholds: Mapping[str, VitalThresholds],
        *,
        policy_id: str,
    ) -> None:
        if not thresholds or not policy_id:
            raise ContractError("explicit vital thresholds and policy_id are required")
        self.thresholds = dict(thresholds)
        self.policy_id = policy_id

    @staticmethod
    def _severity(value: float, threshold: VitalThresholds) -> str | None:
        if value < threshold.critical_low or value > threshold.critical_high:
            return "critical"
        if value < threshold.low or value > threshold.high:
            return "warning"
        return None

    def run(self, session_id: str, records: Sequence[Mapping]) -> FlagArtifact:
        flags: list[FlagRecord] = []
        for record in records:
            start = record["start_seconds"]
            end = record["end_seconds"]
            raw_text = record.get("raw_ocr_text", {})
            values = record.get("values", {})
            for vital_name, threshold in self.thresholds.items():
                value = values.get(vital_name)
                if value is None:
                    continue
                severity = self._severity(float(value), threshold)
                if severity is None:
                    continue
                evidence_id = record["evidence_id"]
                flags.append(
                    FlagRecord(
                        flag_id=f"vital-{evidence_id}-{vital_name}",
                        source=FlagSource.VITALS_THRESHOLD,
                        start_seconds=start,
                        end_seconds=end,
                        evidence_ids=(evidence_id,),
                        policy_id=self.policy_id,
                        payload={
                            "vital": vital_name,
                            "value": value,
                            "severity": severity,
                            "raw_ocr_text": raw_text.get(vital_name),
                            "thresholds": {
                                "low": threshold.low,
                                "high": threshold.high,
                                "critical_low": threshold.critical_low,
                                "critical_high": threshold.critical_high,
                            },
                            "source_frame": record.get("source_frame"),
                        },
                    )
                )
        return FlagArtifact.success(
            session_id=session_id,
            source=FlagSource.VITALS_THRESHOLD,
            flags=flags,
            provenance={"policy_id": self.policy_id},
        )
