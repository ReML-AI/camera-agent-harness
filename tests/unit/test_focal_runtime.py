import inspect
import json
from pathlib import Path
import pytest

from scripts.core.errors import ContractError
from scripts.focal.runtime import FocalRuntime


ROOT = Path(__file__).resolve().parents[2]
SHIPPED_CONFIG = ROOT / "configs" / "focal_runtime_qwen2_5_7b_ollama_q4km.json"


def runtime_values():
    return {
        "profile_id": "synthetic-profile", "model_id": "synthetic-model",
        "model_revision": "synthetic-revision", "model_checksum": "0" * 64,
        "tokenizer_revision": "synthetic-tokenizer", "backend_name": "synthetic-backend",
        "backend_version": "synthetic-version", "container_id": None, "cuda_gpu": None,
        "dtype_quantization": "synthetic-dtype", "context_length": 4096,
        "chat_template_id": "synthetic-chat-template", "json_parameters": {"synthetic": True},
        "maximum_output_tokens": 256, "stop_sequences": (), "seed": 1,
        "batching": "synthetic-serial", "request_order": ("T", "M"),
        "timeout_seconds": 5, "retry_policy": "synthetic-no-retry",
        "temperature": 0, "json_mode": True,
    }


def test_resolved_paper_runtime_gate_constructs_an_explicit_profile():
    runtime = FocalRuntime.checked(paper_mode=True, **runtime_values())
    assert runtime.backend_name == "synthetic-backend"


def test_runtime_interface_has_no_defaults_for_focal_identifiers():
    parameters = inspect.signature(FocalRuntime).parameters
    assert all(parameter.default is inspect.Parameter.empty for parameter in parameters.values())


def test_runtime_refuses_decoding_drift_even_in_synthetic_mode():
    values = runtime_values()
    values["temperature"] = 0.1
    with pytest.raises(ContractError, match="temperature 0"):
        FocalRuntime.checked(paper_mode=False, **values)


def test_explicit_synthetic_runtime_serializes_every_focal_field():
    empty_identifier = runtime_values()
    empty_identifier["container_id"] = ""
    with pytest.raises(ContractError, match="non-empty or explicit null"):
        FocalRuntime.checked(paper_mode=False, **empty_identifier)

    runtime = FocalRuntime.checked(paper_mode=False, **runtime_values())
    serialized = runtime.to_dict()
    assert serialized["model_revision"] == "synthetic-revision"
    assert serialized["backend_version"] == "synthetic-version"
    assert serialized["container_id"] is None
    assert serialized["cuda_gpu"] is None
    assert serialized["request_order"] == ["T", "M"]
    assert len(runtime.sha256) == 64


def test_shipped_focal_runtime_config_satisfies_contract():
    values = json.loads(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    values["stop_sequences"] = tuple(values["stop_sequences"])
    values["request_order"] = tuple(values["request_order"])

    runtime = FocalRuntime.checked(paper_mode=True, **values)

    assert runtime.request_order == ("T", "M")
    assert runtime.temperature == 0
    assert runtime.json_mode is True
    assert runtime.container_id is None
    assert runtime.model_checksum == (
        "2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730"
    )
