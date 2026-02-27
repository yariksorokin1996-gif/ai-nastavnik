import { useUser } from '../hooks/useUser';
import { updateStyle } from '../api';

const MODES = [
  { id: 'astrologer', icon: '🔮', label: 'Астролог' },
  { id: 'coach', icon: '🧠', label: 'Коуч' },
  { id: 'friend', icon: '👩', label: 'Подруга' },
];

const STYLE_NAMES: Record<number, string> = {
  1: '🌿 Мягкий',
  2: '⚖️ Сбалансированный',
  3: '🔥 Жёсткий',
};

export function ProfilePage() {
  const tg = window.Telegram?.WebApp;
  const tgUser = tg?.initDataUnsafe?.user;
  const { user, setUser } = useUser();

  const name = tgUser?.first_name || user?.name || 'Гость';
  const photoUrl = tgUser?.photo_url;
  const currentMode = user?.mode || 'astrologer';

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

  const handleModeSelect = (modeId: string) => {
    if (!user) return;
    setUser({ ...user, mode: modeId });
    tg?.HapticFeedback?.selectionChanged();
  };

  return (
    <>
      {/* Профиль */}
      <div className="profile-header">
        <div className="profile-avatar">
          {photoUrl ? (
            <img src={photoUrl} alt={name} />
          ) : (
            name[0]
          )}
        </div>
        <div className="profile-name">{name}</div>
        <div className="profile-meta">
          Сессий: {user?.sessions_count || 0} · {user?.is_premium ? 'Про' : 'Базовый план'}
        </div>
      </div>

      {/* Подписка — только если не премиум */}
      {!user?.is_premium && (
        <div className="sub-banner">
          <h3>Полный доступ</h3>
          <p>Все режимы общения, расклады, персональные прогнозы и безлимитные сессии</p>
          <button>Оформить подписку ⭐</button>
        </div>
      )}

      {/* Наставник — режим */}
      <div className="section">
        <div className="section-header">Режим общения</div>
        <div className="modes-grid">
          {MODES.map((mode) => (
            <div
              key={mode.id}
              className={`mode-item ${currentMode === mode.id ? 'mode-item--active' : ''}`}
              onClick={() => handleModeSelect(mode.id)}
            >
              <span className="mode-item__icon">{mode.icon}</span>
              <span className="mode-item__label">{mode.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Наставник — стиль */}
      <div className="section">
        <div className="section-header">Наставник</div>
        <div className="section-card">
          <div className="cell" onClick={handleStyleChange} style={{ cursor: 'pointer' }}>
            <span className="cell-icon">🎯</span>
            <div className="cell-body">
              <div className="cell-title">Стиль коучинга</div>
            </div>
            <span className="cell-after">{STYLE_NAMES[user?.coaching_style || 2]}</span>
          </div>
        </div>
      </div>

      {/* Настройки */}
      <div className="section">
        <div className="section-header">Настройки</div>
        <div className="section-card">
          <div className="cell">
            <span className="cell-icon">⏰</span>
            <div className="cell-body">
              <div className="cell-title">Утреннее сообщение</div>
            </div>
            <span className="cell-after">08:00</span>
          </div>
          <div className="cell">
            <span className="cell-icon">🌙</span>
            <div className="cell-body">
              <div className="cell-title">Вечерний чек-ин</div>
            </div>
            <span className="cell-after">21:00</span>
          </div>
          <div className="cell">
            <span className="cell-icon">🔔</span>
            <div className="cell-body">
              <div className="cell-title">Напоминания</div>
            </div>
            <span className="cell-after">Включены</span>
          </div>
        </div>
      </div>

      {/* Ещё */}
      <div className="section">
        <div className="section-header">Ещё</div>
        <div className="section-card">
          <div className="cell">
            <span className="cell-icon">📜</span>
            <div className="cell-body">
              <div className="cell-title">История платежей</div>
            </div>
            <span className="cell-chevron">›</span>
          </div>
          <div className="cell">
            <span className="cell-icon">❓</span>
            <div className="cell-body">
              <div className="cell-title">Помощь</div>
            </div>
            <span className="cell-chevron">›</span>
          </div>
        </div>
      </div>
    </>
  );
}
