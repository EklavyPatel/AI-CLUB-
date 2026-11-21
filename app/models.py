"""
Relational schema for Beyond the Number.

  skills ──< items ──< options >── misconceptions
               │  └── (probe items point to their parent item)
  classrooms ──< learners ──< responses >── options
                    └──< profiles (one per learner + skill)

The key idea: a `response` stores the raw evidence (answer, confidence, time),
and `story` stores WHY we think the learner got it that way. A wrong answer is
a clue, not a verdict: its story is only decided once enough evidence exists.
"""
from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String,
                        Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Skill(Base):
    __tablename__ = "skills"
    skill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))


class Misconception(Base):
    __tablename__ = "misconceptions"
    code: Mapped[str] = mapped_column(String(96), primary_key=True)
    skill_id: Mapped[str | None] = mapped_column(ForeignKey("skills.skill_id"), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    remediation: Mapped[str] = mapped_column(Text, default="")


class Item(Base):
    __tablename__ = "items"
    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.skill_id"), index=True)
    stem: Mapped[str] = mapped_column(Text)
    is_probe: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_item_id: Mapped[str | None] = mapped_column(ForeignKey("items.item_id"), nullable=True, index=True)
    expected_time_s: Mapped[int] = mapped_column(Integer, default=30)

    options: Mapped[list["Option"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Option.label"
    )


class Option(Base):
    __tablename__ = "options"
    __table_args__ = (UniqueConstraint("item_id", "label", name="uq_option_item_label"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.item_id"), index=True)
    label: Mapped[str] = mapped_column(String(8))  # "A", "B", ...
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    misconception_code: Mapped[str | None] = mapped_column(ForeignKey("misconceptions.code"), nullable=True)

    item: Mapped[Item] = relationship(back_populates="options")
    misconception: Mapped[Misconception | None] = relationship()


class Classroom(Base):
    __tablename__ = "classrooms"
    class_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))


class ClassroomCode(Base):
    __tablename__ = 'classroom_codes'
    class_id: Mapped[str] = mapped_column(ForeignKey('classrooms.class_id'), primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)


class Learner(Base):
    __tablename__ = "learners"
    learner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    class_id: Mapped[str | None] = mapped_column(ForeignKey("classrooms.class_id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Response(Base):
    __tablename__ = "responses"
    response_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.learner_id"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.item_id"), index=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.skill_id"), index=True)
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id"))
    correct: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[str] = mapped_column(String(16))  # Sure | Unsure | Guessing
    time_ms: Mapped[int] = mapped_column(Integer)
    is_probe: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_response_id: Mapped[int | None] = mapped_column(ForeignKey("responses.response_id"), nullable=True)
    # secure | fragile_correct | knowledge_gap | rushed | unresolved | missed_condition | mistaken_rule
    story: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    option: Mapped[Option] = relationship()


class Profile(Base):
    __tablename__ = "profiles"
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.learner_id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.skill_id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(32))
    dominant_misconception: Mapped[str | None] = mapped_column(ForeignKey("misconceptions.code"), nullable=True)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    stories: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_needed: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(Text)
    sid: Mapped[str] = mapped_column(String(64), default='', server_default='')
    branch: Mapped[str] = mapped_column(String(128), default='', server_default='')


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ClassOwner(Base):
    __tablename__ = 'class_owners'
    class_id: Mapped[str] = mapped_column(ForeignKey('classrooms.class_id'), primary_key=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)


class Membership(Base):
    __tablename__ = 'memberships'
    class_id: Mapped[str] = mapped_column(ForeignKey('classrooms.class_id'), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), primary_key=True)


class Invitation(Base):
    __tablename__ = 'invitations'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    class_id: Mapped[str] = mapped_column(ForeignKey('classrooms.class_id'))
    email: Mapped[str] = mapped_column(String(254))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)


class Quiz(Base):
    __tablename__ = 'quizzes'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    class_id: Mapped[str] = mapped_column(ForeignKey('classrooms.class_id'), index=True)
    title: Mapped[str] = mapped_column(String(128))
    skill_id: Mapped[str] = mapped_column(ForeignKey('skills.skill_id'), unique=True)
    total_time_s: Mapped[int] = mapped_column(Integer)


class QuizAttempt(Base):
    __tablename__ = 'quiz_attempts'
    __table_args__ = (UniqueConstraint('quiz_id', 'learner_id', name='uq_quiz_learner'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey('quizzes.id'), index=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    deadline: Mapped[datetime] = mapped_column(DateTime)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    question_started_at: Mapped[datetime] = mapped_column(DateTime)
    question_deadline: Mapped[datetime] = mapped_column(DateTime)


class ExamPolicy(Base):
    __tablename__ = 'exam_policies'
    quiz_id: Mapped[str] = mapped_column(ForeignKey('quizzes.id'), primary_key=True)
    question_count: Mapped[int] = mapped_column(Integer)
    bank: Mapped[list] = mapped_column(JSON)
    negative_marks: Mapped[float] = mapped_column(Float, default=0.0, server_default='0.0')
    schedule_mode: Mapped[str] = mapped_column(String(16), default='instant', server_default='instant')
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ExamPaper(Base):
    __tablename__ = 'exam_papers'
    __table_args__ = (UniqueConstraint('quiz_id', 'signature', name='uq_exam_set'),)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('quiz_attempts.id'), primary_key=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey('quizzes.id'), index=True)
    signature: Mapped[str] = mapped_column(String(64))
    questions: Mapped[list] = mapped_column(JSON)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
