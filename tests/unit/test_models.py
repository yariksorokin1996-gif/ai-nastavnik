"""
Тесты для shared/models.py (20 тестов) + shared/config.py (3 теста).
Валидация Pydantic-моделей: happy path, edge cases, ValidationError.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from pydantic import ValidationError

from shared.models import (
    ContextMeta,
    CrisisResult,
    DailyMessage,
    Episode,
    FullUpdateResult,
    Goal,
    GoalStep,
    MiniUpdateResult,
    PauseContext,
    PersonEntry,
    PhaseEvaluation,
    ProceduralMemory,
    ProfileDiff,
    SemanticProfile,
    SessionFeedback,
    WebappEvent,
)


# ===========================================================================
# PersonEntry
# ===========================================================================


def test_person_entry_valid():
    """PersonEntry с обязательным name и опциональными полями."""
    entry = PersonEntry(name="Саша", relation="муж")
    assert entry.name == "Саша"
    assert entry.relation == "муж"
    assert entry.description is None
    assert entry.how_user_calls is None


# ===========================================================================
# SemanticProfile
# ===========================================================================


def test_semantic_profile_minimal():
    """Пустой SemanticProfile — все поля Optional, дефолт None/[]."""
    profile = SemanticProfile()
    assert profile.name is None
    assert profile.age is None
    assert profile.city is None
    assert profile.people == []
    assert profile.triggers is None


def test_semantic_profile_full():
    """SemanticProfile с заполненными полями и вложенным PersonEntry."""
    profile = SemanticProfile(
        name="Маша",
        age=32,
        city="Москва",
        family="замужем",
        work="дизайнер",
        main_problem="тревожность",
        root_pattern="перфекционизм",
        current_goal="научиться отдыхать",
        communication_style="эмоциональная",
        triggers=["критика", "дедлайны"],
        strengths=["эмпатия", "креативность"],
        achievements=["повышение"],
        sensitive_topics=["отношения с мамой"],
        people=[PersonEntry(name="мама", relation="мать")],
    )
    assert profile.name == "Маша"
    assert profile.age == 32
    assert len(profile.people) == 1
    assert profile.people[0].name == "мама"
    assert profile.triggers == ["критика", "дедлайны"]


# ===========================================================================
# ProfileDiff
# ===========================================================================


def test_profile_diff_defaults():
    """ProfileDiff() -> пустые дефолты."""
    diff = ProfileDiff()
    assert diff.set_fields == {}
    assert diff.add_to_lists == {}
    assert diff.remove_fields == []


# ===========================================================================
# Episode
# ===========================================================================


def test_episode_valid():
    """Episode с обязательными полями."""
    ep = Episode(
        title="Ссора с мужем",
        summary="Обсудили конфликт и нашли компромисс",
        emotional_tone="злость -> принятие",
    )
    assert ep.title == "Ссора с мужем"
    assert ep.emotional_tone == "злость -> принятие"
    assert ep.key_insight is None
    assert ep.commitments == []


def test_episode_key_insight_nullable():
    """Episode с key_insight=None — OK."""
    ep = Episode(
        title="Тест",
        summary="Тест",
        emotional_tone="нейтрально",
        key_insight=None,
    )
    assert ep.key_insight is None


# ===========================================================================
# ProceduralMemory
# ===========================================================================


def test_procedural_memory_defaults():
    """ProceduralMemory() -> пустые списки и dict."""
    pm = ProceduralMemory()
    assert pm.what_works == []
    assert pm.what_doesnt == []
    assert pm.communication_style == {}


# ===========================================================================
# PhaseEvaluation
# ===========================================================================


def test_phase_evaluation_advance():
    """PhaseEvaluation(recommendation='advance', confidence=0.8) — OK."""
    pe = PhaseEvaluation(recommendation="advance", confidence=0.8)
    assert pe.recommendation == "advance"
    assert pe.confidence == 0.8
    assert pe.criteria_met == []


def test_phase_evaluation_invalid_recommendation():
    """recommendation='jump' -> ValidationError (Literal['advance','stay'])."""
    with pytest.raises(ValidationError):
        PhaseEvaluation(recommendation="jump", confidence=0.5)


def test_phase_evaluation_confidence_out_of_range():
    """confidence=1.5 -> ValidationError (le=1.0)."""
    with pytest.raises(ValidationError):
        PhaseEvaluation(recommendation="stay", confidence=1.5)


# ===========================================================================
# Goal + GoalStep
# ===========================================================================


def test_goal_and_goal_step():
    """Goal и GoalStep с дефолтами."""
    goal = Goal(telegram_id=123, title="Медитировать каждый день")
    assert goal.status == "active"
    assert goal.created_at is None
    assert goal.completed_at is None

    step = GoalStep(goal_id=1, telegram_id=123, title="Скачать приложение")
    assert step.status == "pending"
    assert step.sort_order == 0
    assert step.deadline_at is None


# ===========================================================================
# MiniUpdateResult
# ===========================================================================


def test_mini_update_result_with_work_experience():
    """MiniUpdateResult с names, age, work_experience."""
    result = MiniUpdateResult(names=["Саша"], age=32, work_experience=5)
    assert result.names == ["Саша"]
    assert result.age == 32
    assert result.work_experience == 5
    assert result.commitments == []
    assert result.emotions == []


# ===========================================================================
# FullUpdateResult
# ===========================================================================


def test_full_update_result():
    """FullUpdateResult с telegram_id и profile_updated."""
    result = FullUpdateResult(telegram_id=123, profile_updated=True)
    assert result.telegram_id == 123
    assert result.profile_updated is True
    assert result.episode_id is None
    assert result.procedural_updated is False
    assert result.pending_facts_processed == 0
    assert result.error is None


# ===========================================================================
# CrisisResult
# ===========================================================================


def test_crisis_result_valid():
    """CrisisResult level=2, trigger, is_verified."""
    cr = CrisisResult(level=2, trigger="хочу умереть", is_verified=True)
    assert cr.level == 2
    assert cr.trigger == "хочу умереть"
    assert cr.is_verified is True


def test_crisis_result_invalid_level():
    """level=5 -> ValidationError (le=3)."""
    with pytest.raises(ValidationError):
        CrisisResult(level=5, trigger="test")


# ===========================================================================
# WebappEvent
# ===========================================================================


def test_webapp_event():
    """WebappEvent с обязательными и дефолтными полями."""
    ev = WebappEvent(telegram_id=123, event_type="page_view")
    assert ev.telegram_id == 123
    assert ev.event_type == "page_view"
    assert ev.page is None
    assert ev.metadata == {}


# ===========================================================================
# DailyMessage
# ===========================================================================


def test_daily_message():
    """DailyMessage с обязательными полями."""
    dm = DailyMessage(telegram_id=123, message_text="Привет", day_number=1)
    assert dm.telegram_id == 123
    assert dm.message_text == "Привет"
    assert dm.day_number == 1


# ===========================================================================
# SessionFeedback
# ===========================================================================


def test_session_feedback():
    """SessionFeedback с дефолтами."""
    fb = SessionFeedback(telegram_id=123, episode_id=1)
    assert fb.telegram_id == 123
    assert fb.episode_id == 1
    assert fb.feeling_after is None
    assert fb.tried_in_practice is None


# ===========================================================================
# ContextMeta
# ===========================================================================


def test_context_meta_defaults():
    """ContextMeta() -> was_truncated=False, пустые списки."""
    cm = ContextMeta()
    assert cm.was_truncated is False
    assert cm.filled_vars == []
    assert cm.tokens_per_var == {}
    assert cm.truncated_vars == []


# ===========================================================================
# PauseContext
# ===========================================================================


def test_pause_context():
    """PauseContext с обязательным pause_minutes."""
    pc = PauseContext(pause_minutes=30)
    assert pc.pause_minutes == 30
    assert pc.last_topic is None
    assert pc.last_emotion is None


# ===========================================================================
# shared/config.py
# ===========================================================================


def test_config_has_all_variables():
    """config содержит все необходимые переменные."""
    import shared.config as cfg

    required = [
        "CLAUDE_MODEL",
        "GPT_MODEL",
        "OWNER_TELEGRAM_ID",
        "TOKEN_BUDGET_SOFT",
        "RATE_LIMIT_PER_MINUTE",
        "CLAUDE_TIMEOUT",
        "GPT_TIMEOUT",
        "FALLBACK_RESPONSE",
        "FULL_UPDATE_PAUSE_MINUTES",
        "ALERT_THRESHOLDS",
    ]
    for attr in required:
        assert hasattr(cfg, attr), f"config не содержит {attr}"


def test_alert_thresholds_keys():
    """ALERT_THRESHOLDS содержит все 4 ключа."""
    import shared.config as cfg

    expected_keys = {
        "consecutive_empty_context",
        "consecutive_errors",
        "latency_critical_ms",
        "crisis_level_3",
    }
    assert set(cfg.ALERT_THRESHOLDS.keys()) == expected_keys


def test_fallback_response_not_empty():
    """FALLBACK_RESPONSE не пустой."""
    import shared.config as cfg

    assert len(cfg.FALLBACK_RESPONSE) > 0
