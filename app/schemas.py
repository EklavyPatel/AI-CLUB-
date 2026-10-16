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
