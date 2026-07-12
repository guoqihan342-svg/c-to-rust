from __future__ import annotations

from dataclasses import dataclass
import re


COMPETITION_LOGICAL_MODEL = "GLM-5.1"
DEFAULT_RESOLVED_MODEL = "zai/glm-5.1"
KNOWN_LOGICAL_MODELS = {
    DEFAULT_RESOLVED_MODEL: COMPETITION_LOGICAL_MODEL,
    "opencode/deepseek-v4-flash-free": "DeepSeek-V4-Flash",
}


@dataclass(frozen=True)
class ModelIdentity:
    provider_label: str
    logical_model: str
    resolved_model: str
    competition_eligible: bool
    evaluation_scope: str

    @property
    def candidate_id(self) -> str:
        if self.competition_eligible:
            return "opencode-glm51-1"
        slug = re.sub(r"[^a-z0-9]+", "-", self.logical_model.lower()).strip("-")
        return f"opencode-{slug[:64]}-1"


def resolve_model_identity(resolved_model: str) -> ModelIdentity:
    if not isinstance(resolved_model, str) or resolved_model != resolved_model.strip():
        raise ValueError("resolved model must be a non-empty provider/model id")
    provider, separator, model = resolved_model.partition("/")
    if not separator or not provider or not model or any(char.isspace() for char in resolved_model):
        raise ValueError("resolved model must be a non-empty provider/model id")
    competition_eligible = resolved_model == DEFAULT_RESOLVED_MODEL
    return ModelIdentity(
        provider_label=provider,
        logical_model=KNOWN_LOGICAL_MODELS.get(resolved_model, model),
        resolved_model=resolved_model,
        competition_eligible=competition_eligible,
        evaluation_scope=(
            "competition-primary" if competition_eligible else "auxiliary-local-validation"
        ),
    )


__all__ = [
    "COMPETITION_LOGICAL_MODEL",
    "DEFAULT_RESOLVED_MODEL",
    "ModelIdentity",
    "resolve_model_identity",
]
