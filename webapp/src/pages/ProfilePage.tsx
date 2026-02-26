import { Section, Cell, Avatar, Title, Caption, Text, Button } from '@telegram-apps/telegram-ui';
import { useUser } from '../hooks/useUser';
import { updateStyle } from '../api';

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

  const name = tgUser?.first_name || user?.name || 'Гость';
  const photoUrl = tgUser?.photo_url;

  return (
    <>
      {/* Профиль */}
      <div className="profile-header">
        <Avatar
          size={72}
          src={photoUrl}
          acronym={name[0]}
        />
        <Title level="2" weight="1">{name}</Title>
        <Caption style={{ color: 'var(--tg-theme-hint-color)' }}>
          Сессий: {user?.sessions_count || 0} · {user?.is_premium ? 'Про' : 'Бесплатно'}
        </Caption>
      </div>

      {/* Подписка */}
      {!user?.is_premium && (
        <div className="sub-banner">
          <h3>Подписка</h3>
          <p>Открой полный доступ ко всем режимам и функциям</p>
          <button>Оформить подписку ⭐</button>
        </div>
      )}

      {/* Стиль */}
      <Section header="Наставник">
        <Cell
          before={<span className="cell-emoji">🎯</span>}
          after={<Caption>{STYLE_NAMES[user?.coaching_style || 2]}</Caption>}
          onClick={handleStyleChange}
        >
          Стиль коучинга
        </Cell>
      </Section>

      {/* Настройки */}
      <Section header="Настройки">
        <Cell
          before={<span className="cell-emoji">⏰</span>}
          after={<Caption>08:00</Caption>}
        >
          Утреннее сообщение
        </Cell>
        <Cell
          before={<span className="cell-emoji">🌙</span>}
          after={<Caption>21:00</Caption>}
        >
          Вечерний чек-ин
        </Cell>
        <Cell
          before={<span className="cell-emoji">🔔</span>}
          after={<Caption>Включены</Caption>}
        >
          Напоминания
        </Cell>
        <Cell
          before={<span className="cell-emoji">📍</span>}
          after={<Caption>Авто</Caption>}
        >
          Часовой пояс
        </Cell>
      </Section>

      {/* Прочее */}
      <Section header="Ещё">
        <Cell before={<span className="cell-emoji">📜</span>}>
          История платежей
        </Cell>
        <Cell before={<span className="cell-emoji">✏️</span>}>
          Редактировать данные
        </Cell>
        <Cell before={<span className="cell-emoji">❓</span>}>
          Помощь
        </Cell>
      </Section>
    </>
  );
}
