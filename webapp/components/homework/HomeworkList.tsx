'use client';

import { HomeworkWithStatus } from '@/types';
import { todayISO }           from '@/lib/dateUtils';
import HomeworkCard           from './HomeworkCard';

interface HomeworkListProps {
  homeworks: HomeworkWithStatus[];
  loading: boolean;
  error: string | null;
  onToggle: (id: string) => void;
  emptyMessage: string;
}

export default function HomeworkList({
  homeworks,
  loading,
  error,
  onToggle,
  emptyMessage,
}: HomeworkListProps) {
  // ── Skeleton loader ───────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="px-3 pt-4 pb-bottom-nav space-y-2.5">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-[88px] rounded-2xl animate-pulse"
            style={{ backgroundColor: 'var(--tg-secondary-bg)', opacity: 1 - i * 0.18 }}
          />
        ))}
      </div>
    );
  }

  // ── Error state ───────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24 px-6 text-center">
        <span className="text-5xl mb-4">⚠️</span>
        <p className="text-[15px] font-medium mb-1" style={{ color: 'var(--tg-text)' }}>
          Ошибка загрузки
        </p>
        <p className="text-[13px]" style={{ color: 'var(--tg-hint)' }}>{error}</p>
      </div>
    );
  }

  // ── Empty state ───────────────────────────────────────────────────────────
  if (homeworks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 px-6 text-center">
        <span className="text-6xl mb-5">✅</span>
        <p className="text-[16px] font-semibold mb-1" style={{ color: 'var(--tg-text)' }}>
          {emptyMessage}
        </p>
        <p className="text-[13px]" style={{ color: 'var(--tg-hint)' }}>
          Отличная работа!
        </p>
      </div>
    );
  }

  // ── Group homeworks ───────────────────────────────────────────────────────
  const today   = todayISO();
  const overdue = homeworks.filter(hw => !hw.isDone && hw.deadline < today);
  const active  = homeworks.filter(hw => !hw.isDone && hw.deadline >= today);
  const done    = homeworks.filter(hw =>  hw.isDone);

  return (
    <div className="pt-3 pb-bottom-nav">
      {overdue.length > 0 && (
        <Section label={`⚠️ Просрочено · ${overdue.length}`}>
          {overdue.map(hw => (
            <HomeworkCard key={hw.id} homework={hw} onToggle={onToggle} />
          ))}
        </Section>
      )}

      {active.length > 0 && (
        <Section label={overdue.length > 0 ? `📋 Активные · ${active.length}` : undefined}>
          {active.map(hw => (
            <HomeworkCard key={hw.id} homework={hw} onToggle={onToggle} />
          ))}
        </Section>
      )}

      {done.length > 0 && (
        <Section label={`✅ Выполнено · ${done.length}`}>
          {done.map(hw => (
            <HomeworkCard key={hw.id} homework={hw} onToggle={onToggle} />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-3">
      {label && (
        <p
          className="px-4 pb-1.5 text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: 'var(--tg-hint)' }}
        >
          {label}
        </p>
      )}
      {children}
    </div>
  );
}
