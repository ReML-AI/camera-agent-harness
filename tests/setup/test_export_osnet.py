from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from scripts.setup import export_osnet


def test_cli_requires_operator_supplied_checkpoint():
    with pytest.raises(SystemExit) as exc:
        export_osnet.main([])
    assert exc.value.code == 2


def test_missing_checkpoint_fails_before_optional_ml_imports(tmp_path, capsys):
    result = export_osnet.main(
        ["--checkpoint", str(tmp_path / "absent.pth"), "--output", str(tmp_path / "out.onnx")]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert "operator-supplied checkpoint is not a file" in captured.err
    assert "will not search for or download one" in captured.err
    assert not (tmp_path / "out.onnx").exists()


def test_state_dict_unwraps_common_container_and_prefixes():
    marker = object()
    assert export_osnet._unwrap_state_dict(
        {"state_dict": {"module.model.conv.weight": marker}}
    ) == {"conv.weight": marker}


class _Metadata:
    def __init__(self, name, shape):
        self.name = name
        self.shape = list(shape)
        self.type = "tensor(float)"


class _Session:
    def __init__(self, output_shape=export_osnet.OUTPUT_SHAPE):
        self.output_shape = output_shape

    def get_inputs(self):
        return [_Metadata(export_osnet.INPUT_NAME, export_osnet.INPUT_SHAPE)]

    def get_outputs(self):
        return [_Metadata(export_osnet.OUTPUT_NAME, self.output_shape)]

    def run(self, output_names, inputs):
        assert output_names == [export_osnet.OUTPUT_NAME]
        assert inputs[export_osnet.INPUT_NAME].dtype == np.float32
        return [np.zeros(self.output_shape, dtype=np.float32)]


def _fake_runtime(session):
    return SimpleNamespace(
        SessionOptions=lambda: SimpleNamespace(),
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="sequential"),
        InferenceSession=lambda *_args, **_kwargs: session,
    )


def test_runtime_validation_executes_exact_fixed_shape_contract(tmp_path):
    export_osnet.validate_onnx_runtime(_fake_runtime(_Session()), tmp_path / "graph.onnx")


def test_runtime_validation_rejects_wrong_output_shape(tmp_path):
    with pytest.raises(export_osnet.ExportError, match="unexpected ONNX output contract"):
        export_osnet.validate_onnx_runtime(
            _fake_runtime(_Session(output_shape=(1, 256))), tmp_path / "graph.onnx"
        )


def test_success_record_keeps_unmeasured_provenance_explicit(capsys):
    export_osnet._print_record(
        {
            "checkpoint_path": "/operator/checkpoint.pth",
            "checkpoint_sha256": "a" * 64,
            "output_path": "/project/models/osnet_x0_25_msmt17.onnx",
            "onnx_sha256": "b" * 64,
            "torch_version": "test",
            "torchreid_version": "test",
            "onnxruntime_version": "test",
        }
    )
    output = capsys.readouterr().out
    assert "checkpoint_source_revision=capture_at_run" in output
    assert "checkpoint_license=capture_at_run" in output
    assert f"onnx_sha256={'b' * 64}" in output
    assert "OPERATOR ACTIONS:" in output

