import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Mapped to Telegram CSS variables (set in globals.css with fallbacks)
        'tg-bg':           'var(--tg-bg)',
        'tg-secondary-bg': 'var(--tg-secondary-bg)',
        'tg-text':         'var(--tg-text)',
        'tg-hint':         'var(--tg-hint)',
        'tg-link':         'var(--tg-link)',
        'tg-accent':       'var(--tg-accent)',
        'tg-accent-text':  'var(--tg-accent-text)',
      },
      fontFamily: {
        sans: [
          '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto',
          'Helvetica', 'Arial', 'sans-serif',
        ],
      },
      keyframes: {
        'slide-up': {
          '0%':   { transform: 'translateY(100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)',    opacity: '1' },
        },
        'fade-in': {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'tab-badge': {
          '0%':   { transform: 'scale(0.4)', opacity: '0' },
          '60%':  { transform: 'scale(1.15)' },
          '100%': { transform: 'scale(1)',   opacity: '1' },
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.4' },
        },
      },
      transitionDuration: {
        '250': '250ms',
      },
      animation: {
        'slide-up':  'slide-up 0.28s cubic-bezier(0.32, 0.72, 0, 1)',
        'fade-in':   'fade-in 0.2s ease-out',
        'tab-badge': 'tab-badge 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
    },
  },
  plugins: [],
};

export default config;
