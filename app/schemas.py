from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.config import get_settings


class AskRequest(BaseModel):
    question: str = Field(..., description="Business question in plain English",
                          examples=["Which product generated the highest revenue?"])

    @field_validator("question")
    @classmethod
    def _check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        if len(v) > get_settings().max_question_length:
            raise ValueError(f"question must be at most {get_settings().max_question_length} characters")
        return v


class AskResponse(BaseModel):
    question: str
    status: Literal["success", "unsupported"]
    intent: str | None
    answer: str
    metrics: dict[str, Any]
    supporting_data: list[dict[str, Any]]
    data_quality: dict[str, Any]
    interpretation_method: Literal["claude", "rule_based"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error: ErrorBody
