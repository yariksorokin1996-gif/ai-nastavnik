/**
 * Webapp analytics — fire-and-forget event tracking.
 * POST /api/analytics/event with throttle (same event_type max once per 2s).
 */

const BASE_URL = import.meta.env.VITE_API_URL || '';
const IS_DEV = !window.Telegram?.WebApp?.initData;
const THROTTLE_MS = 2000;

// Last send time per event_type
const _lastSent: Record<string, number> = {};

interface WebappEvent {
  event_type: string;
  page?: string;
  metadata?: Record<string, unknown>;
}

export function trackEvent(event: WebappEvent): void {
  // Dev mode — just log
  if (IS_DEV) {
    console.debug('[analytics]', event.event_type, event.page || '');
    return;
  }

  // Throttle: same event_type max once per 2s
  const now = Date.now();
  const last = _lastSent[event.event_type] ?? 0;
  if (now - last < THROTTLE_MS) return;
  _lastSent[event.event_type] = now;

  // Fire-and-forget
  const initData = window.Telegram?.WebApp?.initData || '';
  fetch(`${BASE_URL}/api/analytics/event`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `tma ${initData}`,
    },
    body: JSON.stringify(event),
  }).catch(() => {});
}
