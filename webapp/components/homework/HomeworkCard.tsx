'use client';

import { useState }                                      from 'react';
import { Check, Camera, ChevronRight }                   from 'lucide-react';
import { HomeworkWithStatus }                            from '@/types';
import { getSubjectStyle }                               from '@/lib/subjects';
import { formatDeadlineShort, daysLeftLabel, isOverdue } from '@/lib/dateUtils';
import HomeworkModal                                     from './HomeworkModal';

interface HomeworkCardProps {
  homework: HomeworkWithStatus;
  onToggle: (id: string) => void;
  onEdit:   (hw: HomeworkWithStatus) => void;
}

export default function HomeworkCard({ homework, onToggle, onEdit }: HomeworkCardProps) {
  const [showModal, setShowModal] = useState(false);

  const style   = getSubjectStyle(homework.subject);
  const overdue = isOverdue(homework.deadline) && !homework.isDone;

  return (
    <>
      <div
        className="relative mx-3 mb-2.5 rounded-2xl overflow-hidden border transition-opacity duration-200"
        style={{
          backgroundColor: style.bg,
          borderColor:     style.border,
          opacity:         homework.isDone ? 0.55 : 1,
        }}
      >
        {/* Coloured left accent */}
        <div
          className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-full"
          style={{ backgroundColor: style.color }}
        />

        <div className="pl-5 pr-3 py-3.5 flex items-start gap-3">
          {/* Checkbox */}
          <button
            onPointerDown={e => e.stopPropagation()}
            onClick={e => { e.stopPropagation(); onToggle(homework.id); }}
            className="mt-[2px] flex-shrink-0 w-[22px] h-[22px] rounded-full border-2
                       flex items-center justify-center transition-all duration-200 active:scale-90"
            style={
              homework.isDone
                ? { backgroundColor: style.color, borderColor: style.color }
                : { borderColor: style.color + '99' }
            }
            aria-label="Отметить выполненным"
          >
            {homework.isDone && <Check size={12} color="#fff" strokeWidth={3} />}
          </button>

          {/* Main content */}
          <button className="flex-1 min-w-0 text-left" onClick={() => setShowModal(true)}>
            <span
              className="inline-block text-[10px] font-bold uppercase tracking-widest px-2 py-[2px] rounded-full mb-1.5"
              style={{ color: style.color, backgroundColor: style.badge }}
            >
              {style.emoji}&nbsp;{homework.subject}
            </span>

            <p
              className="text-[14px] leading-snug line-clamp-2"
              style={{ color: 'var(--tg-text)', textDecoration: homework.isDone ? 'line-through' : 'none' }}
            >
              {homework.description}
            </p>

            <div className="flex items-center gap-3 mt-2">
              <span
                className="text-[11px] font-medium"
                style={{ color: overdue ? '#ff3b30' : 'var(--tg-hint)' }}
              >
                {overdue ? '⚠️ ' : '📅 '}
                {formatDeadlineShort(homework.deadline)}
                {!homework.isDone && (
                  <span className="ml-1 text-[10px] opacity-75">
                    ({daysLeftLabel(homework.deadline)})
                  </span>
                )}
              </span>

              {homework.photos.length > 0 && (
                <span className="flex items-center gap-0.5 text-[11px]" style={{ color: 'var(--tg-hint)' }}>
                  <Camera size={11} />{homework.photos.length}
                </span>
              )}
            </div>
          </button>

          <button
            onClick={() => setShowModal(true)}
            className="flex-shrink-0 mt-1 opacity-30 active:opacity-60"
            style={{ color: 'var(--tg-hint)' }}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {showModal && (
        <HomeworkModal
          homework={homework}
          onClose={() => setShowModal(false)}
          onToggle={() => { onToggle(homework.id); setShowModal(false); }}
          onEdit={() => { setShowModal(false); onEdit(homework); }}
        />
      )}
    </>
  );
}
