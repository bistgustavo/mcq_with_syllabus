"""Schemas for quiz submission, server-side scoring, attempt history and stats."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.generated_question import OPTION_COUNT


class QuizAttemptCreate(BaseModel):
    """Raw attempt record (kept for compatibility with Day 1-4 code paths)."""

    user_id: int | None = None
    topic_id: int
    question_ids: list[int]
    answers: list[int | None] | None = None
    score: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class QuizAttemptRead(BaseModel):
    """Stored quiz attempt, including the chosen option index per question."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    topic_id: int
    question_ids: list[int]
    answers: list[int | None] | None = None
    score: int
    total: int
    created_at: datetime | None = None


class QuizAnswer(BaseModel):
    """One answer in a submission; ``selected_index`` is null when skipped."""

    question_id: int
    selected_index: Annotated[int, Field(ge=0, le=OPTION_COUNT - 1)] | None = None


class QuizSubmission(BaseModel):
    """Body of ``POST /quiz-attempts``."""

    topic_id: int
    answers: list[QuizAnswer] = Field(..., min_length=1, max_length=100)
    difficulty: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)


class QuizResultItem(BaseModel):
    """Per-question outcome returned after scoring."""

    question_id: int
    question_text: str
    options: list[str]
    selected_index: int | None = None
    correct_index: int
    is_correct: bool
    explanation: str | None = None
    source: str | None = None
    reference: str | None = None


class QuizResult(BaseModel):
    """Scored attempt returned by ``POST /quiz-attempts``."""

    attempt_id: int
    topic_id: int
    score: int
    total: int
    percent: float
    results: list[QuizResultItem]
    difficulty: str | None = None
    duration_seconds: int | None = None
    created_at: datetime | None = None


class TopicStats(BaseModel):
    """Aggregate statistics for a topic (``GET /topics/{id}/stats``)."""

    topic_id: int
    question_count: int
    attempts: int
    avg_percent: float
    best_percent: float
    by_source: dict[str, int] = Field(default_factory=dict)


class AttemptSummary(BaseModel):
    """Row of ``GET /quiz-attempts/me``: attempt plus the topic's name."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int | None = None
    topic_name: str
    course_name: str | None = None
    score: int
    total: int
    percent: float
    difficulty: str | None = None
    duration_seconds: int | None = None
    created_at: datetime | None = None


class QuizStart(BaseModel):
    """Questions served for a new quiz (answers withheld)."""

    topic_id: int
    topic_name: str
    difficulty: str | None = None
    requested: int
    available: int
    fresh_generated: int = 0  # written on the spot for this quiz
    repeats: int = 0  # questions the student has seen before
    questions: list["QuizQuestionPublicRef"]


class QuizQuestionPublicRef(BaseModel):
    id: int
    question_text: str
    options: list[str]
    difficulty: str = "medium"
    source: str


QuizStart.model_rebuild()


class TopicProgress(BaseModel):
    topic_id: int
    topic_name: str
    course_name: str | None = None
    attempts: int
    avg_percent: float
    best_percent: float
    last_attempt_at: datetime | None = None


class UserDashboard(BaseModel):
    """Aggregates shown on the student's dashboard."""

    attempts: int
    avg_percent: float
    best_percent: float
    questions_answered: int
    correct_answers: int
    topics_practiced: int
    recent: list[AttemptSummary]
    topics: list[TopicProgress]
    weakest_topics: list[TopicProgress]


class AdminOverview(BaseModel):
    users: int
    courses: int
    chapters: int
    topics: int
    topics_with_content: int
    documents: int
    questions: int
    attempts: int
    questions_by_source: dict[str, int]
    questions_by_difficulty: dict[str, int]
