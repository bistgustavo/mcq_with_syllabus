"""Pydantic schemas for the MCQ Generator Platform API.

Every schema (Day 1-4 names and the Day 5-12 additions) is re-exported here so
routers and services can ``from app.schemas import ...``. Submodules must only
import from sibling submodules (never from this package) to avoid cycles.
"""

from app.schemas.chapter import ChapterCreate, ChapterRead, ChapterTree, ChapterUpdate
from app.schemas.course import CourseCreate, CourseRead, CourseSummary, CourseTree, CourseUpdate
from app.schemas.generated_question import (
    DIFFICULTIES,
    OPTION_COUNT,
    AsyncTaskAccepted,
    GeneratedQuestionCreate,
    GeneratedQuestionRead,
    GenerateQuestionsRequest,
    GenerationResponse,
    QuestionHistory,
    QuizQuestionPublic,
    validate_difficulty,
)
from app.schemas.quiz_attempt import (
    AdminOverview,
    AttemptSummary,
    QuizStart,
    TopicProgress,
    UserDashboard,
    QuizAnswer,
    QuizAttemptCreate,
    QuizAttemptRead,
    QuizResult,
    QuizResultItem,
    QuizSubmission,
    TopicStats,
)
from app.schemas.syllabus_document import (
    SyllabusDocumentCreate,
    SyllabusDocumentRead,
    UploadResponse,
)
from app.schemas.topic import TopicCreate, TopicDetail, TopicRead, TopicStatus, TopicTree, TopicUpdate
from app.schemas.user import AdminUserUpdate, Token, UserCreate, UserRead, UserUpdate

__all__ = [
    "AdminOverview",
    "AdminUserUpdate",
    "ChapterUpdate",
    "CourseSummary",
    "CourseUpdate",
    "QuizStart",
    "TopicDetail",
    "TopicProgress",
    "TopicUpdate",
    "UserDashboard",
    "UserUpdate",
    # users / auth
    "UserCreate",
    "UserRead",
    "Token",
    # courses / chapters / topics
    "CourseCreate",
    "CourseRead",
    "CourseTree",
    "ChapterCreate",
    "ChapterRead",
    "ChapterTree",
    "TopicCreate",
    "TopicRead",
    "TopicStatus",
    "TopicTree",
    # documents
    "SyllabusDocumentCreate",
    "SyllabusDocumentRead",
    "UploadResponse",
    # generation
    "DIFFICULTIES",
    "OPTION_COUNT",
    "validate_difficulty",
    "GeneratedQuestionCreate",
    "GeneratedQuestionRead",
    "GenerateQuestionsRequest",
    "GenerationResponse",
    "AsyncTaskAccepted",
    "QuestionHistory",
    "QuizQuestionPublic",
    # quiz
    "QuizAttemptCreate",
    "QuizAttemptRead",
    "QuizAnswer",
    "QuizSubmission",
    "QuizResultItem",
    "QuizResult",
    "TopicStats",
    "AttemptSummary",
]
