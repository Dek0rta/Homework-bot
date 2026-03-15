'use client';

import { useEffect, useState, useCallback } from 'react';
import { TelegramUser } from '@/types';

// ── Telegram WebApp type stubs ────────────────────────────────────────────────
interface TelegramWebApp {
  ready(): void;
  expand(): void;
  close(): void;
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  isExpanded: boolean;
  initDataUnsafe: { user?: TelegramUser };
  themeParams: {
    bg_color?: string;
    text_color?: string;
    hint_color?: string;
    link_color?: string;
    button_color?: string;
    button_text_color?: string;
    secondary_bg_color?: string;
  };
  HapticFeedback: {
    impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notificationOccurred(type: 'error' | 'success' | 'warning'): void;
    selectionChanged(): void;
  };
  BackButton: {
    isVisible: boolean;
    show(): void;
    hide(): void;
    onClick(fn: () => void): void;
    offClick(fn: () => void): void;
  };
  enableClosingConfirmation(): void;
  disableClosingConfirmation(): void;
  sendData(data: string): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}

/** Fallback dev user when running outside Telegram */
const DEV_USER: TelegramUser = {
  id: 999_999_999,
  first_name: 'Dev',
  last_name: 'User',
  username: 'devuser',
  language_code: 'ru',
};

export function useTelegram() {
  const [user, setUser]               = useState<TelegramUser | null>(null);
  const [colorScheme, setColorScheme] = useState<'light' | 'dark'>('light');
  const [isReady, setIsReady]         = useState(false);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;

    if (tg) {
      tg.ready();
      tg.expand();
      setUser(tg.initDataUnsafe.user ?? DEV_USER);
      setColorScheme(tg.colorScheme ?? 'light');
    } else {
      // Browser / dev environment
      setUser(DEV_USER);
      const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      setColorScheme(dark ? 'dark' : 'light');
    }

    setIsReady(true);
  }, []);

  /** Trigger haptic feedback (silently ignored outside Telegram) */
  const haptic = useCallback(
    (type: 'light' | 'medium' | 'heavy' | 'success' | 'error' | 'warning' = 'light') => {
      const fb = window.Telegram?.WebApp?.HapticFeedback;
      if (!fb) return;
      if (type === 'success' || type === 'error' || type === 'warning') {
        fb.notificationOccurred(type);
      } else {
        fb.impactOccurred(type);
      }
    },
    [],
  );

  return {
    user,
    colorScheme,
    isReady,
    haptic,
    /** Raw WebApp object — use with caution */
    tg: typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined,
  };
}
