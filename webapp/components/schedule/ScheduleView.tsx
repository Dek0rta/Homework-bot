'use client';

import { useState, useEffect, useRef, useMemo }   from 'react';
import { ChevronLeft, ChevronRight, Check, Plus }  from 'lucide-react';
import { HomeworkWithStatus, ScheduleLesson }      from '@/types';
import { getSubjectStyle }                         from '@/lib/subjects';
import {
  getWeekStart, getWeekDays, addDays, dateToISO,
  formatDayHeader, formatWeekRange, todayISO, isOverdue,
} from '@/lib/dateUtils';

interface ScheduleViewProps {
  homeworks: HomeworkWithStatus[];
  schedule:  ScheduleLesson[];
  loading:   boolean;
  onToggle:  (id: string) => void;
  onOpen:    (hw: HomeworkWithStatus) => void;
  onAddForSubject?: (subject: string, deadline: string) => void;
}

export default function ScheduleView({
  homeworks, schedule, loading, onToggle, onOpen, onAddForSubject,
}: ScheduleViewProps) {
  const [weekOffset, setWeekOffset] = useState(0);
  const todayRef  = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const weekStart = useMemo(
    () => addDays(getWeekStart(), weekOffset * 7),
    [weekOffset],
  );
  const weekDays = useMemo(() => getWeekDays(weekStart), [weekStart]);
  const today    = todayISO();

  // Scroll to today on mount / week change
  useEffect(() => {
    if (weekOffset === 0 && todayRef.current && scrollRef.current) {
      const top = todayRef.current.offsetTop - 8;
      scrollRef.current.scrollTo({ top, behavior: 'smooth' });
    }
  }, [weekOffset, loading]);

  if (loading) return <ScheduleSkeleton />;

  const isCurrentWeek = weekOffset === 0;
  const weekRange     = formatWeekRange(weekStart);

  return (
    <div className="flex flex-col h-full">
      {/* ── Week navigation ── */}
      <div
        className="flex items-center justify-between px-4 py-2.5 flex-shrink-0 border-b"
        style={{ borderColor: 'rgba(142,142,147,0.18)' }}
      >
        <button
          onClick={() => setWeekOffset(o => o - 1)}
          className="w-8 h-8 flex items-center justify-center rounded-full active:opacity-50"
          style={{ backgroundColor: 'var(--tg-secondary-bg)' }}
        >
          <ChevronLeft size={16} style={{ color: 'var(--tg-hint)' }} />
        </button>

        <button
          onClick={() => setWeekOffset(0)}
          className="text-[13px] font-medium text-center"
          style={{ color: isCurrentWeek ? 'var(--tg-accent)' : 'var(--tg-text)' }}
        >
          {weekRange}
        </button>

        <button
          onClick={() => setWeekOffset(o => o + 1)}
          className="w-8 h-8 flex items-center justify-center rounded-full active:opacity-50"
          style={{ backgroundColor: 'var(--tg-secondary-bg)' }}
        >
          <ChevronRight size={16} style={{ color: 'var(--tg-hint)' }} />
        </button>
      </div>

      {/* ── Day chips ── */}
      <div
        className="flex gap-1.5 px-4 py-2 overflow-x-auto flex-shrink-0 scrollbar-hide"
        style={{ borderBottom: '1px solid rgba(142,142,147,0.12)' }}
      >
        {weekDays.map((day, i) => {
          const ds       = dateToISO(day);
          const isToday  = ds === today;
          const isPast   = ds < today;
          const header   = formatDayHeader(day);
          const hasDue   = homeworks.some(hw => hw.deadline === ds && !hw.isDone);

          return (
            <button
              key={ds}
              onClick={() => {
                const el = document.getElementById(`day-${ds}`);
                el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
              }}
              className="flex-shrink-0 flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-xl transition-all"
              style={{
                backgroundColor: isToday ? 'var(--tg-accent)' : 'var(--tg-secondary-bg)',
                opacity: isPast && !isToday ? 0.55 : 1,
              }}
            >
              <span
                className="text-[10px] font-bold uppercase tracking-wide"
                style={{ color: isToday ? 'var(--tg-accent-text)' : 'var(--tg-hint)' }}
              >
                {header.short}
              </span>
              <span
                className="text-[14px] font-semibold"
                style={{ color: isToday ? 'var(--tg-accent-text)' : 'var(--tg-text)' }}
              >
                {day.getDate()}
              </span>
              {hasDue && !isToday && (
                <div className="w-1 h-1 rounded-full" style={{ backgroundColor: 'var(--tg-accent)' }} />
              )}
            </button>
          );
        })}
      </div>

      {/* ── Day sections ── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto pb-bottom-nav">
        {weekDays.map((day, dayIdx) => {
          const ds      = dateToISO(day);
          const isToday = ds === today;
          const isPast  = ds < today;
          const header  = formatDayHeader(day);

          const dayLessons = schedule
            .filter(l => l.dayOfWeek === dayIdx)
            .sort((a, b) => a.lessonNumber - b.lessonNumber);

          // Homework due on this day
          const dueToday = homeworks.filter(hw => hw.deadline === ds);

          // For overdue items: collect and show on today's section only
          const overdueItems = isToday
            ? homeworks.filter(hw => !hw.isDone && isOverdue(hw.deadline))
            : [];

          if (dayLessons.length === 0 && dueToday.length === 0 && overdueItems.length === 0) {
            return null; // skip empty days
          }

          return (
            <div
              key={ds}
              id={`day-${ds}`}
              ref={isToday ? todayRef : undefined}
              className="mb-2"
            >
              {/* Day header */}
              <div
                className="px-4 pt-4 pb-1.5 flex items-center gap-2"
              >
                <div
                  className="w-7 h-7 rounded-xl flex items-center justify-center text-[13px] font-bold flex-shrink-0"
                  style={{
                    backgroundColor: isToday ? 'var(--tg-accent)' : 'transparent',
                    color:           isToday ? 'var(--tg-accent-text)' : isPast ? 'var(--tg-hint)' : 'var(--tg-text)',
                  }}
                >
                  {day.getDate()}
                </div>
                <span
                  className="text-[12px] font-bold uppercase tracking-widest"
                  style={{ color: isToday ? 'var(--tg-accent)' : isPast ? 'var(--tg-hint)' : 'var(--tg-text)' }}
                >
                  {header.full}
                  {isToday && ' · Сегодня'}
                </span>
              </div>

              {/* Overdue notice (today only) */}
              {overdueItems.length > 0 && (
                <div className="mx-3 mb-2 px-3 py-2 rounded-2xl flex items-center gap-2"
                  style={{ backgroundColor: 'rgba(255,59,48,0.10)' }}>
                  <span className="text-[12px]" style={{ color: '#ff3b30' }}>
                    ⚠️ {overdueItems.length} просроченных задани{overdueItems.length === 1 ? 'е' : 'я'}
                  </span>
                </div>
              )}

              {/* Lessons */}
              <div
                className="mx-3 rounded-2xl overflow-hidden"
                style={{ backgroundColor: 'var(--tg-secondary-bg)' }}
              >
                {dayLessons.map((lesson, li) => {
                  const style      = getSubjectStyle(lesson.subject);
                  const lessonHW   = homeworks.filter(
                    hw => hw.subject === lesson.subject && hw.deadline === ds,
                  );
                  const isLast     = li === dayLessons.length - 1 && lessonHW.length === 0;

                  return (
                    <div key={`${ds}-${lesson.lessonNumber}`}>
                      {li > 0 && (
                        <div className="mx-3 h-px" style={{ backgroundColor: 'rgba(142,142,147,0.12)' }} />
                      )}

                      {/* Lesson row */}
                      <div className="flex items-center gap-3 px-3 py-2.5">
                        {/* Lesson number */}
                        <div
                          className="w-6 h-6 rounded-lg flex items-center justify-center text-[11px] font-bold flex-shrink-0"
                          style={{ backgroundColor: style.bg, color: style.color }}
                        >
                          {lesson.lessonNumber}
                        </div>

                        {/* Time */}
                        <span
                          className="text-[11px] font-medium w-[38px] flex-shrink-0 tabular-nums"
                          style={{ color: 'var(--tg-hint)' }}
                        >
                          {lesson.startTime}
                        </span>

                        {/* Subject */}
                        <span className="flex-1 text-[14px] font-medium" style={{ color: 'var(--tg-text)' }}>
                          {style.emoji} {lesson.subject}
                        </span>

                        {/* HW count badge */}
                        {lessonHW.length > 0 && (
                          <span
                            className="text-[10px] font-bold px-1.5 py-0.5 rounded-full"
                            style={{
                              backgroundColor: lessonHW.every(h => h.isDone)
                                ? 'rgba(52,199,89,0.18)'
                                : style.badge,
                              color: lessonHW.every(h => h.isDone) ? '#34c759' : style.color,
                            }}
                          >
                            {lessonHW.every(h => h.isDone) ? '✓' : `ДЗ ${lessonHW.length}`}
                          </span>
                        )}
                      </div>

                      {/* Inline HW mini-cards */}
                      {lessonHW.map(hw => (
                        <MiniHWCard
                          key={hw.id}
                          hw={hw}
                          style={style}
                          onToggle={onToggle}
                          onOpen={onOpen}
                        />
                      ))}
                    </div>
                  );
                })}

                {/* Homework due today but not matched to a lesson */}
                {dueToday
                  .filter(hw => !dayLessons.some(l => l.subject === hw.subject))
                  .map((hw, idx, arr) => (
                    <div key={hw.id}>
                      {(dayLessons.length > 0 || idx > 0) && (
                        <div className="mx-3 h-px" style={{ backgroundColor: 'rgba(142,142,147,0.12)' }} />
                      )}
                      <div className="px-3 py-1.5">
                        <span
                          className="text-[10px] font-bold uppercase tracking-widest"
                          style={{ color: 'var(--tg-hint)' }}
                        >
                          Сдать сегодня
                        </span>
                      </div>
                      <MiniHWCard
                        hw={hw}
                        style={getSubjectStyle(hw.subject)}
                        onToggle={onToggle}
                        onOpen={onOpen}
                      />
                    </div>
                  ))}
              </div>
            </div>
          );
        })}

        {/* Empty state when no lessons/hw for the whole week */}
        {weekDays.every((day, i) => {
          const ds = dateToISO(day);
          return schedule.filter(l => l.dayOfWeek === i).length === 0
            && homeworks.filter(hw => hw.deadline === ds).length === 0;
        }) && (
          <div className="flex flex-col items-center justify-center py-20 px-6 text-center">
            <span className="text-5xl mb-4">📅</span>
            <p className="text-[16px] font-semibold mb-1" style={{ color: 'var(--tg-text)' }}>
              Расписание не загружено
            </p>
            <p className="text-[13px]" style={{ color: 'var(--tg-hint)' }}>
              Задай расписание через бота командой /schedule
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Mini homework card (inline in schedule) ───────────────────────────────────

function MiniHWCard({
  hw, style, onToggle, onOpen,
}: {
  hw:       HomeworkWithStatus;
  style:    ReturnType<typeof getSubjectStyle>;
  onToggle: (id: string) => void;
  onOpen:   (hw: HomeworkWithStatus) => void;
}) {
  return (
    <div
      className="mx-3 mb-2 rounded-xl overflow-hidden"
      style={{
        backgroundColor: hw.isDone ? 'rgba(142,142,147,0.08)' : style.bg,
        borderLeft:      `3px solid ${hw.isDone ? 'rgba(142,142,147,0.25)' : style.color}`,
        opacity:         hw.isDone ? 0.6 : 1,
      }}
    >
      <button
        className="w-full text-left px-3 py-2 flex items-start gap-2"
        onClick={() => onOpen(hw)}
      >
        {/* Checkbox */}
        <button
          onPointerDown={e => e.stopPropagation()}
          onClick={e => { e.stopPropagation(); onToggle(hw.id); }}
          className="mt-0.5 w-[18px] h-[18px] rounded-full border-2 flex-shrink-0
                     flex items-center justify-center transition-all active:scale-90"
          style={
            hw.isDone
              ? { backgroundColor: style.color, borderColor: style.color }
              : { borderColor: style.color + '99' }
          }
        >
          {hw.isDone && <Check size={10} color="#fff" strokeWidth={3} />}
        </button>

        <p
          className="flex-1 text-[13px] leading-snug"
          style={{
            color:          'var(--tg-text)',
            textDecoration: hw.isDone ? 'line-through' : 'none',
          }}
        >
          {hw.description.length > 90
            ? hw.description.slice(0, 90) + '…'
            : hw.description}
        </p>
      </button>
    </div>
  );
}

// ── Skeleton loader ───────────────────────────────────────────────────────────

function ScheduleSkeleton() {
  return (
    <div className="px-3 pt-4 space-y-3">
      {[5, 4, 6, 5].map((lines, di) => (
        <div key={di}>
          <div
            className="h-3 w-32 rounded-full mb-3 animate-pulse"
            style={{ backgroundColor: 'var(--tg-secondary-bg)' }}
          />
          <div
            className="rounded-2xl overflow-hidden animate-pulse"
            style={{ backgroundColor: 'var(--tg-secondary-bg)', height: `${lines * 44}px` }}
          />
        </div>
      ))}
    </div>
  );
}
