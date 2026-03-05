import { useState, useEffect, useCallback } from 'react';

type Theme = 'light' | 'dark';

const STORAGE_KEY = 'theme';

// Telegram theme CSS vars for light/dark
const THEME_VARS: Record<Theme, Record<string, string>> = {
  light: {
    '--tg-theme-bg-color': '#F2F2F7',
    '--tg-theme-text-color': '#000000',
    '--tg-theme-hint-color': '#6C6C70',
    '--tg-theme-link-color': '#FF6B8A',
    '--tg-theme-button-color': '#FF6B8A',
    '--tg-theme-button-text-color': '#FFFFFF',
    '--tg-theme-secondary-bg-color': '#FFFFFF',
    '--tg-theme-header-bg-color': '#FFFFFF',
    '--tg-theme-accent-text-color': '#FF6B8A',
    '--tg-theme-section-bg-color': '#FFFFFF',
    '--tg-theme-section-header-text-color': '#6C6C70',
    '--tg-theme-subtitle-text-color': '#6C6C70',
    '--tg-theme-destructive-text-color': '#FF3B30',
    '--tg-theme-section-separator-color': 'rgba(60, 60, 67, 0.12)',
    '--tg-theme-bottom-bar-bg-color': '#FFFFFF',
    '--tgui--bg_color': '#F2F2F7',
    '--tgui--secondary_bg_color': '#F2F2F7',
    '--tgui--text_color': '#000000',
    '--tgui--hint_color': '#6C6C70',
    '--tgui--link_color': '#FF6B8A',
    '--tgui--button_color': '#FF6B8A',
    '--tgui--button_text_color': '#FFFFFF',
    '--tgui--header_bg_color': '#FFFFFF',
    '--tgui--section_bg_color': '#FFFFFF',
    '--tgui--section_header_text_color': '#6C6C70',
    '--tgui--subtitle_text_color': '#6C6C70',
    '--tgui--destructive_text_color': '#FF3B30',
    '--tgui--section_separator_color': 'rgba(60, 60, 67, 0.12)',
  },
  dark: {
    '--tg-theme-bg-color': '#1C1C1E',
    '--tg-theme-text-color': '#FFFFFF',
    '--tg-theme-hint-color': '#AEAEB2',
    '--tg-theme-link-color': '#FF6B8A',
    '--tg-theme-button-color': '#FF6B8A',
    '--tg-theme-button-text-color': '#FFFFFF',
    '--tg-theme-secondary-bg-color': '#2C2C2E',
    '--tg-theme-header-bg-color': '#1C1C1E',
    '--tg-theme-accent-text-color': '#FF6B8A',
    '--tg-theme-section-bg-color': '#2C2C2E',
    '--tg-theme-section-header-text-color': '#AEAEB2',
    '--tg-theme-subtitle-text-color': '#AEAEB2',
    '--tg-theme-destructive-text-color': '#FF453A',
    '--tg-theme-section-separator-color': 'rgba(255, 255, 255, 0.12)',
    '--tg-theme-bottom-bar-bg-color': '#2C2C2E',
    '--tgui--bg_color': '#1C1C1E',
    '--tgui--secondary_bg_color': '#1C1C1E',
    '--tgui--text_color': '#FFFFFF',
    '--tgui--hint_color': '#AEAEB2',
    '--tgui--link_color': '#FF6B8A',
    '--tgui--button_color': '#FF6B8A',
    '--tgui--button_text_color': '#FFFFFF',
    '--tgui--header_bg_color': '#1C1C1E',
    '--tgui--section_bg_color': '#2C2C2E',
    '--tgui--section_header_text_color': '#AEAEB2',
    '--tgui--subtitle_text_color': '#AEAEB2',
    '--tgui--destructive_text_color': '#FF453A',
    '--tgui--section_separator_color': 'rgba(255, 255, 255, 0.12)',
  },
};

/** Detect initial theme: localStorage → Telegram → media query → light */
export function getInitialTheme(): Theme {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === 'light' || saved === 'dark') return saved;

  const tgScheme = window.Telegram?.WebApp?.colorScheme;
  if (tgScheme === 'dark' || tgScheme === 'light') return tgScheme;

  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark';

  return 'light';
}

/** Apply theme to DOM: data-theme attr + CSS vars + Telegram API */
function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.setAttribute('data-theme', theme);

  // Set all CSS vars with !important
  const vars = THEME_VARS[theme];
  for (const [key, value] of Object.entries(vars)) {
    root.style.setProperty(key, value, 'important');
  }

  // Body colors
  document.body.style.backgroundColor = theme === 'dark' ? '#1C1C1E' : '#F2F2F7';
  document.body.style.color = theme === 'dark' ? '#FFFFFF' : '#000000';

  // Telegram WebApp API
  const tg = window.Telegram?.WebApp;
  if (tg) {
    try { tg.setHeaderColor(theme === 'dark' ? '#1C1C1E' : '#FFFFFF'); } catch {}
    try { tg.setBackgroundColor(theme === 'dark' ? '#1C1C1E' : '#F2F2F7'); } catch {}
    try { tg.setBottomBarColor(theme === 'dark' ? '#2C2C2E' : '#FFFFFF'); } catch {}
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  // Apply theme on mount and changes
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Listen for Telegram theme changes (only if no manual override)
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;

    const handler = () => {
      // Only follow Telegram if user hasn't manually chosen
      if (!localStorage.getItem(STORAGE_KEY)) {
        const newTheme = tg.colorScheme === 'dark' ? 'dark' : 'light';
        setTheme(newTheme);
      }
    };

    tg.onEvent('themeChanged', handler);
    return () => tg.offEvent('themeChanged', handler);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === 'light' ? 'dark' : 'light';
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light');
  }, []);

  return { theme, toggleTheme } as const;
}
