import { useState, useEffect } from 'react';
import { Flame } from 'lucide-react';
import { ModeCard } from '../components/ModeCard';
import { GoalCard } from '../components/GoalCard';
import { fetchDaily, type DailyData } from '../api';
import { useUser } from '../hooks/useUser';
import './HomePage.css';

const MODES = [
  { id: 'astrologer', icon: '🔮', label: 'Астролог', description: 'Расклады и прогнозы' },
  { id: 'coach', icon: '🧠', label: 'Коуч', description: 'Разборы и задания' },
  { id: 'friend', icon: '👩', label: 'Подруга', description: 'Поболтать, поддержка' },
];

const PHASE_LABELS: Record<string, string> = {
  onboarding: 'Знакомство',
  diagnosis: 'Диагностика',
  goal: 'Постановка цели',
  planning: 'Составление плана',
  daily: 'Ежедневная работа',
};

export function HomePage() {
  const { user } = useUser();
  const [activeMode, setActiveMode] = useState('astrologer');
  const [daily, setDaily] = useState<DailyData | null>(null);

  useEffect(() => {
    fetchDaily().then(setDaily).catch(() => {});
  }, []);

  const handleModeSelect = (modeId: string) => {
    setActiveMode(modeId);
    if (window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.selectionChanged();
    }
  };

  const handleOpenChat = () => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.close();
    }
  };

  const firstName = user?.name || window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || 'Привет';
  const streak = daily?.streak || 0;
  const sessionsCount = daily?.sessions_count || user?.sessions_count || 0;
  const phase = user?.phase || 'onboarding';
  const hasGoal = !!user?.goal;

  return (
    <div className="scroll-area">
      {/* Приветствие */}
      <div className="home-header animate-in">
        <h1 className="heading-lg">{firstName}! ✨</h1>
        <div className="home-streak">
          <Flame size={16} color="#F59E0B" />
          <span>День {sessionsCount || 1} · Серия: {streak || 1}</span>
        </div>
      </div>

      {/* Карта дня */}
      <section className="home-section animate-in" style={{ animationDelay: '50ms' }}>
        <div className="card-accent tarot-card">
          <div className="tarot-card__emoji">🃏</div>
          <h3 className="heading-sm">Карта дня</h3>
          <p className="body-md" style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
            {phase === 'onboarding'
              ? 'Пройди онбординг, чтобы получить свою первую карту'
              : 'Нажми, чтобы получить расклад на сегодня'}
          </p>
        </div>
      </section>

      {/* Задание дня */}
      {daily?.commitments && daily.commitments.length > 0 ? (
        <section className="home-section animate-in" style={{ animationDelay: '100ms' }}>
          <h2 className="heading-sm section-title">Задание дня</h2>
          {daily.commitments.map((c, i) => (
            <div key={i} className="card task-card">
              <div className="task-card__check">◻</div>
              <div>
                <p className="body-md">{c.action}</p>
                {c.deadline && (
                  <p className="body-sm" style={{ color: 'var(--text-secondary)' }}>До: {c.deadline}</p>
                )}
              </div>
            </div>
          ))}
        </section>
      ) : (
        <section className="home-section animate-in" style={{ animationDelay: '100ms' }}>
          <h2 className="heading-sm section-title">Задание дня</h2>
          <div className="card task-card">
            <div className="task-card__check">◻</div>
            <p className="body-md">Начни общение с наставником в любом режиме</p>
          </div>
        </section>
      )}

      {/* Режим общения */}
      <section className="home-section animate-in" style={{ animationDelay: '150ms' }}>
        <h2 className="heading-sm section-title">Режим общения</h2>
        <div className="modes-grid">
          {MODES.map((mode) => (
            <ModeCard
              key={mode.id}
              icon={mode.icon}
              label={mode.label}
              description={mode.description}
              isActive={activeMode === mode.id}
              onClick={() => handleModeSelect(mode.id)}
            />
          ))}
        </div>
      </section>

      {/* Мои цели */}
      <section className="home-section animate-in" style={{ animationDelay: '200ms' }}>
        <h2 className="heading-sm section-title">Мои цели</h2>
        {hasGoal ? (
          <GoalCard
            icon="🎯"
            sphere={user?.area || 'Общая'}
            title={user?.goal || ''}
            progress={phase === 'daily' ? 30 : phase === 'planning' ? 15 : 5}
            currentStep={PHASE_LABELS[phase] || phase}
          />
        ) : (
          <div className="goals-placeholder card">
            <p className="body-md" style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>
              💬 {phase === 'onboarding' ? 'Мы знакомимся...' : `Фаза: ${PHASE_LABELS[phase] || phase}`}<br />
              Через пару дней я предложу твои цели
            </p>
          </div>
        )}
      </section>

      {/* MainButton — переход в чат */}
      <div className="home-cta">
        <button className="btn-primary" onClick={handleOpenChat}>
          Перейти в чат →
        </button>
      </div>
    </div>
  );
}
