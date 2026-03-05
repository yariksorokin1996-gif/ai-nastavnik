/**
 * Моковые данные для просмотра webapp без Telegram.
 * Активируются автоматически когда нет initData (не в Telegram).
 */
import type {
  UserData,
  PatternData,
  GoalsData,
  TodayStepsData,
  CalendarData,
  AffirmationData,
  StepData,
} from '../api';

// --- Хелперы для динамических дат ---

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return formatDate(d);
}

const TODAY = formatDate(new Date());

// --- Моковые данные ---

export const MOCK_USER: UserData = {
  telegram_id: 123456,
  name: 'Маша',
  phase: 'ЗЕРКАЛО',
  sessions_count: 15,
};

export const MOCK_CALENDAR: CalendarData = {
  active_days: [
    TODAY,
    daysAgo(1),
    daysAgo(2),
    daysAgo(4),
    daysAgo(5),
    daysAgo(7),
    daysAgo(10),
    daysAgo(14),
    daysAgo(18),
  ],
  streak: 3,
  total_sessions: 15,
};

export const MOCK_AFFIRMATION: AffirmationData = {
  text: 'Ты справляешься лучше, чем тебе кажется. Каждый маленький шаг — это уже движение вперёд.',
  source: 'bank',
};

export const MOCK_TODAY_STEPS: TodayStepsData = {
  steps: [
    { id: 1, title: 'Написать маме', status: 'done', deadline_at: TODAY, completed_at: TODAY },
    { id: 2, title: 'Погулять 30 минут', status: 'pending', deadline_at: TODAY, completed_at: null },
    { id: 3, title: 'Записать 3 благодарности', status: 'pending', deadline_at: TODAY, completed_at: null },
  ],
  completed_count: 1,
  total_count: 3,
};

export const MOCK_GOALS: GoalsData = {
  goal: {
    id: 1,
    title: 'Наладить отношения с мамой',
    status: 'active',
    steps: [
      { id: 1, title: 'Написать маме', status: 'done', deadline_at: daysAgo(3), completed_at: daysAgo(3) },
      { id: 2, title: 'Позвонить и поговорить 10 минут', status: 'done', deadline_at: daysAgo(1), completed_at: daysAgo(1) },
      { id: 3, title: 'Погулять 30 минут', status: 'pending', deadline_at: TODAY, completed_at: null },
      { id: 4, title: 'Записать 3 благодарности', status: 'pending', deadline_at: daysAgo(-2), completed_at: null },
      { id: 5, title: 'Пригласить маму на чай', status: 'pending', deadline_at: daysAgo(-5), completed_at: null },
    ],
  },
};

export const MOCK_PATTERNS: PatternData[] = [
  { pattern_type: 'behavior', pattern_text: 'Избегание конфликтов', count: 5 },
  { pattern_type: 'emotion', pattern_text: 'Тревога перед разговорами', count: 3 },
];

// --- Роутинг мок-ответов ---

export function getMockResponse(path: string, options?: RequestInit): unknown {
  // PUT /api/user/goals/steps/:id
  if (path.startsWith('/api/user/goals/steps/') && options?.method === 'PUT') {
    const body = JSON.parse(options.body as string);
    const stepId = parseInt(path.split('/').pop() || '0');
    const mockStep: StepData = {
      id: stepId,
      title: 'Шаг',
      status: body.status,
      deadline_at: TODAY,
      completed_at: body.status === 'done' ? TODAY : null,
    };
    return mockStep;
  }

  // DELETE /api/user
  if (path === '/api/user' && options?.method === 'DELETE') {
    return { ok: true };
  }

  switch (path) {
    case '/api/user':
      return MOCK_USER;
    case '/api/user/patterns':
      return MOCK_PATTERNS;
    case '/api/user/goals':
      return MOCK_GOALS;
    case '/api/user/goals/today':
      return MOCK_TODAY_STEPS;
    case '/api/user/calendar':
      return MOCK_CALENDAR;
    case '/api/user/affirmation':
      return MOCK_AFFIRMATION;
    default:
      return {};
  }
}
