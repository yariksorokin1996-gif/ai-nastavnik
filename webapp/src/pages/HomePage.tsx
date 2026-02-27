import { useState, useEffect } from 'react';
import { fetchDaily, type DailyData } from '../api';
import type { UserState } from '../hooks/useUser';

interface HomePageProps {
  userState: UserState;
}

export function HomePage({ userState }: HomePageProps) {
  const { user, loading, error, retry } = userState;
  const [daily, setDaily] = useState<DailyData | null>(null);
  const [cardRevealed, setCardRevealed] = useState(false);
  const [currentTaskIndex, setCurrentTaskIndex] = useState(0);

  useEffect(() => {
    fetchDaily().then(setDaily).catch(() => {});
  }, []);

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
        <div className="error-state__text">Не удалось загрузить данные</div>
        <button className="error-state__btn" onClick={retry}>Повторить</button>
      </div>
    );
  }

  const firstName = user?.name || window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || '';
  const streak = daily?.streak || 0;
  const sessionsCount = daily?.sessions_count || user?.sessions_count || 0;
  const isNewUser = sessionsCount === 0;

  const commitments = daily?.commitments || user?.commitments || [];
  const currentTask = commitments[currentTaskIndex];

  const handleOpenChat = () => {
    window.Telegram?.WebApp?.close();
  };

  const handleTaskDone = () => {
    window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('success');
    if (currentTaskIndex < commitments.length - 1) {
      setCurrentTaskIndex(currentTaskIndex + 1);
    } else {
      setCurrentTaskIndex(commitments.length); // all done
    }
  };

  // ===== NEW USER =====
  if (isNewUser) {
    return (
      <>
        <div className="page-title">
          <h1>{firstName ? `Привет, ${firstName}!` : 'Привет!'}</h1>
          <div className="subtitle">Я — твой AI-наставник. Помогу разобраться в себе и достичь целей</div>
        </div>

        {/* Карта дня — первый интерактив */}
        <div
          className="feature-card"
          onClick={() => !cardRevealed && setCardRevealed(true)}
          style={cardRevealed ? { cursor: 'default' } : {}}
        >
          {!cardRevealed ? (
            <>
              <div className="feature-card__emoji">✦</div>
              <div className="feature-card__title">Карта дня</div>
              <div className="feature-card__desc">Нажми, чтобы открыть</div>
            </>
          ) : (
            <>
              <div className="feature-card__emoji">👑</div>
              <div className="feature-card__title">Императрица</div>
              <div className="feature-card__desc">
                Императрица говорит о внутренней силе и решительности.
                Сегодня ты способна на большее, чем думаешь.
              </div>
            </>
          )}
        </div>

        <button className="btn-primary" onClick={handleOpenChat}>
          Начать знакомство →
        </button>
        <div className="btn-hint">Откроется чат с наставником</div>
      </>
    );
  }

  // ===== ACTIVE USER =====
  return (
    <>
      <div className="page-title">
        <h1>Привет, {firstName}!</h1>
        <div className="subtitle">
          {streak > 1 ? `Серия: ${streak} дней · Ты молодец!` : 'Рада тебя видеть!'}
        </div>
      </div>

      {/* Мысль дня */}
      {daily?.recent_patterns && daily.recent_patterns.length > 0 && daily.recent_patterns[0].pattern_text ? (
        <div className="section">
          <div className="section-header">Мысль дня</div>
          <div className="section-card">
            <div className="cell">
              <span className="cell-icon">✨</span>
              <div className="cell-body">
                <div className="cell-title" style={{ fontStyle: 'italic', fontSize: 15 }}>
                  «{daily.recent_patterns[0].pattern_text}»
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="feature-card" onClick={() => !cardRevealed && setCardRevealed(true)} style={cardRevealed ? { cursor: 'default' } : {}}>
          {!cardRevealed ? (
            <>
              <div className="feature-card__emoji">✦</div>
              <div className="feature-card__title">Карта дня</div>
              <div className="feature-card__desc">Нажми, чтобы открыть</div>
            </>
          ) : (
            <>
              <div className="feature-card__emoji">👑</div>
              <div className="feature-card__title">Императрица</div>
              <div className="feature-card__desc">
                Императрица говорит о внутренней силе и решительности.
                Сегодня ты способна на большее, чем думаешь.
              </div>
            </>
          )}
        </div>
      )}

      {/* Текущее задание — ОДНО */}
      <div className="section">
        <div className="section-header">Задание</div>
        <div className="section-card">
          {currentTask && currentTaskIndex < commitments.length ? (
            <div className="cell" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span className="cell-icon">🎯</span>
                <div className="cell-body">
                  <div className="cell-title">{currentTask.action}</div>
                  {currentTask.deadline && (
                    <div className="cell-subtitle">До: {currentTask.deadline}</div>
                  )}
                </div>
              </div>
              <button
                className="btn-primary"
                style={{ margin: 0, width: '100%' }}
                onClick={handleTaskDone}
              >
                Выполнено ✓
              </button>
            </div>
          ) : commitments.length > 0 ? (
            <div className="placeholder">
              <div className="placeholder__emoji">🎉</div>
              <div className="placeholder__text">Все задания на сегодня выполнены!</div>
            </div>
          ) : (
            <div className="placeholder">
              <div className="placeholder__emoji">💬</div>
              <div className="placeholder__text">Задание появится после разговора с наставником</div>
            </div>
          )}
        </div>
      </div>

      <button className="btn-primary" onClick={handleOpenChat}>
        Написать наставнику →
      </button>
      <div className="btn-hint">Откроется чат с наставником</div>
    </>
  );
}
