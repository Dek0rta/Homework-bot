/** Locale-aware date utilities — no external dependencies, uses Intl */

const RU_MONTHS_SHORT = [
  'янв', 'фев', 'мар', 'апр', 'май', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
];
const RU_MONTHS_LONG = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

function parseDate(dateStr: string): Date {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function todayLocal(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

export function getDaysLeft(dateStr: string): number {
  return Math.round(
    (parseDate(dateStr).getTime() - todayLocal().getTime()) / 86_400_000,
  );
}

export function isOverdue(dateStr: string): boolean {
  return getDaysLeft(dateStr) < 0;
}

/** "Сегодня" | "Завтра" | "Вчера" | "15 мар" */
export function formatDeadlineShort(dateStr: string): string {
  const days = getDaysLeft(dateStr);
  if (days === 0)  return 'Сегодня';
  if (days === 1)  return 'Завтра';
  if (days === -1) return 'Вчера';
  const d = parseDate(dateStr);
  return `${d.getDate()} ${RU_MONTHS_SHORT[d.getMonth()]}`;
}

/** "15 марта 2025" */
export function formatDeadlineLong(dateStr: string): string {
  const days = getDaysLeft(dateStr);
  if (days === 0)  return 'Сегодня';
  if (days === 1)  return 'Завтра';
  if (days === -1) return 'Вчера';
  const d = parseDate(dateStr);
  const year        = d.getFullYear();
  const currentYear = new Date().getFullYear();
  const base        = `${d.getDate()} ${RU_MONTHS_LONG[d.getMonth()]}`;
  return year !== currentYear ? `${base} ${year}` : base;
}

export function daysLeftLabel(dateStr: string): string {
  const days = getDaysLeft(dateStr);
  if (days === 0)  return 'сдать сегодня';
  if (days > 0)    return `${days} дн.`;
  return `просрочено на ${Math.abs(days)} дн.`;
}

/** Today as "YYYY-MM-DD" */
export function todayISO(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

// ── Week utilities ────────────────────────────────────────────────────────────

/** Add n calendar days to a Date */
export function addDays(d: Date, n: number): Date {
  const result = new Date(d);
  result.setDate(result.getDate() + n);
  return result;
}

/** Return the Monday of the week containing `ref` (defaults to today) */
export function getWeekStart(ref?: Date): Date {
  const d   = ref ? new Date(ref) : new Date();
  const day = d.getDay();                   // 0=Sun
  const diff = day === 0 ? -6 : 1 - day;   // shift to Mon
  const mon = new Date(d);
  mon.setDate(d.getDate() + diff);
  mon.setHours(0, 0, 0, 0);
  return mon;
}

/** Return 6 dates Mon–Sat starting from weekStart */
export function getWeekDays(weekStart: Date): Date[] {
  return Array.from({ length: 6 }, (_, i) => addDays(weekStart, i));
}

/** Date → "YYYY-MM-DD" */
export function dateToISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** "YYYY-MM-DD" → 0=Monday … 6=Sunday */
export function getDayOfWeek(dateStr: string): number {
  const js = parseDate(dateStr).getDay(); // 0=Sun
  return js === 0 ? 6 : js - 1;
}

const DAYS_FULL  = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];
const DAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

export function formatDayHeader(d: Date): { short: string; date: string; full: string } {
  const idx  = d.getDay() === 0 ? 6 : d.getDay() - 1; // 0=Mon
  const date = `${d.getDate()} ${RU_MONTHS_SHORT[d.getMonth()]}`;
  return {
    short: DAYS_SHORT[idx] ?? '??',
    date,
    full:  `${DAYS_FULL[idx] ?? '?'}, ${date}`,
  };
}

/** Week range label: "16 – 21 марта 2026" */
export function formatWeekRange(weekStart: Date): string {
  const weekEnd = addDays(weekStart, 5); // Saturday
  const startD  = weekStart.getDate();
  const endD    = weekEnd.getDate();
  const month   = RU_MONTHS_LONG[weekEnd.getMonth()];
  const year    = weekEnd.getFullYear();
  if (weekStart.getMonth() === weekEnd.getMonth()) {
    return `${startD} – ${endD} ${month} ${year}`;
  }
  return `${startD} ${RU_MONTHS_SHORT[weekStart.getMonth()]} – ${endD} ${month} ${year}`;
}
