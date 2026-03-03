"""Pydantic-модели для всех внутренних структур данных."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class PersonEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    relation: Optional[str] = None
    description: Optional[str] = None
    how_user_calls: Optional[str] = None


class SemanticProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: Optional[str] = None
    age: Optional[int] = None
    city: Optional[str] = None
    family: Optional[str] = None
    work: Optional[str] = None
    main_problem: Optional[str] = None
    root_pattern: Optional[str] = None
    current_goal: Optional[str] = None
    communication_style: Optional[str] = None
    triggers: Optional[list[str]] = None
    strengths: Optional[list[str]] = None
    achievements: Optional[list[str]] = None
    sensitive_topics: Optional[list[str]] = None
    people: list[PersonEntry] = Field(default_factory=list)


class ProfileDiff(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    set_fields: dict[str, Any] = Field(default_factory=dict)
    add_to_lists: dict[str, list[Any]] = Field(default_factory=dict)
    remove_fields: list[str] = Field(default_factory=list)


class Episode(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    title: str
    summary: str
    emotional_tone: str
    key_insight: Optional[str] = None
    commitments: list[str] = Field(default_factory=list)
    techniques_worked: list[str] = Field(default_factory=list)
    techniques_failed: list[str] = Field(default_factory=list)


class ProceduralMemory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    what_works: list[str] = Field(default_factory=list)
    what_doesnt: list[str] = Field(default_factory=list)
    communication_style: dict[str, Any] = Field(default_factory=dict)


class PhaseEvaluation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    recommendation: Literal['advance', 'stay']
    confidence: float = Field(ge=0.0, le=1.0)
    criteria_met: list[str] = Field(default_factory=list)


class Goal(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    telegram_id: int
    title: str
    status: str = 'active'
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


class GoalStep(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    goal_id: int
    telegram_id: int
    title: str
    status: str = 'pending'
    sort_order: int = 0
    deadline_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class MiniUpdateResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    names: list[str] = Field(default_factory=list)
    commitments: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)
    age: Optional[int] = None
    work_experience: Optional[int] = None


class FullUpdateResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    telegram_id: int
    episode_id: Optional[int] = None
    profile_updated: bool = False
    procedural_updated: bool = False
    pending_facts_processed: int = 0
    error: Optional[str] = None


class ContextMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    filled_vars: list[str] = Field(default_factory=list)
    tokens_per_var: dict[str, int] = Field(default_factory=dict)
    was_truncated: bool = False
    truncated_vars: list[str] = Field(default_factory=list)


class DailyMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    telegram_id: int
    message_text: str
    day_number: int


class PauseContext(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pause_minutes: int
    last_topic: Optional[str] = None
    last_emotion: Optional[str] = None


class SessionFeedback(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    telegram_id: int
    episode_id: int
    feeling_after: Optional[int] = None
    tried_in_practice: Optional[bool] = None


class WebappEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    telegram_id: int
    event_type: str
    page: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrisisResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    level: int = Field(ge=0, le=3)
    trigger: Optional[str] = None
    is_verified: bool = False
