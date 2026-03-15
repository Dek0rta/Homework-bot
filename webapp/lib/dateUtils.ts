/** Locale-aware date utilities (no external dependency — uses Intl) */

const RU_MONTHS_SHORT = [
  'янв', 'фев', 'мар', 'апр', 'май', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
];
const RU_MONTHS_LONG = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

function parseDate(dateStr: string): Date {
  // "YYYY-MM-DD" → parse as local date (avoid UTC shift)
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function todayLocal(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

export function getDaysLeft(dateStr: string): number {
  const target = parseDate(dateStr);
  const today  = todayLocal();
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

export function isOverdue(dateStr: string): boolean {
  return getDaysLeft(dateStr) < 0;
}

/** "Сегодня" | "Завтра" | "Вчера" | "15 мар" */
export function formatDeadlineShort(dateStr: string): string {
  const days = getDaysLeft(dateStr);
  if (days === 0) return 'Сегодня';
  if (days === 1) return 'Завтра';
  if (days === -1) return 'Вчера';
  const d = parseDate(dateStr);
  return `${d.getDate()} ${RU_MONTHS_SHORT[d.getMonth()]}`;
}

/** "15 марта 2025" */
export function formatDeadlineLong(dateStr: string): string {
  const days = getDaysLeft(dateStr);
  if (days === 0) return 'Сегодня';
  if (days === 1) return 'Завтра';
  if (days === -1) return 'Вчера';
  const d = parseDate(dateStr);
  const year = d.getFullYear();
  const currentYear = new Date().getFullYear();
  const base = `${d.getDate()} ${RU_MONTHS_LONG[d.getMonth()]}`;
  return year !== currentYear ? `${base} ${year}` : base;
}

/** Human-readable relative label for the card footer */
export function daysLeftLabel(dateStr: string): string {
  const days = getDaysLeft(dateStr);
  if (days === 0) return 'сдать сегодня';
  if (days > 0)  return `${days} дн.`;
  return `просрочено на ${Math.abs(days)} дн.`;
}

/** Today's date as "YYYY-MM-DD" (for min= on date input) */
export function todayISO(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}
