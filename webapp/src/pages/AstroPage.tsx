import { useState } from 'react';
import { Section, Cell, Title, Text, Caption } from '@telegram-apps/telegram-ui';
import { Lock } from 'lucide-react';

export function AstroPage() {
  const [cardRevealed, setCardRevealed] = useState(false);

  const handleReveal = () => {
    setCardRevealed(true);
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light');
  };

  return (
    <>
      <div className="page-title">
        <Title level="1" weight="1">Астро</Title>
        <Caption style={{ color: '#8E8E93', marginTop: 4 }}>
          Твоё звёздное пространство 🌙
        </Caption>
      </div>

      {/* Карта дня */}
      <div style={{ padding: '0 16px 16px' }}>
        <div
          className={`tarot-card ${cardRevealed ? 'tarot-card--revealed' : ''}`}
          onClick={!cardRevealed ? handleReveal : undefined}
        >
          {!cardRevealed ? (
            <>
              <div className="tarot-card__emoji">✦</div>
              <Text weight="2">Карта дня</Text>
              <Caption style={{ color: '#8E8E93', marginTop: 4 }}>
                Нажми, чтобы открыть
              </Caption>
            </>
          ) : (
            <>
              <div className="tarot-card__emoji">👑</div>
              <Text weight="1">Императрица</Text>
              <Caption style={{ color: '#8E8E93', marginTop: 8, textAlign: 'center', lineHeight: '18px' }}>
                Императрица говорит о внутренней силе и решительности.
                Сегодня ты способна на большее, чем думаешь.
              </Caption>
            </>
          )}
        </div>
      </div>

      {/* Аффирмация */}
      <Section header="Аффирмация дня">
        <Cell before={<span className="cell-emoji">✨</span>} multiline>
          <Text style={{ fontStyle: 'italic' }}>
            «Я заслуживаю лучшего и не боюсь за это бороться»
          </Text>
        </Cell>
      </Section>

      {/* Мини-гороскоп */}
      <Section header="Мини-гороскоп">
        <Cell before={<span className="cell-emoji">🌙</span>} multiline>
          <Caption style={{ color: '#8E8E93' }}>
            Пройди онбординг и введи дату рождения для персонального гороскопа
          </Caption>
        </Cell>
      </Section>

      {/* Премиум */}
      <Section header="Премиум">
        <Cell
          before={<span className="cell-emoji">🔮</span>}
          subtitle="Подробное чтение карт на ситуацию"
          after={<Lock size={16} color="#C7C7CC" />}
          multiline
        >
          Полный расклад
        </Cell>
        <Cell
          before={<span className="cell-emoji">💑</span>}
          subtitle="Анализ отношений по датам рождения"
          after={<Lock size={16} color="#C7C7CC" />}
          multiline
        >
          Совместимость
        </Cell>
        <Cell
          before={<span className="cell-emoji">📅</span>}
          subtitle="Персональный прогноз с рекомендациями"
          after={<Lock size={16} color="#C7C7CC" />}
          multiline
        >
          Прогноз на месяц
        </Cell>
      </Section>

      {/* Архив */}
      <Section>
        <Cell
          before={<span className="cell-emoji">📜</span>}
          subtitle="История твоих карт дня"
        >
          Архив карт
        </Cell>
      </Section>
    </>
  );
}
