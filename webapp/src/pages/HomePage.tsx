import { useState, useEffect } from 'react';
import { Section, Cell, Button, Text, Title, Caption, Progress, Placeholder } from '@telegram-apps/telegram-ui';
import { fetchDaily, type DailyData } from '../api';
import { useUser } from '../hooks/useUser';

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

const PHASE_PROGRESS: Record<string, number> = {
  onboarding: 5,
  diagnosis: 15,
  goal: 30,
  planning: 50,
  daily: 70,
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
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
  };

  const handleOpenChat = () => {
    window.Telegram?.WebApp?.close();
  };

  const firstName = user?.name || window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || 'Привет';
  const streak = daily?.streak || 0;
  const sessionsCount = daily?.sessions_count || user?.sessions_count || 0;
  const phase = user?.phase || 'onboarding';

  return (
    <>
      <div className="page-title">
        <Title level="1" weight="1">Привет, {firstName}!</Title>
        <Caption style={{ color: '#8E8E93', marginTop: 4 }}>
          День {sessionsCount || 1} · Серия: {streak || 1} 🔥
        </Caption>
      </div>

      {/* Карта дня */}
      <div style={{ padding: '0 16px 16px' }}>
        <div className="tarot-card">
          <div className="tarot-card__emoji">🃏</div>
          <Text weight="2">Карта дня</Text>
          <Caption style={{ color: '#8E8E93', marginTop: 4 }}>
            {phase === 'onboarding'
              ? 'Пройди онбординг для первой карты'
              : 'Нажми, чтобы получить расклад'}
          </Caption>
        </div>
      </div>

      {/* Задание дня */}
      <Section header="Задание дня">
        {daily?.commitments && daily.commitments.length > 0 ? (
          daily.commitments.map((c, i) => (
            <Cell
              key={i}
              before={<span className="cell-emoji">☐</span>}
              subtitle={c.deadline ? `До: ${c.deadline}` : undefined}
              multiline
            >
              {c.action}
            </Cell>
          ))
        ) : (
          <Cell before={<span className="cell-emoji">☐</span>} multiline>
            Начни общение с наставником
          </Cell>
        )}
      </Section>

      {/* Режим общения */}
      <Section header="Режим общения">
        <div className="modes-grid" style={{ paddingTop: 8, paddingBottom: 16 }}>
          {MODES.map((mode) => (
            <div
              key={mode.id}
              className={`mode-item ${activeMode === mode.id ? 'mode-item--active' : ''}`}
              onClick={() => handleModeSelect(mode.id)}
            >
              <span className="mode-item__icon">{mode.icon}</span>
              <span className="mode-item__label">{mode.label}</span>
              <span className="mode-item__desc">{mode.description}</span>
            </div>
          ))}
        </div>
      </Section>

      {/* Мои цели */}
      <Section header="Мои цели">
        {user?.goal ? (
          <Cell
            before={<span className="cell-emoji">🎯</span>}
            subtitle={PHASE_LABELS[phase] || phase}
            after={<Caption style={{ color: '#007AFF' }}>{PHASE_PROGRESS[phase] || 0}%</Caption>}
            multiline
          >
            {user.goal}
            <div className="cell-progress">
              <Progress value={PHASE_PROGRESS[phase] || 0} />
            </div>
          </Cell>
        ) : (
          <Placeholder description={`Фаза: ${PHASE_LABELS[phase] || phase}\nЧерез пару дней предложу цели`}>
            💬
          </Placeholder>
        )}
      </Section>

      {/* CTA */}
      <div style={{ padding: '8px 16px 24px' }}>
        <Button size="l" stretched onClick={handleOpenChat}>
          Перейти в чат →
        </Button>
      </div>
    </>
  );
}
