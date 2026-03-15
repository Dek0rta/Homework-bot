import { HomeworkWithStatus } from '@/types';
import { addDays, dateToISO } from '@/lib/dateUtils';

export type LoadLevel = 'none' | 'ok' | 'warn' | 'danger';

export interface LoadEntry {
  date:         string;   // "YYYY-MM-DD"
  dayLabel:     string;   // "Пн 16"
  taskCount:    number;
  totalMinutes: number;
  level:        LoadLevel;
}

const MINUTES_PER_TASK = 30;
export const NORM_MINUTES = 180;   // 3 h — "нормальная" нагрузка
export const WARN_MINUTES = 270;   // 4.5 h — предупреждение

const DAY_SHORT = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
const MON_SHORT = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];

function fmtLabel(d: Date): string {
  return `${DAY_SHORT[d.getDay()]} ${d.getDate()} ${MON_SHORT[d.getMonth()]}`;
}

export function levelColor(level: LoadLevel): string {
  switch (level) {
    case 'danger': return '#ff3b30';
    case 'warn':   return '#ff9500';
    case 'ok':     return '#34c759';
    default:       return 'rgba(142,142,147,0.35)';
  }
}

export function levelLabel(level: LoadLevel): string {
  switch (level) {
    case 'danger': return 'Перегруз';
    case 'warn':   return 'Высокая';
    case 'ok':     return 'Норма';
    default:       return 'Свободно';
  }
}

/** Compute per-day load for the next N weekdays (Mon–Sat, skip Sunday) */
export function computeLoad(
  homeworks: HomeworkWithStatus[],
  days = 14,
): LoadEntry[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const entries: LoadEntry[] = [];

  for (let i = 0; entries.length < days; i++) {
    const d = addDays(today, i);
    if (d.getDay() === 0) continue;          // skip Sunday

    const iso       = dateToISO(d);
    const tasks     = homeworks.filter(hw => !hw.isDone && hw.deadline === iso);
    const minutes   = tasks.length * MINUTES_PER_TASK;

    let level: LoadLevel = 'none';
    if      (minutes > WARN_MINUTES) level = 'danger';
    else if (minutes > NORM_MINUTES) level = 'warn';
    else if (minutes > 0)            level = 'ok';

    entries.push({ date: iso, dayLabel: fmtLabel(d), taskCount: tasks.length, totalMinutes: minutes, level });
  }

  return entries;
}
