"""
VS Bias Prompt Contract - Phase 1
Validates artifact payloads for bias audit prompts.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, validator


class VSBiasContent(BaseModel):
    """The actual prompt content."""
    user_query: str = Field(..., min_length=10, max_length=2000)
    engineered_prompt: str = Field(..., min_length=50, max_length=5000)
    notes_for_lite: Optional[str] = Field(None, max_length=1000)
    bias_dimensions: List[str] = Field(
        default_factory=lambda: ["gender", "race", "age"],
        min_items=1,
        max_items=7,
    )

    @validator("bias_dimensions")
    def validate_dimensions(cls, v: List[str]) -> List[str]:
        valid = {
            "gender",
            "race",
            "age",
            "disability",
            "religion",
            "nationality",
            "sexual_orientation",
        }
        for dim in v:
            if dim not in valid:
                raise ValueError(f"Invalid bias dimension: {dim}")
        return v


class VSBiasContext(BaseModel):
    """Context about where this prompt comes from."""
    app_name: str = Field(default="VS Bias Audit Builder")
    owner: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)


class VSBiasPolishInstructions(BaseModel):
    """What Lite is allowed to change."""
    goals: List[str] = Field(
        default_factory=lambda: [
            "Tighten structure",
            "Clarify bias dimensions",
            "Improve testability",
        ]
    )
    allowed_changes: List[str] = Field(
        default_factory=lambda: [
            "wording",
            "structure",
            "examples",
        ]
    )
    preserve_intent: bool = Field(default=True)
    max_length: Optional[int] = Field(default=1000)


class VSBiasPromptContract(BaseModel):
    """Complete VS Bias artifact contract."""
    artifact_type: str = Field("vs_bias_prompt", const=True)
    content: VSBiasContent
    context: VSBiasContext
    polish_instructions: VSBiasPolishInstructions
    request_id: Optional[str] = None

    @validator("artifact_type")
    def check_artifact_type(cls, v: str) -> str:
        if v != "vs_bias_prompt":
            raise ValueError(f"Expected 'vs_bias_prompt', got '{v}'")
        return v


def validate_vs_bias_prompt(payload: dict) -> VSBiasPromptContract:
    """
    Validate a VS Bias prompt payload.

    Args:
        payload: Raw JSON dict from request.

    Returns:
        Validated VSBiasPromptContract instance.

    Raises:
        pydantic.ValidationError: If payload doesn't match schema.
    """
    return VSBiasPromptContract(**payload)

