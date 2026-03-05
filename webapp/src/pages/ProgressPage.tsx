import { useState, useEffect } from 'react';
import {
  fetchGoals,
  fetchCalendar,
  fetchPatterns,
  type GoalsData,
  type CalendarData,
  type PatternData,
} from '../api';
import type { UserState } from '../hooks/useUser';

interface ProgressPageProps {
  userState: UserState;
}

export function ProgressPage({ userState }: ProgressPageProps) {
  const { loading, error, retry } = userState;
  const [goals, setGoals] = useState<GoalsData | null>(null);
  const [calendar, setCalendar] = useState<CalendarData | null>(null);
  const [patterns, setPatterns] = useState<PatternData[]>([]);

  useEffect(() => {
    fetchGoals().then(setGoals).catch(() => {});
    fetchCalendar().then(setCalendar).catch(() => {});
    fetchPatterns().then(setPatterns).catch(() => {});
  }, []);

  // Loading
  if (loading) {
    return (
      <div className="skeleton-page">
        <div className="skeleton skeleton-title" />
        <div className="skeleton skeleton-card" style={{ marginTop: 20, height: 200 }} />
        <div className="skeleton skeleton-card" style={{ height: 180 }} />
        <div className="skeleton skeleton-card" style={{ height: 80 }} />
      </div>
    );
  }

  // Error
  if (error) {
    return (
      <div className="error-state">
        <div className="error-state__emoji">😔</div>
        <div className="error-state__text">Не удалось загрузить</div>
        <button className="error-state__btn" onClick={retry}>Повторить</button>
      </div>
    );
  }

  const goal = goals?.goal ?? null;
  const streak = calendar?.streak ?? 0;
  const totalSessions = calendar?.total_sessions ?? 0;

  // Goal progress
  const completedSteps = goal ? goal.steps.filter((s) => s.status === 'done').length : 0;
  const totalSteps = goal ? goal.steps.length : 0;
  const progressPercent = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;

  // Calendar
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const today = now.getDate();
  const monthName = now.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
  // Capitalize first letter
  const monthNameCapitalized = monthName.charAt(0).toUpperCase() + monthName.slice(1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDayRaw = new Date(year, month, 1).getDay();
  const firstDayOffset = firstDayRaw === 0 ? 6 : firstDayRaw - 1;

  // Active days set for current month
  const activeDaysSet = new Set(calendar?.active_days ?? []);

  const formatDayStr = (dayNum: number): string => {
    const m = String(month + 1).padStart(2, '0');
    const d = String(dayNum).padStart(2, '0');
    return `${year}-${m}-${d}`;
  };

  const statusIcon = (status: string): string => {
    if (status === 'done') return '✓';
    if (status === 'skipped') return '–';
    return '○';
  };

  return (
    <>
      <div className="page-title">
        <h1>Мой путь</h1>
      </div>

      {/* Цель */}
      <div className="section">
        <div className="section-header">Цель</div>
        <div className="section-card">
          {goal ? (
            <div style={{ padding: '16px' }}>
              <div style={{ fontSize: 17, fontWeight: 600, color: 'var(--text)', marginBottom: 12 }}>
                🎯 {goal.title}
              </div>
              <div className="goal-steps">
                {goal.steps.map((step) => (
                  <div key={step.id} className="goal-step">
                    <div className={`goal-step__icon ${step.status === 'done' ? 'goal-step__icon--done' : step.status === 'skipped' ? 'goal-step__icon--future' : 'goal-step__icon--current'}`}>
                      {statusIcon(step.status)}
                    </div>
                    <div className={`goal-step__text ${step.status === 'done' ? 'goal-step__text--done' : ''}`}>
                      {step.title}
                    </div>
                  </div>
                ))}
              </div>
              <div className="progress-bar" style={{ marginTop: 12 }}>
                <div className="progress-fill progress-fill--green" style={{ width: `${progressPercent}%` }} />
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', textAlign: 'right', marginTop: 4 }}>
                {progressPercent}%
              </div>
            </div>
          ) : (
            <div className="placeholder">
              <div className="placeholder__emoji">✨</div>
              <div className="placeholder__text">Цель появится после первых разговоров с Евой</div>
            </div>
          )}
        </div>
      </div>

      {/* Календарь текущего месяца */}
      <div className="section">
        <div className="section-header">{monthNameCapitalized}</div>
        <div className="section-card">
          <div className="calendar-grid">
            {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((d) => (
              <span key={d} className="calendar-header">{d}</span>
            ))}
            {/* Empty cells before 1st */}
            {Array.from({ length: firstDayOffset }, (_, i) => (
              <span key={`empty-${i}`} className="calendar-day" style={{ visibility: 'hidden' }}>0</span>
            ))}
            {/* Days */}
            {Array.from({ length: daysInMonth }, (_, i) => {
              const dayNum = i + 1;
              const dayStr = formatDayStr(dayNum);
              const isActive = activeDaysSet.has(dayStr);
              const isToday = dayNum === today;
              return (
                <span
                  key={dayNum}
                  className={`calendar-day ${isActive ? 'calendar-day--active' : ''} ${isToday ? 'calendar-day--today' : ''}`}
                >
                  {dayNum}
                </span>
              );
            })}
          </div>
        </div>
      </div>

      {/* Достижения */}
      <div className="section">
        <div className="section-header">Достижения</div>
        <div className="section-card">
          <div className="cell">
            <span className="cell-icon">🔥</span>
            <div className="cell-body">
              <div className="cell-title">Серия</div>
            </div>
            <span className="cell-after">{streak > 0 ? `${streak} дней` : '—'}</span>
          </div>
          <div className="cell">
            <span className="cell-icon">💬</span>
            <div className="cell-body">
              <div className="cell-title">Всего</div>
            </div>
            <span className="cell-after">{totalSessions} сессий</span>
          </div>
        </div>
      </div>

      {/* Паттерны */}
      <div className="section">
        <div className="section-header">Что замечает Ева</div>
        <div className="section-card">
          {patterns.length > 0 ? (
            patterns.slice(0, 3).map((p, i) => (
              <div key={i} className="cell">
                <span className="cell-icon">💡</span>
                <div className="cell-body">
                  <div className="cell-title">{p.pattern_text || p.pattern_type}</div>
                </div>
              </div>
            ))
          ) : (
            <div className="placeholder">
              <div className="placeholder__emoji">🔍</div>
              <div className="placeholder__text">Наставник заметит привычки после 3+ разговоров</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
