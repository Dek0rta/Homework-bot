'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Target, Trash2, ChevronDown } from 'lucide-react';
import { Grade } from '@/types';
import { getSubjectStyle } from '@/lib/subjects';

interface GradesViewProps {
  grades:       Grade[];
  targets:      Record<string, number>;
  loading:      boolean;
  subjects:     string[];
  onAddGrade:   (subject: string, value: 2 | 3 | 4 | 5) => void;
  onDeleteGrade:(gradeId: string) => void;
  onSetTarget:  (subject: string, target: number) => void;
}

// ── Colour helpers ─────────────────────────────────────────────────────────────

function gradeColor(avg: number): string {
  if (avg >= 4.5) return '#22c55e';
  if (avg >= 3.5) return '#f59e0b';
  return '#ef4444';
}

function gradeBg(avg: number): string {
  if (avg >= 4.5) return 'rgba(34,197,94,0.13)';
  if (avg >= 3.5) return 'rgba(245,158,11,0.13)';
  return 'rgba(239,68,68,0.13)';
}

// Progress bar width as % (grades run 2–5, so range = 3)
function progressPct(value: number): number {
  return Math.max(0, Math.min(100, ((value - 2) / 3) * 100));
}

// ── Sub-components ─────────────────────────────────────────────────────────────

interface SubjectCardProps {
  subject:      string;
  subGrades:    Grade[];
  target?:      number;
  onAddGrade:   (v: 2 | 3 | 4 | 5) => void;
  onDeleteGrade:(id: string) => void;
  onSetTarget:  (t: number) => void;
}

function SubjectCard({
  subject, subGrades, target, onAddGrade, onDeleteGrade, onSetTarget,
}: SubjectCardProps) {
  const [expanded,      setExpanded]      = useState(false);
  const [editingTarget, setEditingTarget] = useState(false);

  const style = getSubjectStyle(subject);
  const count = subGrades.length;
  const avg   = count > 0 ? subGrades.reduce((s, g) => s + g.value, 0) / count : 0;

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ backgroundColor: 'var(--tg-secondary-bg)' }}
    >
      {/* ── Header row ──────────────────────────────────────────────────────── */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 active:opacity-70"
        onClick={() => setExpanded(e => !e)}
      >
        <span className="text-[20px] flex-shrink-0">{style.emoji}</span>

        <div className="flex-1 text-left min-w-0">
          <p className="text-[14px] font-medium truncate" style={{ color: 'var(--tg-text)' }}>
            {subject}
          </p>

          {count > 0 && (
            <div className="relative mt-[5px] h-[5px] rounded-full overflow-hidden"
              style={{ backgroundColor: 'rgba(142,142,147,0.18)' }}
            >
              <motion.div
                className="absolute inset-y-0 left-0 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${progressPct(avg)}%` }}
                transition={{ duration: 0.55, ease: 'easeOut' }}
                style={{ backgroundColor: gradeColor(avg) }}
              />
              {/* Target marker */}
              {target && (
                <div
                  className="absolute top-0 bottom-0 w-[2px] rounded-full"
                  style={{
                    left:            `${progressPct(target)}%`,
                    backgroundColor: 'var(--tg-accent)',
                    opacity:         0.7,
                  }}
                />
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {count > 0 ? (
            <span
              className="text-[16px] font-bold min-w-[38px] text-right tabular-nums"
              style={{ color: gradeColor(avg) }}
            >
              {avg.toFixed(2)}
            </span>
          ) : (
            <span className="text-[14px] min-w-[38px] text-right" style={{ color: 'var(--tg-hint)' }}>
              —
            </span>
          )}

          <motion.div animate={{ rotate: expanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronDown size={16} style={{ color: 'var(--tg-hint)' }} />
          </motion.div>
        </div>
      </button>

      {/* ── Expanded panel ──────────────────────────────────────────────────── */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3">

              {/* Divider */}
              <div className="h-px" style={{ backgroundColor: 'rgba(142,142,147,0.15)' }} />

              {/* Target row */}
              <div className="flex items-center justify-between">
                <span className="text-[12px]" style={{ color: 'var(--tg-hint)' }}>Цель</span>

                {editingTarget ? (
                  <div className="flex items-center gap-1.5">
                    {([3, 4, 5] as const).map(t => (
                      <button
                        key={t}
                        onClick={() => { onSetTarget(t); setEditingTarget(false); }}
                        className="w-8 h-8 rounded-xl text-[13px] font-bold active:opacity-60 transition-colors"
                        style={{
                          backgroundColor: t === target ? 'var(--tg-accent)' : gradeBg(t),
                          color:           t === target ? '#fff'             : gradeColor(t),
                        }}
                      >
                        {t}
                      </button>
                    ))}
                    <button
                      onClick={() => setEditingTarget(false)}
                      className="text-[11px] px-1 active:opacity-60"
                      style={{ color: 'var(--tg-hint)' }}
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setEditingTarget(true)}
                    className="flex items-center gap-1 active:opacity-60"
                  >
                    <Target size={13} style={{ color: 'var(--tg-accent)' }} />
                    <span className="text-[13px]" style={{ color: 'var(--tg-accent)' }}>
                      {target ? `≥ ${target}` : 'Задать цель'}
                    </span>
                  </button>
                )}
              </div>

              {/* Individual grade chips */}
              {count > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {[...subGrades].reverse().map(grade => (
                    <motion.button
                      key={grade.id}
                      initial={{ scale: 0.75, opacity: 0 }}
                      animate={{ scale: 1,    opacity: 1 }}
                      exit={{    scale: 0.75, opacity: 0 }}
                      whileTap={{ scale: 0.88 }}
                      onClick={() => onDeleteGrade(grade.id)}
                      title={grade.note ?? `Оценка ${grade.value} от ${grade.date}`}
                      className="flex items-center gap-[3px] px-2 py-1 rounded-xl active:opacity-60"
                      style={{ backgroundColor: gradeBg(grade.value), color: gradeColor(grade.value) }}
                    >
                      <span className="text-[14px] font-bold leading-none">{grade.value}</span>
                      <Trash2 size={9} strokeWidth={2} />
                    </motion.button>
                  ))}
                </div>
              )}

              {/* Quick add */}
              <div className="flex items-center gap-2">
                <span className="text-[12px] flex-shrink-0" style={{ color: 'var(--tg-hint)' }}>
                  Добавить:
                </span>
                {([2, 3, 4, 5] as const).map(v => (
                  <motion.button
                    key={v}
                    whileTap={{ scale: 0.85 }}
                    onClick={() => onAddGrade(v)}
                    className="w-9 h-9 rounded-xl text-[16px] font-bold active:opacity-70"
                    style={{ backgroundColor: gradeBg(v), color: gradeColor(v) }}
                  >
                    {v}
                  </motion.button>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Main view ──────────────────────────────────────────────────────────────────

export default function GradesView({
  grades, targets, loading, subjects, onAddGrade, onDeleteGrade, onSetTarget,
}: GradesViewProps) {

  const overallAvg = grades.length > 0
    ? grades.reduce((s, g) => s + g.value, 0) / grades.length
    : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div
          className="w-7 h-7 rounded-full border-[3px] animate-spin"
          style={{ borderColor: 'var(--tg-accent)', borderTopColor: 'transparent' }}
        />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto" style={{ backgroundColor: 'var(--tg-bg)' }}>

      {/* ── GPA Summary card ── */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1,  y: 0   }}
        transition={{ duration: 0.3 }}
        className="mx-3 mt-3 mb-3 rounded-2xl p-4"
        style={{ backgroundColor: 'var(--tg-secondary-bg)' }}
      >
        <div className="flex items-end justify-between">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide"
               style={{ color: 'var(--tg-hint)' }}>
              Средний балл
            </p>
            <motion.p
              key={overallAvg.toFixed(2)}
              initial={{ scale: 0.85, opacity: 0 }}
              animate={{ scale: 1,    opacity: 1 }}
              className="text-[36px] font-bold leading-none mt-1"
              style={{ color: overallAvg > 0 ? gradeColor(overallAvg) : 'var(--tg-hint)' }}
            >
              {overallAvg > 0 ? overallAvg.toFixed(2) : '—'}
            </motion.p>
          </div>

          <div className="text-right">
            <p className="text-[11px] font-medium uppercase tracking-wide"
               style={{ color: 'var(--tg-hint)' }}>
              Оценок
            </p>
            <p className="text-[28px] font-semibold leading-none mt-1"
               style={{ color: 'var(--tg-text)' }}>
              {grades.length}
            </p>
          </div>
        </div>

        {overallAvg > 0 && (
          <div className="mt-3 h-[6px] rounded-full overflow-hidden"
               style={{ backgroundColor: 'rgba(142,142,147,0.18)' }}>
            <motion.div
              className="h-full rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${progressPct(overallAvg)}%` }}
              transition={{ duration: 0.65, ease: 'easeOut' }}
              style={{ backgroundColor: gradeColor(overallAvg) }}
            />
          </div>
        )}

        {/* Legend */}
        <div className="flex gap-4 mt-3">
          {[
            { label: 'Отлично',    color: '#22c55e', min: '≥ 4.5' },
            { label: 'Хорошо',     color: '#f59e0b', min: '3.5–4.4' },
            { label: 'Плохо',      color: '#ef4444', min: '< 3.5' },
          ].map(({ label, color, min }) => (
            <div key={label} className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
              <span className="text-[10px]" style={{ color: 'var(--tg-hint)' }}>
                {min} — {label}
              </span>
            </div>
          ))}
        </div>
      </motion.div>

      {/* ── Subject list ── */}
      <div className="mx-3 pb-4 space-y-1.5">
        {subjects.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <span className="text-[48px]">📊</span>
            <p className="text-[16px] font-medium" style={{ color: 'var(--tg-text)' }}>
              Предметы не найдены
            </p>
            <p className="text-[13px] text-center px-8" style={{ color: 'var(--tg-hint)' }}>
              Настройте расписание, чтобы начать отслеживать оценки
            </p>
          </div>
        ) : (
          subjects.map((subject, idx) => {
            const subGrades = grades.filter(g => g.subject === subject);
            return (
              <motion.div
                key={subject}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.025, duration: 0.22 }}
              >
                <SubjectCard
                  subject={subject}
                  subGrades={subGrades}
                  target={targets[subject]}
                  onAddGrade={v  => onAddGrade(subject, v)}
                  onDeleteGrade={onDeleteGrade}
                  onSetTarget={t => onSetTarget(subject, t)}
                />
              </motion.div>
            );
          })
        )}
      </div>
    </div>
  );
}
