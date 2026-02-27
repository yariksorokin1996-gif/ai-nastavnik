import { useState, useEffect } from 'react';
import { useUser } from '../hooks/useUser';
import { fetchDaily, fetchPatterns, type DailyData, type PatternData } from '../api';

// Goal milestones from API (future: will come from backend)
// For now, derive from phase
const PHASE_MILESTONES: Record<string, { steps: string[]; current: number }> = {
  onboarding: {
    steps: ['Познакомиться с наставником', 'Рассказать о себе', 'Определить направление', 'Поставить первую цель', 'Начать работу'],
    current: 0,
  },
  diagnosis: {
    steps: ['Познакомиться с наставником', 'Рассказать о себе', 'Определить направление', 'Поставить первую цель', 'Начать работу'],
    current: 1,
  },
  goal: {
    steps: ['Познакомиться с наставником', 'Рассказать о себе', 'Определить направление', 'Поставить первую цель', 'Начать работу'],
    current: 2,
  },
  planning: {
    steps: ['Познакомиться с наставником', 'Рассказать о себе', 'Определить направление', 'Поставить первую цель', 'Начать работу'],
    current: 3,
  },
  daily: {
    steps: ['Познакомиться с наставником', 'Рассказать о себе', 'Определить направление', 'Поставить первую цель', 'Начать работу'],
    current: 4,
  },
};

export function ProgressPage() {
  const { user } = useUser();
  const [daily, setDaily] = useState<DailyData | null>(null);
  const [patterns, setPatterns] = useState<PatternData[]>([]);

  useEffect(() => {
    fetchDaily().then(setDaily).catch(() => {});
    fetchPatterns().then(setPatterns).catch(() => {});
  }, []);

  const phase = user?.phase || 'onboarding';
  const sessionsCount = daily?.sessions_count || user?.sessions_count || 0;
  const streak = daily?.streak || 0;
  const goalName = user?.goal;

  // Milestones
  const milestones = PHASE_MILESTONES[phase] || PHASE_MILESTONES.onboarding;
  const progressPercent = Math.round((milestones.current / milestones.steps.length) * 100);

  // Dynamic calendar
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const today = now.getDate();
  const monthName = now.toLocaleDateString('ru-RU', { month: 'long' });
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  // Day of week for 1st of month (0=Sun, convert to Mon=0)
  const firstDayRaw = new Date(year, month, 1).getDay();
  const firstDayOffset = firstDayRaw === 0 ? 6 : firstDayRaw - 1;

  // Patterns for display
  const displayPatterns = patterns.length > 0
    ? patterns
    : (daily?.recent_patterns || []);

  return (
    <>
      <div className="page-title">
        <h1>Мой путь</h1>
      </div>

      {/* Цель с шагами */}
      <div className="section">
        <div className="section-header">Цель</div>
        <div className="section-card">
          {goalName || sessionsCount > 0 ? (
            <div style={{ padding: '16px' }}>
              <div style={{ fontSize: 17, fontWeight: 600, color: 'var(--text)', marginBottom: 12 }}>
                🎯 {goalName || 'Знакомство с наставником'}
              </div>
              <div className="goal-steps">
                {milestones.steps.map((step, i) => {
                  const isDone = i < milestones.current;
                  const isCurrent = i === milestones.current;
                  return (
                    <div key={i} className="goal-step">
                      <div className={`goal-step__icon ${isDone ? 'goal-step__icon--done' : isCurrent ? 'goal-step__icon--current' : 'goal-step__icon--future'}`}>
                        {isDone ? '✅' : isCurrent ? '→' : '○'}
                      </div>
                      <div className={`goal-step__text ${isDone ? 'goal-step__text--done' : isCurrent ? 'goal-step__text--current' : ''}`}>
                        {step}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="progress-bar" style={{ marginTop: 12 }}>
                <div className="progress-fill progress-fill--green" style={{ width: `${progressPercent}%` }} />
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', textAlign: 'right', marginTop: 4 }}>
                {progressPercent}%
              </div>
              <div className="goal-hint">
                Хочешь сменить цель? Просто скажи наставнику
              </div>
            </div>
          ) : (
            <div className="placeholder">
              <div className="placeholder__emoji">✨</div>
              <div className="placeholder__text">Цель появится после первого разговора с наставником</div>
            </div>
          )}
        </div>
      </div>

      {/* Календарь — динамический */}
      <div className="section">
        <div className="section-header">{monthName}</div>
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
              // Sessions in recent days (simple heuristic: last N days based on streak)
              const isDone = dayNum < today && dayNum >= today - Math.min(streak, today - 1);
              const isToday = dayNum === today;
              return (
                <span
                  key={dayNum}
                  className={`calendar-day ${isDone ? 'calendar-day--done' : ''} ${isToday ? 'calendar-day--today' : ''}`}
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
              <div className="cell-title">Серия дней</div>
            </div>
            <span className="cell-after">{streak || '—'}</span>
          </div>
          <div className="cell">
            <span className="cell-icon">💬</span>
            <div className="cell-body">
              <div className="cell-title">Всего сессий</div>
            </div>
            <span className="cell-after">{sessionsCount}</span>
          </div>
        </div>
      </div>

      {/* Паттерны */}
      <div className="section">
        <div className="section-header">Что замечает наставник</div>
        <div className="section-card">
          {displayPatterns.length > 0 ? (
            displayPatterns.slice(0, 3).map((p, i) => (
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
              <div className="placeholder__text">Наставник заметит привычки после 3+ сессий</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
