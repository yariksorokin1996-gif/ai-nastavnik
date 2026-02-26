import { GoalCard } from '../components/GoalCard';
import { useUser } from '../hooks/useUser';
import './ProgressPage.css';

const PHASE_LABELS: Record<string, string> = {
  onboarding: 'Знакомство',
  diagnosis: 'Диагностика',
  goal: 'Постановка цели',
  planning: 'Составление плана',
  daily: 'Ежедневная работа',
};

const PHASE_PROGRESS: Record<string, number> = {
  onboarding: 0,
  diagnosis: 10,
  goal: 25,
  planning: 40,
  daily: 60,
};

export function ProgressPage() {
  const { user } = useUser();
  const phase = user?.phase || 'onboarding';
  const hasGoal = !!user?.goal;

  return (
    <div className="scroll-area">
      <h1 className="heading-lg animate-in" style={{ marginBottom: 'var(--space-7)' }}>
        Мой путь
      </h1>

      {/* Цели */}
      <section className="progress-section animate-in" style={{ animationDelay: '50ms' }}>
        <div className="goals-list">
          {hasGoal ? (
            <GoalCard
              icon="🎯"
              sphere={user?.area || 'Общая'}
              title={user?.goal || ''}
              progress={PHASE_PROGRESS[phase] || 0}
              currentStep={PHASE_LABELS[phase] || phase}
            />
          ) : (
            <>
              <GoalCard
                icon="✨"
                sphere="Самореализация"
                title="Цель будет определена в процессе"
                progress={PHASE_PROGRESS[phase] || 0}
                currentStep={PHASE_LABELS[phase] || 'Ожидает постановки цели'}
              />
              <GoalCard
                icon="💰"
                sphere="Деньги"
                title="Цель будет определена в процессе"
                progress={0}
                currentStep="Ожидает постановки цели"
              />
            </>
          )}
        </div>
      </section>

      {/* Календарь */}
      <section className="progress-section animate-in" style={{ animationDelay: '100ms' }}>
        <h2 className="heading-sm section-title">Февраль</h2>
        <div className="calendar-grid">
          {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((d) => (
            <span key={d} className="calendar-header">{d}</span>
          ))}
          {Array.from({ length: 28 }, (_, i) => {
            const dayNum = i + 1;
            const today = new Date().getDate();
            const isDone = dayNum < today && (user?.sessions_count || 0) > 0;
            const isToday = dayNum === today;
            return (
              <span
                key={i}
                className={`calendar-day ${isDone ? 'calendar-day--done' : ''} ${isToday ? 'calendar-day--today' : ''}`}
              >
                {dayNum}
              </span>
            );
          })}
        </div>
        <div className="streak-info">
          <span>Серия: {Math.max(user?.sessions_count || 0, 1)} день 🔥</span>
          <span>Сессий: {user?.sessions_count || 0}</span>
        </div>
      </section>

      {/* Недельный отчёт */}
      <section className="progress-section animate-in" style={{ animationDelay: '150ms' }}>
        <h2 className="heading-sm section-title">Недельный отчёт</h2>
        <div className="card">
          <p className="body-md" style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>
            {(user?.sessions_count || 0) >= 7
              ? 'Отчёт формируется...'
              : 'Пока недостаточно данных.\nОбщайся с наставником — отчёт появится через неделю'}
          </p>
        </div>
      </section>
    </div>
  );
}
