'use client';

import { useMemo }     from 'react';
import { HomeworkWithStatus } from '@/types';
import { computeLoad, levelColor, levelLabel, NORM_MINUTES, WARN_MINUTES, LoadEntry } from '@/lib/loadUtils';
import { todayISO } from '@/lib/dateUtils';

interface LoadViewProps {
  homeworks: HomeworkWithStatus[];
  loading:   boolean;
}

// ── SVG bar chart ─────────────────────────────────────────────────────────────

const CHART_W  = 350;
const CHART_H  = 100;
const LABEL_H  = 28;
const PAD_L    = 0;
const PAD_R    = 0;
const BARS     = 14;
const SLOT_W   = (CHART_W - PAD_L - PAD_R) / BARS;
const BAR_W    = Math.round(SLOT_W * 0.62);
const BAR_X0   = PAD_L + (SLOT_W - BAR_W) / 2;

function BarChart({ entries }: { entries: LoadEntry[] }) {
  const maxMin = Math.max(...entries.map(e => e.totalMinutes), WARN_MINUTES);

  const normY = CHART_H - Math.round((NORM_MINUTES / maxMin) * CHART_H);
  const today = todayISO();

  return (
    <svg
      viewBox={`0 0 ${CHART_W} ${CHART_H + LABEL_H}`}
      className="w-full"
      style={{ overflow: 'visible' }}
    >
      {/* Dashed norm line */}
      <line
        x1={0} y1={normY} x2={CHART_W} y2={normY}
        stroke="rgba(142,142,147,0.5)"
        strokeWidth={1}
        strokeDasharray="4 3"
      />
      {/* "3 ч" label on norm line */}
      <text
        x={CHART_W - 2} y={normY - 3}
        textAnchor="end"
        fontSize={7}
        fill="rgba(142,142,147,0.7)"
      >
        3 ч
      </text>

      {entries.map((e, idx) => {
        const x      = PAD_L + idx * SLOT_W + (SLOT_W - BAR_W) / 2;
        const barH   = e.totalMinutes > 0
          ? Math.max(4, Math.round((e.totalMinutes / maxMin) * CHART_H))
          : 3;
        const y      = CHART_H - barH;
        const color  = levelColor(e.level);
        const isToday = e.date === today;

        // Day label: only show day-of-week + date for first entry of week (Mon) or every 2nd for small screens
        const parts  = e.dayLabel.split(' ');   // ["Пн","16","мар"]
        const shortD = parts[0] ?? '';
        const dateN  = parts[1] ?? '';

        return (
          <g key={e.date}>
            {/* Bar */}
            <rect
              x={x}
              y={y}
              width={BAR_W}
              height={barH}
              rx={3}
              fill={color}
              opacity={isToday ? 1 : 0.75}
            />

            {/* Today highlight: circle under bar */}
            {isToday && (
              <circle
                cx={x + BAR_W / 2}
                cy={CHART_H + LABEL_H - 5}
                r={2.5}
                fill="var(--tg-accent)"
              />
            )}

            {/* Day-of-week label */}
            <text
              x={x + BAR_W / 2}
              y={CHART_H + 10}
              textAnchor="middle"
              fontSize={7.5}
              fill={isToday ? 'var(--tg-accent)' : 'rgba(142,142,147,0.8)'}
              fontWeight={isToday ? 700 : 400}
            >
              {shortD}
            </text>
            <text
              x={x + BAR_W / 2}
              y={CHART_H + 20}
              textAnchor="middle"
              fontSize={7}
              fill={isToday ? 'var(--tg-accent)' : 'rgba(142,142,147,0.6)'}
              fontWeight={isToday ? 700 : 400}
            >
              {dateN}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Stats row ─────────────────────────────────────────────────────────────────

function StatCard({ value, label, color }: { value: string | number; label: string; color?: string }) {
  return (
    <div
      className="flex-1 flex flex-col items-center justify-center py-2.5 px-1 rounded-2xl"
      style={{ backgroundColor: 'var(--tg-secondary-bg)' }}
    >
      <span
        className="text-[22px] font-bold leading-none mb-0.5"
        style={{ color: color ?? 'var(--tg-text)' }}
      >
        {value}
      </span>
      <span className="text-[10px] text-center leading-tight" style={{ color: 'var(--tg-hint)' }}>
        {label}
      </span>
    </div>
  );
}

// ── Day row ───────────────────────────────────────────────────────────────────

function DayRow({ entry }: { entry: LoadEntry }) {
  const today = todayISO();
  const isToday = entry.date === today;
  const color = levelColor(entry.level);
  const hours  = Math.floor(entry.totalMinutes / 60);
  const mins   = entry.totalMinutes % 60;
  const timeStr = entry.totalMinutes === 0
    ? 'Нет заданий'
    : hours > 0
      ? `${hours} ч ${mins > 0 ? mins + ' мин' : ''}`.trim()
      : `${mins} мин`;

  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5 border-b"
      style={{
        borderColor: 'rgba(142,142,147,0.12)',
        backgroundColor: isToday ? 'rgba(142,142,147,0.07)' : undefined,
      }}
    >
      {/* Color dot */}
      <div
        className="flex-shrink-0 w-2.5 h-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />

      {/* Day label */}
      <span
        className="text-[13px] w-[76px] flex-shrink-0"
        style={{
          color:      isToday ? 'var(--tg-accent)' : 'var(--tg-text)',
          fontWeight: isToday ? 600 : 400,
        }}
      >
        {entry.dayLabel}
        {isToday && <span className="ml-1 text-[10px]" style={{ color: 'var(--tg-accent)' }}>• сегодня</span>}
      </span>

      {/* Load label */}
      <span
        className="text-[12px] flex-1"
        style={{ color: entry.level === 'none' ? 'var(--tg-hint)' : color }}
      >
        {levelLabel(entry.level)}
      </span>

      {/* Task count + time */}
      <div className="flex flex-col items-end">
        {entry.taskCount > 0 && (
          <span className="text-[12px] font-semibold" style={{ color: 'var(--tg-text)' }}>
            {entry.taskCount} зад.
          </span>
        )}
        <span className="text-[10px]" style={{ color: 'var(--tg-hint)' }}>
          {timeStr}
        </span>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function LoadView({ homeworks, loading }: LoadViewProps) {
  const entries = useMemo(() => computeLoad(homeworks), [homeworks]);

  if (loading) {
    return (
      <div className="px-4 pt-4 space-y-3">
        <div className="h-36 rounded-2xl animate-pulse" style={{ backgroundColor: 'var(--tg-secondary-bg)' }} />
        <div className="flex gap-2">
          {[1,2,3].map(i => (
            <div key={i} className="flex-1 h-16 rounded-2xl animate-pulse"
              style={{ backgroundColor: 'var(--tg-secondary-bg)', opacity: 1 - i * 0.2 }} />
          ))}
        </div>
      </div>
    );
  }

  const totalTasks    = entries.reduce((s, e) => s + e.taskCount, 0);
  const dangerDays    = entries.filter(e => e.level === 'danger').length;
  const peakEntry     = entries.reduce((a, b) => b.totalMinutes > a.totalMinutes ? b : a, entries[0]);
  const peakLabel     = peakEntry && peakEntry.totalMinutes > 0
    ? peakEntry.dayLabel.split(' ').slice(0, 2).join(' ')
    : '—';

  return (
    <div className="h-full overflow-y-auto pb-safe">

      {/* ── Chart card ── */}
      <div
        className="mx-3 mt-3 mb-3 px-3 pt-4 pb-3 rounded-2xl"
        style={{ backgroundColor: 'var(--tg-secondary-bg)' }}
      >
        <p className="text-[10px] font-bold uppercase tracking-widest mb-3 px-1" style={{ color: 'var(--tg-hint)' }}>
          Нагрузка — ближайшие 14 дней
        </p>
        <BarChart entries={entries} />

        {/* Legend */}
        <div className="flex items-center gap-3 mt-3 px-1 flex-wrap">
          {(['ok', 'warn', 'danger'] as const).map(lv => (
            <div key={lv} className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: levelColor(lv) }} />
              <span className="text-[9px]" style={{ color: 'var(--tg-hint)' }}>{levelLabel(lv)}</span>
            </div>
          ))}
          <div className="flex items-center gap-1">
            <svg width="14" height="6" viewBox="0 0 14 6">
              <line x1={0} y1={3} x2={14} y2={3} stroke="rgba(142,142,147,0.5)" strokeWidth={1} strokeDasharray="3 2" />
            </svg>
            <span className="text-[9px]" style={{ color: 'var(--tg-hint)' }}>3 ч (норма)</span>
          </div>
        </div>
      </div>

      {/* ── Stats row ── */}
      <div className="flex gap-2 mx-3 mb-3">
        <StatCard value={totalTasks}  label="заданий всего" />
        <StatCard value={peakLabel}   label="пиковый день" />
        <StatCard
          value={dangerDays}
          label="дней перегруза"
          color={dangerDays > 0 ? '#ff3b30' : undefined}
        />
      </div>

      {/* ── Day list ── */}
      <div
        className="mx-3 mb-3 rounded-2xl overflow-hidden"
        style={{ backgroundColor: 'var(--tg-secondary-bg)' }}
      >
        <p
          className="px-4 pt-3 pb-1.5 text-[10px] font-bold uppercase tracking-widest"
          style={{ color: 'var(--tg-hint)' }}
        >
          По дням
        </p>
        {entries.map(e => <DayRow key={e.date} entry={e} />)}
      </div>

    </div>
  );
}
