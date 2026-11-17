"""Schemas for generated MCQs, generation requests/responses and quiz-safe views."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

DIFFICULTIES: tuple[str, ...] = ("easy", "medium", "hard")
OPTION_COUNT = 4


def validate_difficulty(value: str) -> str:
    """Normalise a difficulty label and ensure it is one of ``DIFFICULTIES``."""
    normalised = (value or "").strip().lower()
    if normalised not in DIFFICULTIES:
        raise ValueError(f"difficulty must be one of: {', '.join(DIFFICULTIES)}")
    return normalised


class GeneratedQuestionCreate(BaseModel):
    """Payload for storing a single MCQ (services / admin tooling)."""

    topic_id: int
    question_text: str = Field(..., min_length=1)
    options: list[str]
    correct_index: int = Field(..., ge=0, le=OPTION_COUNT - 1)
    explanation: str = ""
    source: str = Field(default="ollama", max_length=50)
    difficulty: str = "medium"

    @field_validator("options")
    @classmethod
    def exactly_four_options(cls, value: list[str]) -> list[str]:
        """Every MCQ must carry exactly four non-empty options."""
        if len(value) != OPTION_COUNT:
            raise ValueError(f"exactly {OPTION_COUNT} options are required")
        if any(not str(option).strip() for option in value):
            raise ValueError("options must not be empty")
        return value

    @field_validator("difficulty")
    @classmethod
    def check_difficulty(cls, value: str) -> str:
        """Difficulty must be easy, medium or hard."""
        return validate_difficulty(value)


class GeneratedQuestionRead(BaseModel):
    """Full representation of a stored MCQ, including the answer key."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    question_text: str
    options: list[str]
    correct_index: int
    explanation: str | None = None
    source: str
    difficulty: str = "medium"
    question_hash: str | None = None
    reference: str | None = None
    created_at: datetime | None = None


class GenerateQuestionsRequest(BaseModel):
    """Body of ``POST /topics/{id}/generate-questions``."""

    count: int = Field(default=10, ge=1, le=25)
    difficulty: str = "medium"  # or "mixed": a spread of easy/medium/hard in one run
    use_web_fallback: bool = True
    run_async: bool = False

    @field_validator("difficulty")
    @classmethod
    def check_difficulty(cls, value: str) -> str:
        """Difficulty must be easy, medium, hard or mixed."""
        if (value or "").strip().lower() == "mixed":
            return "mixed"
        return validate_difficulty(value)


class QuizQuestionPublic(BaseModel):
    """Question as served to a quiz taker: no ``correct_index``, no ``explanation``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    question_text: str
    options: list[str]
    difficulty: str = "medium"
    source: str


class GenerationResponse(BaseModel):
    """Result of a synchronous generation run (mirrors ``quiz_service.generate_for_topic``)."""

    topic_id: int
    questions: list[GeneratedQuestionRead]
    source: str
    model: str
    context_source: str
    requested: int
    generated: int


class AsyncTaskAccepted(BaseModel):
    """Body returned (HTTP 202) when generation is queued on Celery."""

    task_id: str
    topic_id: int
    message: str


class QuestionHistory(BaseModel):
    """Paginated list of a topic's stored questions."""

    total: int
    limit: int
    offset: int
    items: list[GeneratedQuestionRead]
