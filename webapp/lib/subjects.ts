export interface SubjectStyle {
  color: string;
  bg: string;
  border: string;
  /** Very subtle bg for badges */
  badge: string;
  emoji: string;
}

export const SUBJECT_MAP: Record<string, SubjectStyle> = {
  'Математика':  { color: '#3b82f6', bg: 'rgba(59,130,246,0.12)',  border: 'rgba(59,130,246,0.28)',  badge: 'rgba(59,130,246,0.18)',  emoji: '📐' },
  'Алгебра':     { color: '#6366f1', bg: 'rgba(99,102,241,0.12)',  border: 'rgba(99,102,241,0.28)',  badge: 'rgba(99,102,241,0.18)',  emoji: '🔢' },
  'Геометрия':   { color: '#8b5cf6', bg: 'rgba(139,92,246,0.12)',  border: 'rgba(139,92,246,0.28)',  badge: 'rgba(139,92,246,0.18)',  emoji: '📏' },
  'Физика':      { color: '#a855f7', bg: 'rgba(168,85,247,0.12)',  border: 'rgba(168,85,247,0.28)',  badge: 'rgba(168,85,247,0.18)',  emoji: '⚡' },
  'Химия':       { color: '#f97316', bg: 'rgba(249,115,22,0.12)',  border: 'rgba(249,115,22,0.28)',  badge: 'rgba(249,115,22,0.18)',  emoji: '🧪' },
  'Биология':    { color: '#22c55e', bg: 'rgba(34,197,94,0.12)',   border: 'rgba(34,197,94,0.28)',   badge: 'rgba(34,197,94,0.18)',   emoji: '🌿' },
  'История':     { color: '#b45309', bg: 'rgba(180,83,9,0.12)',    border: 'rgba(180,83,9,0.28)',    badge: 'rgba(180,83,9,0.18)',    emoji: '📜' },
  'Обществознание': { color: '#92400e', bg: 'rgba(146,64,14,0.12)',  border: 'rgba(146,64,14,0.28)',  badge: 'rgba(146,64,14,0.18)',  emoji: '🏛️' },
  'Литература':  { color: '#16a34a', bg: 'rgba(22,163,74,0.12)',   border: 'rgba(22,163,74,0.28)',   badge: 'rgba(22,163,74,0.18)',   emoji: '📚' },
  'Русский':     { color: '#dc2626', bg: 'rgba(220,38,38,0.12)',   border: 'rgba(220,38,38,0.28)',   badge: 'rgba(220,38,38,0.18)',   emoji: '📝' },
  'Английский':  { color: '#0891b2', bg: 'rgba(8,145,178,0.12)',   border: 'rgba(8,145,178,0.28)',   badge: 'rgba(8,145,178,0.18)',   emoji: '🇬🇧' },
  'Немецкий':    { color: '#0369a1', bg: 'rgba(3,105,161,0.12)',   border: 'rgba(3,105,161,0.28)',   badge: 'rgba(3,105,161,0.18)',   emoji: '🇩🇪' },
  'География':   { color: '#65a30d', bg: 'rgba(101,163,13,0.12)',  border: 'rgba(101,163,13,0.28)',  badge: 'rgba(101,163,13,0.18)',  emoji: '🌍' },
  'Информатика': { color: '#0284c7', bg: 'rgba(2,132,199,0.12)',   border: 'rgba(2,132,199,0.28)',   badge: 'rgba(2,132,199,0.18)',   emoji: '💻' },
  'Физкультура': { color: '#e11d48', bg: 'rgba(225,29,72,0.12)',   border: 'rgba(225,29,72,0.28)',   badge: 'rgba(225,29,72,0.18)',   emoji: '🏃' },
  'Музыка':      { color: '#db2777', bg: 'rgba(219,39,119,0.12)',  border: 'rgba(219,39,119,0.28)',  badge: 'rgba(219,39,119,0.18)',  emoji: '🎵' },
  'Рисование':   { color: '#d97706', bg: 'rgba(217,119,6,0.12)',   border: 'rgba(217,119,6,0.28)',   badge: 'rgba(217,119,6,0.18)',   emoji: '🎨' },
};

const DEFAULT_STYLE: SubjectStyle = {
  color: '#6b7280',
  bg: 'rgba(107,114,128,0.12)',
  border: 'rgba(107,114,128,0.28)',
  badge: 'rgba(107,114,128,0.18)',
  emoji: '📖',
};

export function getSubjectStyle(subject: string): SubjectStyle {
  return SUBJECT_MAP[subject] ?? DEFAULT_STYLE;
}

export const SUBJECTS = Object.keys(SUBJECT_MAP);
