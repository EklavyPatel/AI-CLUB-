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

    @model_validator(mode="after")
    def _check(self):
        labels = [o.id for o in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError("option ids must be unique within an item")
        if sum(o.is_correct for o in self.options) != 1:
            raise ValueError("each item needs exactly one correct option")
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
    role: Optional[Literal['teacher', 'student']] = None
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @model_validator(mode='after')
    def validate_email(self):
        import re
        self.email = self.email.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.email):
            raise ValueError('Enter a valid email address')
        return self


class Register(Credentials):
    name: str = Field(min_length=1, max_length=128)
    role: Literal['teacher', 'student']


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class InviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class InviteAccept(BaseModel):
    token: str = Field(min_length=20, max_length=128)


class QuizCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    total_time_s: int = Field(ge=10, le=86400)
    question_time_s: int = Field(ge=5, le=3600)
    items: List[ItemCreate] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def unique_items(self):
        ids = [i.item_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError('Question IDs must be unique')
        if not any(not i.is_probe for i in self.items):
            raise ValueError('Include at least one regular question')
        if any(i.parent_item_id and i.parent_item_id not in ids for i in self.items):
            raise ValueError('Probe parent must be included in this quiz')
        return self


class TimedAnswer(BaseModel):
    item_id: str
    chosen_option: Optional[str] = None
    confidence: Literal['Sure', 'Unsure', 'Guessing'] = 'Guessing'
