'use client';

import { useEffect, useState }                            from 'react';
import { X, Calendar, Camera, Check, ChevronLeft }        from 'lucide-react';
import { HomeworkWithStatus }                             from '@/types';
import { getSubjectStyle }                                from '@/lib/subjects';
import { formatDeadlineLong, getDaysLeft, isOverdue }     from '@/lib/dateUtils';

interface HomeworkModalProps {
  homework: HomeworkWithStatus;
  onClose:  () => void;
  onToggle: () => void;
}

export default function HomeworkModal({
  homework,
  onClose,
  onToggle,
}: HomeworkModalProps) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const style   = getSubjectStyle(homework.subject);
  const overdue = isOverdue(homework.deadline) && !homework.isDone;
  const days    = getDaysLeft(homework.deadline);

  // Lock body scroll
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <>
      {/* ── Backdrop ── */}
      <div
        className="fixed inset-0 z-40 bg-black/50 animate-fade-in"
        onClick={onClose}
      />

      {/* ── Bottom sheet ── */}
      <div
        className="fixed inset-x-0 bottom-0 z-50 flex flex-col rounded-t-3xl overflow-hidden animate-slide-up"
        style={{
          backgroundColor: 'var(--tg-secondary-bg)',
          maxHeight: '88vh',
        }}
      >
        {/* Handle */}
        <div className="flex justify-center pt-2.5 pb-0 flex-shrink-0">
          <div className="w-9 h-1 rounded-full" style={{ backgroundColor: 'var(--tg-hint)', opacity: 0.35 }} />
        </div>

        {/* Header */}
        <div className="flex items-start gap-3 px-5 pt-3 pb-2 flex-shrink-0">
          {/* Subject icon circle */}
          <div
            className="w-11 h-11 rounded-2xl flex items-center justify-center text-xl flex-shrink-0"
            style={{ backgroundColor: style.bg }}
          >
            {style.emoji}
          </div>

          <div className="flex-1 min-w-0 pt-0.5">
            <span
              className="block text-[10px] font-bold uppercase tracking-widest mb-0.5"
              style={{ color: style.color }}
            >
              {homework.subject}
            </span>
            <p
              className="text-[15px] font-semibold leading-tight line-clamp-2"
              style={{ color: 'var(--tg-text)' }}
            >
              {homework.description.split('\n')[0]}
            </p>
          </div>

          <button
            onClick={onClose}
            className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center"
            style={{ backgroundColor: 'rgba(142,142,147,0.18)' }}
          >
            <X size={15} style={{ color: 'var(--tg-hint)' }} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 pt-1 pb-4" style={{ WebkitOverflowScrolling: 'touch' } as React.CSSProperties}>
          {/* Deadline row */}
          <div
            className="flex items-center gap-2.5 p-3 rounded-2xl mb-4"
            style={{
              backgroundColor: overdue ? 'rgba(255,59,48,0.12)' : 'var(--tg-bg)',
            }}
          >
            <Calendar
              size={16}
              style={{ color: overdue ? '#ff3b30' : 'var(--tg-accent)', flexShrink: 0 }}
            />
            <div>
              <p
                className="text-[13px] font-semibold"
                style={{ color: overdue ? '#ff3b30' : 'var(--tg-text)' }}
              >
                {formatDeadlineLong(homework.deadline)}
              </p>
              {!homework.isDone && days !== undefined && (
                <p className="text-[11px]" style={{ color: overdue ? '#ff3b30' : 'var(--tg-hint)' }}>
                  {days === 0
                    ? 'Сдать сегодня!'
                    : days < 0
                      ? `Просрочено на ${Math.abs(days)} дн.`
                      : `Осталось ${days} дн.`}
                </p>
              )}
            </div>
          </div>

          {/* Full description */}
          <div className="mb-5">
            <SectionLabel text="Задание" />
            <p
              className="text-[14px] leading-relaxed whitespace-pre-wrap"
              style={{ color: 'var(--tg-text)' }}
            >
              {homework.description}
            </p>
          </div>

          {/* Photos grid */}
          {homework.photos.length > 0 && (
            <div className="mb-4">
              <SectionLabel text={`Фото · ${homework.photos.length}`} Icon={Camera} />
              <div className="grid grid-cols-3 gap-1.5">
                {homework.photos.map((url, i) => (
                  <button
                    key={i}
                    onClick={() => setLightboxIndex(i)}
                    className="aspect-square rounded-xl overflow-hidden"
                    style={{ backgroundColor: 'var(--tg-bg)' }}
                  >
                    <img
                      src={url}
                      alt={`Фото ${i + 1}`}
                      className="w-full h-full object-cover"
                    />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* CTA button */}
        <div
          className="flex-shrink-0 px-5 pt-3 pb-safe border-t"
          style={{ borderColor: 'rgba(142,142,147,0.2)' }}
        >
          <button
            onClick={onToggle}
            className="w-full py-3.5 rounded-2xl font-semibold text-[15px]
                       flex items-center justify-center gap-2
                       transition-all duration-150 active:scale-[0.98]"
            style={{
              backgroundColor: homework.isDone ? 'rgba(142,142,147,0.2)' : style.color,
              color:           homework.isDone ? 'var(--tg-hint)' : '#fff',
            }}
          >
            {homework.isDone ? (
              'Снять отметку'
            ) : (
              <>
                <Check size={18} strokeWidth={2.5} />
                Отметить выполненным
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── Lightbox ── */}
      {lightboxIndex !== null && (
        <div
          className="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center animate-fade-in"
          onClick={() => setLightboxIndex(null)}
        >
          {/* Prev */}
          {lightboxIndex > 0 && (
            <button
              onClick={e => { e.stopPropagation(); setLightboxIndex(i => i! - 1); }}
              className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10
                         bg-white/20 rounded-full flex items-center justify-center"
            >
              <ChevronLeft size={20} color="#fff" />
            </button>
          )}

          <img
            src={homework.photos[lightboxIndex]}
            alt={`Фото ${lightboxIndex + 1}`}
            className="max-w-full max-h-full object-contain px-16"
            onClick={e => e.stopPropagation()}
          />

          {/* Next */}
          {lightboxIndex < homework.photos.length - 1 && (
            <button
              onClick={e => { e.stopPropagation(); setLightboxIndex(i => i! + 1); }}
              className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10
                         bg-white/20 rounded-full flex items-center justify-center"
            >
              <ChevronLeft size={20} color="#fff" className="rotate-180" />
            </button>
          )}

          {/* Counter */}
          <span className="absolute bottom-6 left-1/2 -translate-x-1/2 text-white/60 text-sm">
            {lightboxIndex + 1} / {homework.photos.length}
          </span>
        </div>
      )}
    </>
  );
}

function SectionLabel({
  text,
  Icon,
}: {
  text: string;
  Icon?: React.ComponentType<{ size: number }>;
}) {
  return (
    <div className="flex items-center gap-1.5 mb-2">
      {Icon && <Icon size={11} />}
      <p
        className="text-[10px] font-bold uppercase tracking-widest"
        style={{ color: 'var(--tg-hint)' }}
      >
        {text}
      </p>
    </div>
  );
}
