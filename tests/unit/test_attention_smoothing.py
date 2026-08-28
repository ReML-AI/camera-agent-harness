import pytest

from scripts.core.errors import ContractError
from scripts.gaze.classify_gaze_targets import (
    ReferenceCalibratedAttention,
    ROLLING_MODE_WINDOW,
)
from tests.unit.test_attention_geometry import SyntheticProcedure, SyntheticSmoothing, calibration


class WrongWidthSmoothing(SyntheticSmoothing):
    window_size = 4


def test_rolling_mode_width_is_fixed_to_five_without_inventing_edge_or_tie_rules():
    assert ROLLING_MODE_WINDOW == 5
    with pytest.raises(ContractError, match="exactly 5"):
        ReferenceCalibratedAttention(
            calibration(), SyntheticProcedure(),
            smoothing_procedure=WrongWidthSmoothing(), paper_mode=False,
        )


def test_synthetic_mode_accepts_an_explicit_smoothing_procedure():
    adapter = ReferenceCalibratedAttention(
        calibration(), SyntheticProcedure(),
        smoothing_procedure=SyntheticSmoothing(), paper_mode=False,
    )
    assert adapter.classify([]) == []
