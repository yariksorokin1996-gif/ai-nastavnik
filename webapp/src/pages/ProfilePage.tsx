import { ChevronRight, Clock, Moon, Bell, MapPin } from 'lucide-react';
import { useUser } from '../hooks/useUser';
import { updateStyle } from '../api';
import './ProfilePage.css';

const STYLE_NAMES: Record<number, string> = {
  1: '🌿 Мягкий',
  2: '⚖️ Сбалансированный',
  3: '🔥 Жёсткий',
};

export function ProfilePage() {
  const tg = window.Telegram?.WebApp;
  const tgUser = tg?.initDataUnsafe?.user;
  const { user, setUser } = useUser();

  const handleStyleChange = async () => {
    if (!user) return;
    const nextStyle = (user.coaching_style % 3) + 1;
    try {
      await updateStyle(nextStyle);
      setUser({ ...user, coaching_style: nextStyle });
      tg?.HapticFeedback?.notificationOccurred('success');
    } catch {
      tg?.HapticFeedback?.notificationOccurred('error');
    }
  };

  return (
    <div className="scroll-area">
      {/* Профиль */}
      <div className="profile-header animate-in">
        <div className="profile-avatar">
          {tgUser?.photo_url ? (
            <img src={tgUser.photo_url} alt="" className="profile-avatar__img" />
          ) : (
            <span className="profile-avatar__fallback">
              {tgUser?.first_name?.[0] || user?.name?.[0] || '?'}
            </span>
          )}
        </div>
        <h1 className="heading-lg">{tgUser?.first_name || user?.name || 'Гость'}</h1>
        <p className="body-md" style={{ color: 'var(--text-secondary)' }}>
          Сессий: {user?.sessions_count || 0} · {user?.is_premium ? 'Про' : 'Бесплатно'}
        </p>
      </div>

      {/* Стиль коучинга */}
      <section className="profile-section animate-in" style={{ animationDelay: '50ms' }}>
        <div className="card settings-item" onClick={handleStyleChange} style={{ cursor: 'pointer' }}>
          <div className="settings-item__left">
            <span className="label-lg">Стиль наставника</span>
          </div>
          <div className="settings-item__right">
            <span className="body-sm" style={{ color: 'var(--text-secondary)' }}>
              {STYLE_NAMES[user?.coaching_style || 2]}
            </span>
            <ChevronRight size={16} color="var(--text-disabled)" />
          </div>
        </div>
      </section>

      {/* Подписка */}
      <section className="profile-section animate-in" style={{ animationDelay: '100ms' }}>
        <div className="card-accent subscription-card">
          <div className="subscription-card__header">
            <span className="label-lg">Подписка</span>
            <span className="subscription-badge">{user?.is_premium ? 'Про' : 'Бесплатно'}</span>
          </div>
          <p className="body-sm" style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
            Открой полный доступ ко всем режимам и функциям
          </p>
          {!user?.is_premium && (
            <button className="btn-primary" style={{ marginTop: 16 }}>
              Оформить подписку ⭐
            </button>
          )}
        </div>
      </section>

      {/* Настройки */}
      <section className="profile-section animate-in" style={{ animationDelay: '150ms' }}>
        <h2 className="heading-sm section-title">Настройки</h2>
        <div className="settings-list">
          {[
            { icon: <Clock size={20} />, label: 'Утреннее сообщение', value: '08:00' },
            { icon: <Moon size={20} />, label: 'Вечерний чек-ин', value: '21:00' },
            { icon: <Bell size={20} />, label: 'Напоминания', value: 'Включены' },
            { icon: <MapPin size={20} />, label: 'Часовой пояс', value: 'Авто' },
          ].map((item) => (
            <div key={item.label} className="settings-item card">
              <div className="settings-item__left">
                <span className="settings-item__icon">{item.icon}</span>
                <span className="label-lg">{item.label}</span>
              </div>
              <div className="settings-item__right">
                <span className="body-sm" style={{ color: 'var(--text-secondary)' }}>{item.value}</span>
                <ChevronRight size={16} color="var(--text-disabled)" />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Прочее */}
      <section className="profile-section animate-in" style={{ animationDelay: '200ms' }}>
        {[
          { label: '📜 История платежей' },
          { label: '✏️ Редактировать данные' },
          { label: '❓ Помощь' },
        ].map((item) => (
          <div key={item.label} className="card settings-item" style={{ marginBottom: 'var(--space-3)' }}>
            <span className="label-lg">{item.label}</span>
            <ChevronRight size={16} color="var(--text-disabled)" />
          </div>
        ))}
      </section>
    </div>
  );
}
