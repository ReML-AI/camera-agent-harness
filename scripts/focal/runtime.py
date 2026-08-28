"""Exact, no-default focal runtime profile and endpoint interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from scripts.core.errors import ContractError
from scripts.core.records import sha256_json
from scripts.core.records import SHA256_RE


@dataclass(frozen=True)
class FocalRuntime:
    profile_id: str
    model_id: str
    model_revision: str
    model_checksum: str
    tokenizer_revision: str
    backend_name: str
    backend_version: str
    container_id: str | None
    cuda_gpu: str | None
    dtype_quantization: str
    context_length: int
    chat_template_id: str
    json_parameters: dict
    maximum_output_tokens: int
    stop_sequences: tuple[str, ...]
    seed: int | None
    batching: str
    request_order: tuple[str, ...]
    timeout_seconds: float
    retry_policy: str
    temperature: float
    json_mode: bool

    def __post_init__(self) -> None:
        required_strings = (
            self.profile_id, self.model_id, self.model_revision, self.model_checksum,
            self.tokenizer_revision, self.backend_name, self.backend_version,
            self.dtype_quantization, self.chat_template_id, self.batching, self.retry_policy,
        )
        if any(not value for value in required_strings):
            raise ContractError("every focal runtime identifier must be explicit")
        if self.container_id == "" or self.cuda_gpu == "":
            raise ContractError("container and GPU identifiers must be non-empty or explicit null")
        if not SHA256_RE.fullmatch(self.model_checksum):
            raise ContractError("focal model checksum must be a lowercase SHA-256 digest")
        if self.context_length <= 0 or self.maximum_output_tokens <= 0 or self.timeout_seconds <= 0:
            raise ContractError("focal runtime sizes and timeout must be positive")
        if self.temperature != 0 or self.json_mode is not True:
            raise ContractError("paper focal runtime requires temperature 0 and JSON mode")
        if len(self.request_order) != 2 or set(self.request_order) != {"T", "M"}:
            raise ContractError("focal request order must explicitly contain T and M exactly once")

    @classmethod
    def checked(cls, *, paper_mode: bool = True, **values) -> "FocalRuntime":
        return cls(**values)

    def to_dict(self) -> dict:
        value = asdict(self)
        value["stop_sequences"] = list(self.stop_sequences)
        value["request_order"] = list(self.request_order)
        return value

    @property
    def sha256(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True)
class FocalRequest:
    condition: str
    prompt: str
    runtime: FocalRuntime
    output_schema: dict


class FocalEndpoint(Protocol):
    def complete(self, request: FocalRequest) -> str: ...
