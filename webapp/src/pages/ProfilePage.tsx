import { useState, useCallback } from 'react';
import { deleteAccount } from '../api';
import type { UserState } from '../hooks/useUser';

const BOT_USERNAME = import.meta.env.VITE_BOT_USERNAME || 'eva_nastavnik_bot';

interface ProfilePageProps {
  userState: UserState;
}

export function ProfilePage({ userState }: ProfilePageProps) {
  const { user, loading, error, retry } = userState;
  const tg = window.Telegram?.WebApp;
  const tgUser = tg?.initDataUnsafe?.user;

  const [showAbout, setShowAbout] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState<'idle' | 'deleting' | 'done'>('idle');

  const handleForgetTopic = useCallback(() => {
    if (tg) {
      tg.openTelegramLink(`https://t.me/${BOT_USERNAME}?start=forget`);
    }
  }, [tg]);

  const handleDeleteAccount = useCallback(async () => {
    const confirmed = window.confirm(
      'Все данные будут удалены. Это действие нельзя отменить. Продолжить?',
    );
    if (!confirmed) return;

    setDeleteStatus('deleting');
    try {
      await deleteAccount();
      setDeleteStatus('done');
      setTimeout(() => {
        tg?.close();
      }, 2000);
    } catch {
      setDeleteStatus('idle');
      tg?.HapticFeedback?.notificationOccurred('error');
    }
  }, [tg]);

  const handleHelp = useCallback(() => {
    if (tg) {
      tg.openTelegramLink(`https://t.me/${BOT_USERNAME}?start=help`);
    }
  }, [tg]);

  // Loading
  if (loading) {
    return (
      <div className="skeleton-page">
        <div className="skeleton" style={{ width: 96, height: 96, borderRadius: '50%', margin: '20px auto 8px' }} />
        <div className="skeleton skeleton-title" style={{ width: '40%', margin: '0 auto 8px' }} />
        <div className="skeleton skeleton-subtitle" style={{ width: '50%', margin: '0 auto' }} />
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

  // Delete done
  if (deleteStatus === 'done') {
    return (
      <div className="error-state">
        <div className="error-state__emoji">👋</div>
        <div className="error-state__text">Готово, все данные удалены</div>
      </div>
    );
  }

  const name = tgUser?.first_name || user?.name || 'Гость';
  const photoUrl = tgUser?.photo_url;

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
          Сессий: {user?.sessions_count || 0}
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
            <span className="badge-soon">Скоро</span>
          </div>
          <div className="cell">
            <span className="cell-icon">🔔</span>
            <div className="cell-body">
              <div className="cell-title">Напоминания</div>
            </div>
            <span className="badge-soon">Скоро</span>
          </div>
        </div>
      </div>

      {/* Действия */}
      <div className="section">
        <div className="section-header">Действия</div>
        <div className="section-card">
          <div className="cell cell--tappable" onClick={handleForgetTopic}>
            <span className="cell-icon">🗑</span>
            <div className="cell-body">
              <div className="cell-title">Забудь тему...</div>
            </div>
            <span className="cell-chevron">›</span>
          </div>
          <div
            className="cell cell--tappable"
            onClick={handleDeleteAccount}
            style={deleteStatus === 'deleting' ? { opacity: 0.5, pointerEvents: 'none' } : undefined}
          >
            <span className="cell-icon">❌</span>
            <div className="cell-body">
              <div className="cell-title" style={{ color: 'var(--tg-theme-destructive-text-color, #FF3B30)' }}>
                {deleteStatus === 'deleting' ? 'Удаляю...' : 'Удалить аккаунт'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Ещё */}
      <div className="section">
        <div className="section-header">Ещё</div>
        <div className="section-card">
          <div className="cell cell--tappable" onClick={() => setShowAbout(true)}>
            <span className="cell-icon">ℹ️</span>
            <div className="cell-body">
              <div className="cell-title">О Еве</div>
            </div>
            <span className="cell-chevron">›</span>
          </div>
          <div className="cell cell--tappable" onClick={handleHelp}>
            <span className="cell-icon">❓</span>
            <div className="cell-body">
              <div className="cell-title">Помощь</div>
            </div>
            <span className="cell-chevron">›</span>
          </div>
        </div>
      </div>

      {/* About overlay */}
      {showAbout && (
        <div className="overlay" onClick={() => setShowAbout(false)}>
          <div className="overlay__card" onClick={(e) => e.stopPropagation()}>
            <div className="overlay__title">О Еве</div>
            <p className="overlay__text">
              Ева — AI-подруга. Она не заменяет психолога, психотерапевта или врача.
              Если тебе тяжело — обратись к специалисту или позвони на горячую линию:
            </p>
            <p className="overlay__text" style={{ fontWeight: 600 }}>
              8-800-2000-122 (бесплатно, 24/7)
            </p>
            <button className="btn-primary" style={{ marginTop: 16 }} onClick={() => setShowAbout(false)}>
              Понятно
            </button>
          </div>
        </div>
      )}
    </>
  );
}
