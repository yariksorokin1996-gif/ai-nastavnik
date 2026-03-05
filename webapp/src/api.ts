/**
 * API-клиент для Mini App.
 * Использует initData из Telegram WebApp для авторизации.
 * Без Telegram (dev-режим) — возвращает моковые данные.
 */

import { getMockResponse } from './mocks/data';

const BASE_URL = import.meta.env.VITE_API_URL || '';
const IS_DEV = !window.Telegram?.WebApp?.initData;

function getInitData(): string {
  return window.Telegram?.WebApp?.initData || '';
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  // Dev-мок: без Telegram возвращаем фейковые данные
  if (IS_DEV) {
    await new Promise(r => setTimeout(r, 300));
    return getMockResponse(path, options) as T;
  }

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

  // DELETE /api/user returns {ok: true} but we type it as void
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

// --- Types ---

export interface UserData {
  telegram_id: number;
  name: string | null;
  phase: string;
  sessions_count: number;
}

export interface PatternData {
  pattern_type: string;
  pattern_text: string | null;
  count: number;
}

export interface StepData {
  id: number;
  title: string;
  status: string;
  deadline_at: string | null;
  completed_at: string | null;
}

export interface GoalData {
  id: number;
  title: string;
  status: string;
  steps: StepData[];
}

export interface GoalsData {
  goal: GoalData | null;
}

export interface TodayStepsData {
  steps: StepData[];
  completed_count: number;
  total_count: number;
}

export interface CalendarData {
  active_days: string[];
  streak: number;
  total_sessions: number;
}

export interface AffirmationData {
  text: string;
  source: 'bank' | 'generated';
}

// --- API methods ---

export function fetchUser(): Promise<UserData> {
  return apiFetch<UserData>('/api/user');
}

export function fetchPatterns(): Promise<PatternData[]> {
  return apiFetch<PatternData[]>('/api/user/patterns');
}

export function fetchGoals(): Promise<GoalsData> {
  return apiFetch<GoalsData>('/api/user/goals');
}

export function fetchTodaySteps(): Promise<TodayStepsData> {
  return apiFetch<TodayStepsData>('/api/user/goals/today');
}

export function updateStepStatus(stepId: number, status: 'done' | 'skipped'): Promise<StepData> {
  return apiFetch<StepData>(`/api/user/goals/steps/${stepId}`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  });
}

export function fetchCalendar(): Promise<CalendarData> {
  return apiFetch<CalendarData>('/api/user/calendar');
}

export function fetchAffirmation(): Promise<AffirmationData> {
  return apiFetch<AffirmationData>('/api/user/affirmation');
}

export function deleteAccount(): Promise<void> {
  return apiFetch<void>('/api/user', { method: 'DELETE' });
}
