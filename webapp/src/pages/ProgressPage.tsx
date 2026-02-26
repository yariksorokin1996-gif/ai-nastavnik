import { Section, Cell, Title, Caption, Text, Progress, Placeholder } from '@telegram-apps/telegram-ui';
import { useUser } from '../hooks/useUser';

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

  const today = new Date().getDate();
  const sessionsCount = user?.sessions_count || 0;

  return (
    <>
      <div className="page-title">
        <Title level="1" weight="1">Мой путь</Title>
      </div>

      {/* Цели */}
      <Section header="Цели">
        {user?.goal ? (
          <Cell
            before={<span className="cell-emoji">🎯</span>}
            subtitle={PHASE_LABELS[phase] || phase}
            after={<Caption>{PHASE_PROGRESS[phase] || 0}%</Caption>}
            multiline
          >
            {user.goal}
            <div className="cell-progress">
              <Progress value={PHASE_PROGRESS[phase] || 0} />
            </div>
          </Cell>
        ) : (
          <>
            <Cell
              before={<span className="cell-emoji">✨</span>}
              subtitle={PHASE_LABELS[phase] || 'Ожидает постановки'}
              after={<Caption>{PHASE_PROGRESS[phase] || 0}%</Caption>}
              multiline
            >
              Самореализация
              <div className="cell-progress">
                <Progress value={PHASE_PROGRESS[phase] || 0} />
              </div>
            </Cell>
            <Cell
              before={<span className="cell-emoji">💰</span>}
              subtitle="Ожидает постановки"
              after={<Caption>0%</Caption>}
              multiline
            >
              Деньги
              <div className="cell-progress">
                <Progress value={0} />
              </div>
            </Cell>
          </>
        )}
      </Section>

      {/* Календарь */}
      <Section header="Февраль">
        <div className="calendar-grid">
          {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((d) => (
            <span key={d} className="calendar-header">{d}</span>
          ))}
          {Array.from({ length: 28 }, (_, i) => {
            const dayNum = i + 1;
            const isDone = dayNum < today && sessionsCount > 0;
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
      </Section>

      {/* Статистика */}
      <Section header="Статистика">
        <Cell after={<Text>{Math.max(sessionsCount, 1)} 🔥</Text>}>
          Серия дней
        </Cell>
        <Cell after={<Text>{sessionsCount}</Text>}>
          Всего сессий
        </Cell>
      </Section>

      {/* Недельный отчёт */}
      <Section header="Недельный отчёт">
        <Placeholder description={
          sessionsCount >= 7
            ? 'Отчёт формируется...'
            : 'Недостаточно данных. Отчёт появится через неделю'
        }>
          📊
        </Placeholder>
      </Section>
    </>
  );
}
