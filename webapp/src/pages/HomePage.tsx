import { useState, useEffect, useCallback } from 'react';
import {
  fetchAffirmation,
  fetchCalendar,
  fetchTodaySteps,
  updateStepStatus,
  type AffirmationData,
  type CalendarData,
  type TodayStepsData,
  type StepData,
} from '../api';
import type { UserState } from '../hooks/useUser';
import { trackEvent } from '../analytics';

const BOT_USERNAME = import.meta.env.VITE_BOT_USERNAME || 'eva_nastavnik_bot';

interface HomePageProps {
  userState: UserState;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}

export function HomePage({ userState, theme, onToggleTheme }: HomePageProps) {
  const { user, loading, error, retry } = userState;

  const [affirmation, setAffirmation] = useState<AffirmationData | null>(null);
  const [calendar, setCalendar] = useState<CalendarData | null>(null);
  const [todaySteps, setTodaySteps] = useState<TodayStepsData | null>(null);
  const [stepErrors, setStepErrors] = useState<Record<number, string>>({});

  const isNewUser = (user?.sessions_count ?? 0) === 0;

  // Load data when user is available
  useEffect(() => {
    if (!user) return;

    fetchAffirmation().then((a) => { setAffirmation(a); trackEvent({ event_type: 'affirmation_view', page: 'home' }); }).catch(() => {});

    if (!isNewUser) {
      fetchCalendar().then(setCalendar).catch(() => {});
      fetchTodaySteps().then(setTodaySteps).catch(() => {});
    }
  }, [user, isNewUser]);

  const handleOpenChat = useCallback(() => {
    trackEvent({ event_type: 'write_eva_click', page: 'home' });
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.openTelegramLink(`https://t.me/${BOT_USERNAME}`);
    }
  }, []);

  const handleToggleStep = useCallback(async (step: StepData) => {
    if (!todaySteps) return;

    const newStatus: 'done' | 'skipped' = step.status === 'done' ? 'skipped' : 'done';

    // Optimistic update
    const prevSteps = todaySteps;
    const updatedSteps = todaySteps.steps.map((s) =>
      s.id === step.id ? { ...s, status: newStatus } : s,
    );
    const completedCount = updatedSteps.filter((s) => s.status === 'done').length;
    setTodaySteps({
      steps: updatedSteps,
      completed_count: completedCount,
      total_count: todaySteps.total_count,
    });
    setStepErrors((prev) => {
      const next = { ...prev };
      delete next[step.id];
      return next;
    });

    window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('success');
    trackEvent({ event_type: newStatus === 'done' ? 'step_complete' : 'step_skip', page: 'home', metadata: { step_id: step.id } });

    try {
      await updateStepStatus(step.id, newStatus);
    } catch {
      // Rollback
      setTodaySteps(prevSteps);
      setStepErrors((prev) => ({ ...prev, [step.id]: 'Не удалось обновить' }));
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('error');
    }
  }, [todaySteps]);

  // Loading
  if (loading) {
    return (
      <div className="skeleton-page">
        <div className="skeleton skeleton-title" />
        <div className="skeleton skeleton-subtitle" />
        <div className="skeleton skeleton-card" style={{ marginTop: 20 }} />
        <div className="skeleton skeleton-card" />
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

  const firstName = user?.name || window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || '';
  const streak = calendar?.streak ?? 0;

  const themeToggle = (
    <button
      className={`theme-toggle ${theme === 'dark' ? 'theme-toggle--dark' : ''}`}
      onClick={() => { onToggleTheme(); trackEvent({ event_type: 'theme_toggle', page: 'home', metadata: { to: theme === 'dark' ? 'light' : 'dark' } }); }}
      aria-label="Переключить тему"
    >
      <span className="theme-toggle__knob">
        {theme === 'dark' ? '🌙' : '☀️'}
      </span>
    </button>
  );

  // ===== NEW USER =====
  if (isNewUser) {
    return (
      <>
        <div className="page-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1>{firstName ? `Привет, ${firstName}!` : 'Привет!'}</h1>
            <div className="subtitle">Я — Ева, рада знакомству</div>
          </div>
          {themeToggle}
        </div>

        {affirmation && (
          <div className="section">
            <div className="section-card">
              <div className="affirmation-card">
                <span className="affirmation-card__icon">✨</span>
                <p className="affirmation-card__text">{affirmation.text}</p>
              </div>
            </div>
          </div>
        )}

        <button className="btn-primary" onClick={handleOpenChat}>
          Написать Еве →
        </button>
        <div className="btn-hint">Откроется чат с Евой</div>
      </>
    );
  }

  // ===== ACTIVE USER =====
  return (
    <>
      <div className="page-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>{firstName ? `Привет, ${firstName}!` : 'Привет!'}</h1>
          <div className="subtitle">
            {streak > 0 ? `🔥 ${streak} дней подряд` : 'Рада тебя видеть!'}
          </div>
        </div>
        {themeToggle}
      </div>

      {/* Аффирмация */}
      {affirmation && (
        <div className="section">
          <div className="section-card">
            <div className="affirmation-card">
              <span className="affirmation-card__icon">✨</span>
              <p className="affirmation-card__text">{affirmation.text}</p>
            </div>
          </div>
        </div>
      )}

      {/* Задания на сегодня */}
      {todaySteps && todaySteps.steps.length > 0 ? (
        <div className="section">
          <div className="section-header">Задания на сегодня</div>
          <div className="section-card">
            {todaySteps.steps.map((step) => (
              <div key={step.id}>
                <div
                  className="cell cell--tappable"
                  onClick={() => handleToggleStep(step)}
                >
                  <span className="cell-icon">
                    {step.status === 'done' ? '✅' : '○'}
                  </span>
                  <div className="cell-body">
                    <div
                      className="cell-title"
                      style={step.status === 'done' ? { textDecoration: 'line-through', color: 'var(--text-secondary)' } : undefined}
                    >
                      {step.title}
                    </div>
                  </div>
                </div>
                {stepErrors[step.id] && (
                  <div className="step-error">{stepErrors[step.id]}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : todaySteps && todaySteps.steps.length === 0 ? (
        <div className="section">
          <div className="section-header">Задания на сегодня</div>
          <div className="section-card">
            <div className="placeholder">
              <div className="placeholder__emoji">☀️</div>
              <div className="placeholder__text">Свободный день</div>
            </div>
          </div>
        </div>
      ) : null}

      <button className="btn-primary" onClick={handleOpenChat}>
        Написать Еве →
      </button>
      <div className="btn-hint">Откроется чат с Евой</div>
    </>
  );
}
