from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class OptionIn(BaseModel):
    id: str = Field(min_length=1, max_length=8)  # the label: "A", "B", ...
    text: str
    is_correct: bool = False
    misconception_code: Optional[str] = None


class ItemCreate(BaseModel):
    item_id: str
    skill_id: str
    stem: str
    options: List[OptionIn]
    is_probe: bool = False
    parent_item_id: Optional[str] = None
    expected_time_s: int = Field(default=30, ge=1)
    kind: Literal['single', 'multiple'] = 'single'

    @model_validator(mode="after")
    def _check(self):
        labels = [o.id for o in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError("option ids must be unique within an item")
        if self.kind == 'single' and sum(o.is_correct for o in self.options) != 1:
            raise ValueError("each item needs exactly one correct option")
        if not self.stem.strip() or not self.options or not any(o.is_correct for o in self.options):
            raise ValueError('Question text, options, and an answer key are required')
        if any(not o.text.strip() for o in self.options):
            raise ValueError('Option text cannot be blank')
        if self.is_probe and not self.parent_item_id:
            raise ValueError("a probe item must set parent_item_id")
        return self


class ResponseSubmit(BaseModel):
    learner_id: str
    item_id: str
    skill_id: str
    chosen_option: str
    confidence: Literal["Sure", "Unsure", "Guessing"]
    time_ms: int = Field(ge=0)
    is_probe: bool = False
    parent_item_id: Optional[str] = None


class Credentials(BaseModel):
    sid: str = Field(default='', max_length=64)
    branch: str = Field(default='', max_length=128)
    role: Optional[Literal['teacher', 'student']] = None
    email: str = Field(default='', max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @model_validator(mode='after')
    def validate_email(self):
        import re
        self.sid = self.sid.strip()
        self.branch = self.branch.strip()
        self.email = self.email.strip()
        if not self.email and not self.sid:
            raise ValueError('Email or student ID is required')
        if self.email:
            if '@' in self.email:
                self.email = self.email.lower()
                if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.email):
                    raise ValueError('Enter a valid email address')
            else:
                if not self.sid:
                    self.sid = self.email
        return self


class Register(Credentials):
    name: str = Field(min_length=1, max_length=128)
    role: Literal['teacher', 'student']

    @model_validator(mode='after')
    def validate_register(self):
        import re
        if not self.email or '@' not in self.email or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.email):
            raise ValueError('Enter a valid email address')
        return self


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class InviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class InviteAccept(BaseModel):
    token: str = Field(min_length=20, max_length=128)


class RoomJoin(BaseModel):
    code: str

    @model_validator(mode='after')
    def normalize_code(self):
        import re
        self.code = self.code.strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{8}', self.code):
            raise ValueError('Enter the 8-character classroom code')
        return self


class QuizCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    total_time_s: int = Field(ge=10, le=86400)
    question_time_s: int = Field(ge=5, le=3600)
    items: List[ItemCreate] = Field(min_length=1, max_length=200)
    mode: Literal['legacy', 'mcq'] = 'legacy'
    question_count: int | None = Field(default=None, ge=1, le=200)
    negative_marks: float = Field(default=0.0, ge=0.0, le=5.0)
    schedule_mode: Literal['instant', 'scheduled'] = 'instant'
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @model_validator(mode='after')
    def unique_items(self):
        ids = [i.item_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError('Question IDs must be unique')
        if not any(not i.is_probe for i in self.items):
            raise ValueError('Include at least one regular question')
        if any(i.parent_item_id and i.parent_item_id not in ids for i in self.items):
            raise ValueError('Probe parent must be included in this quiz')
        if self.mode == 'legacy' and any(i.kind != 'single' for i in self.items):
            raise ValueError('Multiple choice requires MCQ mode')
        if self.mode == 'mcq':
            count = self.question_count or len(self.items)
            if any(i.is_probe for i in self.items):
                raise ValueError('MCQ banks cannot contain probe questions')
            if count > len(self.items):
                raise ValueError('Questions per student cannot exceed bank size')
        if self.schedule_mode == 'scheduled':
            if not self.start_time or not self.end_time:
                raise ValueError('Scheduled assessments require start and end times')
            if self.end_time <= self.start_time:
                raise ValueError('End time must be after start time')
        return self


class ExamSubmission(BaseModel):
    answers: dict[str, list[str]]


class TimedAnswer(BaseModel):
    item_id: str
    chosen_option: Optional[str] = None
    confidence: Literal['Sure', 'Unsure', 'Guessing'] = 'Guessing'
