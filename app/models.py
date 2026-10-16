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

from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Integer, String,
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
