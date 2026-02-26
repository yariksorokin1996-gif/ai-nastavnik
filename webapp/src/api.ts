/**
 * API-клиент для Mini App.
 * Использует initData из Telegram WebApp для авторизации.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '';

function getInitData(): string {
  return window.Telegram?.WebApp?.initData || '';
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `tma ${getInitData()}`,
      ...options?.headers,
    },
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }

  return res.json();
}

// --- Types ---

export interface UserData {
  telegram_id: number;
  name: string | null;
  phase: string;
  goal: string | null;
  goal_deadline: string | null;
  area: string | null;
  sessions_count: number;
  is_premium: boolean;
  coaching_style: number;
  mode: string;
  commitments: Array<{ action: string; deadline: string }>;
  patterns_detected: string[];
}

export interface PatternData {
  pattern_type: string;
  pattern_text: string | null;
  count: number;
}

export interface DailyData {
  commitments: Array<{ action: string; deadline: string }>;
  recent_patterns: PatternData[];
  sessions_count: number;
  phase: string;
  streak: number;
}

// --- API methods ---

export function fetchUser(): Promise<UserData> {
  return apiFetch<UserData>('/api/user');
}

export function fetchPatterns(): Promise<PatternData[]> {
  return apiFetch<PatternData[]>('/api/user/patterns');
}

export function fetchDaily(): Promise<DailyData> {
  return apiFetch<DailyData>('/api/user/daily');
}

export function updateStyle(coaching_style: number): Promise<{ ok: boolean }> {
  return apiFetch('/api/user/style', {
    method: 'PUT',
    body: JSON.stringify({ coaching_style }),
  });
}
