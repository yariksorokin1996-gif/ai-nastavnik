import { useState } from 'react';
import { Lock, ChevronRight } from 'lucide-react';
import './AstroPage.css';

export function AstroPage() {
  const [cardRevealed, setCardRevealed] = useState(false);

  const handleReveal = () => {
    setCardRevealed(true);
    if (window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
    }
  };

  return (
    <div className="scroll-area">
      <h1 className="heading-lg animate-in" style={{ marginBottom: 'var(--space-7)' }}>
        Твоё звёздное пространство 🌙
      </h1>

      {/* Карта дня */}
      <section className="astro-section animate-in" style={{ animationDelay: '50ms' }}>
        <div
          className={`tarot-main ${cardRevealed ? 'tarot-main--revealed' : ''}`}
          onClick={!cardRevealed ? handleReveal : undefined}
        >
          {!cardRevealed ? (
            <div className="tarot-back">
              <div className="tarot-back__pattern">✦</div>
              <p className="body-md" style={{ color: 'var(--primary-300)' }}>
                Нажми, чтобы открыть
              </p>
            </div>
          ) : (
            <div className="tarot-front">
              <span className="tarot-front__emoji">👑</span>
              <h3 className="heading-md">Императрица</h3>
              <p className="body-md" style={{ color: 'var(--text-secondary)', marginTop: 12 }}>
                Императрица говорит о внутренней силе и решительности.
                Сегодня ты способна на большее, чем думаешь.
              </p>
            </div>
          )}
        </div>
      </section>

      {/* Аффирмация */}
      <section className="astro-section animate-in" style={{ animationDelay: '100ms' }}>
        <div className="card-accent affirmation">
          <span className="affirmation__label label-md">✨ Аффирмация дня</span>
          <p className="body-lg" style={{ marginTop: 8, fontStyle: 'italic' }}>
            «Я заслуживаю лучшего и не боюсь за это бороться»
          </p>
        </div>
      </section>

      {/* Мини-гороскоп */}
      <section className="astro-section animate-in" style={{ animationDelay: '150ms' }}>
        <div className="card">
          <span className="label-md" style={{ color: 'var(--primary-400)' }}>🌙 Мини-гороскоп</span>
          <p className="body-md" style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
            Пройди онбординг и введи дату рождения, чтобы получить
            персональный гороскоп
          </p>
        </div>
      </section>

      {/* Платные функции */}
      <section className="astro-section animate-in" style={{ animationDelay: '200ms' }}>
        {[
          { icon: '🔮', label: 'Полный расклад', desc: 'Подробное чтение карт на ситуацию' },
          { icon: '💑', label: 'Совместимость', desc: 'Анализ отношений по датам рождения' },
          { icon: '📅', label: 'Прогноз на месяц', desc: 'Персональный прогноз с рекомендациями' },
        ].map((item) => (
          <div key={item.label} className="card premium-item">
            <div className="premium-item__left">
              <span className="premium-item__icon">{item.icon}</span>
              <div>
                <p className="label-lg">{item.label}</p>
                <p className="body-sm" style={{ color: 'var(--text-secondary)' }}>{item.desc}</p>
              </div>
            </div>
            <Lock size={16} color="var(--text-disabled)" />
          </div>
        ))}
      </section>

      {/* Архив */}
      <section className="astro-section animate-in" style={{ animationDelay: '250ms' }}>
        <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="label-lg">📜 Архив карт</span>
            <p className="body-sm" style={{ color: 'var(--text-secondary)', marginTop: 4 }}>
              История твоих карт дня
            </p>
          </div>
          <ChevronRight size={20} color="var(--text-disabled)" />
        </div>
      </section>
    </div>
  );
}
