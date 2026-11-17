# Import every model here so Base.metadata knows about all of them — Alembic's
# autogenerate and Base.metadata.create_all() both rely on this file having run.
from app.models.user import User
from app.models.course import Course
from app.models.chapter import Chapter
from app.models.topic import Topic
from app.models.syllabus_document import SyllabusDocument
from app.models.generated_question import GeneratedQuestion
from app.models.quiz_attempt import QuizAttempt
from app.models.exam_attempt import ExamAttempt
from app.models.app_setting import AppSetting
from app.models.past_paper import PastPaper

__all__ = [
    "User",
    "Course",
    "Chapter",
    "Topic",
    "SyllabusDocument",
    "GeneratedQuestion",
    "QuizAttempt",
    "ExamAttempt",
    "AppSetting",
    "PastPaper",
]