#!/usr/bin/env python3
"""Export an operator-supplied Torchreid OSNet checkpoint to fixed-shape ONNX.

This command deliberately has no download path.  The checkpoint is a governed
input whose origin, revision, licence, and digest must be recorded by the
operator who supplies it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "models" / "osnet_x0_25_msmt17.onnx"
INPUT_NAME = "input"
OUTPUT_NAME = "embedding"
INPUT_SHAPE = (1, 3, 256, 128)
OUTPUT_SHAPE = (1, 512)


class ExportError(RuntimeError):
    """An actionable failure while loading, exporting, or validating OSNet."""


def sha256_file(path: Path) -> str:
    """Return the measured SHA-256 of *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _distribution_version(name: str, module: Any) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return str(getattr(module, "__version__", "capture_at_run"))


def _require_dependencies() -> tuple[Any, Any, Any]:
    missing: list[str] = []
    modules: dict[str, Any] = {}
    for name in ("torch", "torchreid", "onnx", "onnxruntime"):
        try:
            modules[name] = __import__(name)
        except (ImportError, ModuleNotFoundError) as exc:
            missing.append(f"{name} ({exc})")
    if missing:
        raise ExportError(
            "missing export dependencies: "
            + ", ".join(missing)
            + ". Install them in the explicit setup environment; this script will not download them."
        )
    return modules["torch"], modules["torchreid"], modules["onnxruntime"]


def _unwrap_state_dict(checkpoint: Any) -> dict[str, Any]:
    """Extract and normalize a tensor state dict without accepting arbitrary objects."""
    state: Any = checkpoint
    if isinstance(checkpoint, Mapping):
        for key in ("state_dict", "model_state_dict"):
            candidate = checkpoint.get(key)
            if isinstance(candidate, Mapping):
                state = candidate
                break
    if not isinstance(state, Mapping) or not state:
        raise ExportError(
            "checkpoint must be a non-empty state dict, or contain 'state_dict' or "
            "'model_state_dict'"
        )

    normalized: dict[str, Any] = {}
    for raw_key, value in state.items():
        if not isinstance(raw_key, str):
            raise ExportError("checkpoint state-dict keys must be strings")
        key = raw_key
        while key.startswith("module.") or key.startswith("model."):
            key = key.split(".", 1)[1]
        if key in normalized:
            raise ExportError(f"checkpoint contains a duplicate normalized key: {key}")
        normalized[key] = value
    return normalized


def _load_checkpoint(torch: Any, checkpoint_path: Path) -> dict[str, Any]:
    load_kwargs: dict[str, Any] = {"map_location": "cpu"}
    if "weights_only" not in inspect.signature(torch.load).parameters:
        raise ExportError(
            "this PyTorch version cannot load the checkpoint in weights-only mode; "
            "upgrade PyTorch rather than unpickling an untrusted checkpoint"
        )
    load_kwargs["weights_only"] = True
    try:
        checkpoint = torch.load(str(checkpoint_path), **load_kwargs)
    except Exception as exc:
        raise ExportError(f"could not load checkpoint in weights-only mode: {exc}") from exc
    return _unwrap_state_dict(checkpoint)


def _infer_num_classes(state_dict: Mapping[str, Any]) -> int:
    classifier_weight = state_dict.get("classifier.weight")
    shape = getattr(classifier_weight, "shape", ())
    if len(shape) == 2 and int(shape[0]) > 0:
        return int(shape[0])
    # The classifier head is not used in eval-mode feature extraction.
    return 1


def _build_model(torchreid: Any, state_dict: Mapping[str, Any]) -> Any:
    try:
        model = torchreid.models.build_model(
            name="osnet_x0_25",
            num_classes=_infer_num_classes(state_dict),
            loss="softmax",
            pretrained=False,
        )
    except Exception as exc:
        raise ExportError(f"could not construct Torchreid osnet_x0_25: {exc}") from exc

    expected = model.state_dict()
    compatible: dict[str, Any] = {}
    incompatible: list[str] = []
    unexpected: list[str] = []
    for key, value in state_dict.items():
        if key not in expected:
            unexpected.append(key)
            continue
        if tuple(getattr(value, "shape", ())) != tuple(expected[key].shape):
            if not key.startswith("classifier."):
                incompatible.append(key)
            continue
        compatible[key] = value

    missing_backbone = sorted(
        key for key in expected if key not in compatible and not key.startswith("classifier.")
    )
    unexpected_backbone = sorted(key for key in unexpected if not key.startswith("classifier."))
    if missing_backbone or incompatible or unexpected_backbone:
        details = []
        if missing_backbone:
            details.append(f"missing backbone keys: {missing_backbone[:8]}")
        if incompatible:
            details.append(f"shape-mismatched backbone keys: {sorted(incompatible)[:8]}")
        if unexpected_backbone:
            details.append(f"unexpected backbone keys: {unexpected_backbone[:8]}")
        raise ExportError(
            "checkpoint is not a complete Torchreid osnet_x0_25 state dict ("
            + "; ".join(details)
            + ")"
        )

    model.load_state_dict(compatible, strict=False)
    model.cpu()
    model.eval()
    return model


def _shape_tuple(metadata: Any) -> tuple[Any, ...]:
    return tuple(metadata.shape)


def validate_onnx_runtime(onnxruntime: Any, graph_path: Path) -> None:
    """Load and execute the graph, enforcing its public tensor contract."""
    try:
        import numpy as np

        options = onnxruntime.SessionOptions()
        options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        session = onnxruntime.InferenceSession(
            str(graph_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
    except Exception as exc:
        raise ExportError(f"ONNX Runtime could not load the exported graph: {exc}") from exc

    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if len(inputs) != 1 or inputs[0].name != INPUT_NAME:
        raise ExportError("exported graph must expose exactly one input named 'input'")
    if inputs[0].type != "tensor(float)" or _shape_tuple(inputs[0]) != INPUT_SHAPE:
        raise ExportError(
            f"unexpected ONNX input contract: {inputs[0].type} {_shape_tuple(inputs[0])}; "
            f"expected tensor(float) {INPUT_SHAPE}"
        )
    if len(outputs) != 1 or outputs[0].name != OUTPUT_NAME:
        raise ExportError("exported graph must expose exactly one output named 'embedding'")
    if outputs[0].type != "tensor(float)" or _shape_tuple(outputs[0]) != OUTPUT_SHAPE:
        raise ExportError(
            f"unexpected ONNX output contract: {outputs[0].type} {_shape_tuple(outputs[0])}; "
            f"expected tensor(float) {OUTPUT_SHAPE}"
        )

    sample = np.zeros(INPUT_SHAPE, dtype=np.float32)
    try:
        result = session.run([OUTPUT_NAME], {INPUT_NAME: sample})
    except Exception as exc:
        raise ExportError(f"ONNX Runtime inference failed: {exc}") from exc
    if len(result) != 1 or result[0].shape != OUTPUT_SHAPE or result[0].dtype != np.float32:
        observed = "no output" if not result else f"{result[0].dtype} {result[0].shape}"
        raise ExportError(
            f"unexpected ONNX Runtime output: {observed}; expected float32 {OUTPUT_SHAPE}"
        )


def _configure_determinism(torch: Any) -> None:
    torch.manual_seed(0)
    torch.set_num_threads(1)
    if hasattr(torch, "set_num_interop_threads"):
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            # It can only be set once per process; a prior value does not affect this CPU export.
            pass
    torch.use_deterministic_algorithms(True)


def export_checkpoint(checkpoint_path: Path, output_path: Path) -> dict[str, str]:
    checkpoint_path = checkpoint_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if not checkpoint_path.is_file():
        raise ExportError(f"operator-supplied checkpoint is not a file: {checkpoint_path}")
    if checkpoint_path == output_path:
        raise ExportError("checkpoint and ONNX output paths must be different")

    torch, torchreid, onnxruntime = _require_dependencies()
    _configure_determinism(torch)
    state_dict = _load_checkpoint(torch, checkpoint_path)
    model = _build_model(torchreid, state_dict)
    sample = torch.zeros(INPUT_SHAPE, dtype=torch.float32, device="cpu")
    with torch.no_grad():
        eager_output = model(sample)
    if tuple(eager_output.shape) != OUTPUT_SHAPE or eager_output.dtype != torch.float32:
        raise ExportError(
            f"Torchreid model returned {eager_output.dtype} {tuple(eager_output.shape)}; "
            f"expected float32 {OUTPUT_SHAPE}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        export_kwargs: dict[str, Any] = {
            "export_params": True,
            "opset_version": 17,
            "do_constant_folding": True,
            "input_names": [INPUT_NAME],
            "output_names": [OUTPUT_NAME],
            "dynamic_axes": None,
        }
        if "dynamo" in inspect.signature(torch.onnx.export).parameters:
            export_kwargs["dynamo"] = False
        with torch.no_grad():
            torch.onnx.export(model, sample, str(temporary_path), **export_kwargs)
        validate_onnx_runtime(onnxruntime, temporary_path)
        os.replace(temporary_path, output_path)
        temporary_path = None
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError(f"ONNX export failed: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return {
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "output_path": str(output_path),
        "onnx_sha256": sha256_file(output_path),
        "torch_version": str(torch.__version__),
        "torchreid_version": _distribution_version("torchreid", torchreid),
        "onnxruntime_version": str(onnxruntime.__version__),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export a local Torchreid osnet_x0_25 MSMT17 checkpoint. "
            "No checkpoint or dependency is downloaded."
        )
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        type=Path,
        help="operator-supplied Torchreid osnet_x0_25 MSMT17 checkpoint",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"fixed-shape ONNX destination (default: {DEFAULT_OUTPUT})",
    )
    return parser


def _print_record(result: Mapping[str, str]) -> None:
    print("OSNet ONNX export and ONNX Runtime validation succeeded.")
    print(f"checkpoint_path={result['checkpoint_path']}")
    print(f"checkpoint_sha256={result['checkpoint_sha256']}")
    print("checkpoint_source_revision=capture_at_run")
    print("checkpoint_license=capture_at_run")
    print(f"torch_version={result['torch_version']}")
    print(f"torchreid_version={result['torchreid_version']}")
    print(f"onnxruntime_version={result['onnxruntime_version']}")
    print(f"onnx_path={result['output_path']}")
    print(f"onnx_sha256={result['onnx_sha256']}")
    print("onnx_input=input tensor(float) [1,3,256,128]")
    print("onnx_output=embedding tensor(float) [1,512]")
    print("OPERATOR ACTIONS:")
    print("1. Record every line above in the run provenance.")
    print(
        "2. Replace checkpoint_source_revision and checkpoint_license only from "
        "documentary evidence; otherwise retain capture_at_run."
    )
    print(
        "3. Use onnx_path and onnx_sha256 as the OSNet model path and checksum for the run."
    )
    print(
        "4. An authorized maintainer must record onnx_sha256 for osnet_x0_25_msmt17 "
        "before the model-verification gate can pass."
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = export_checkpoint(args.checkpoint, args.output)
    except ExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            "Supply a local Torchreid osnet_x0_25 checkpoint trained on MSMT17; "
            "this script will not search for or download one.",
            file=sys.stderr,
        )
        return 2
    _print_record(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
