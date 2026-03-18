'use client';

import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { getSubjectStyle } from '@/lib/subjects';
import { formatDeadlineLong, getDaysLeft } from '@/lib/dateUtils';

interface PreviewCardProps {
  subject:       string;
  description:   string;
  deadline:      string;
  photoPreviews: string[];
  onConfirm:     () => void;
  onCancel:      () => void;
  submitting?:   boolean;
}

export default function PreviewCard({
  subject, description, deadline, photoPreviews,
  onConfirm, onCancel, submitting,
}: PreviewCardProps) {
  const st       = getSubjectStyle(subject);
  const daysLeft = getDaysLeft(deadline);

  const urgencyLabel = daysLeft < 0 ? 'Просрочено!'
    : daysLeft === 0 ? 'Сдать сегодня'
    : daysLeft === 1 ? 'Завтра'
    : `Через ${daysLeft} дн.`;

  const urgencyStyle = {
    backgroundColor: daysLeft < 0
      ? 'rgba(255,59,48,0.12)'
      : daysLeft <= 1
      ? 'rgba(255,149,0,0.12)'
      : 'rgba(52,199,89,0.12)',
    color: daysLeft < 0 ? '#ff3b30' : daysLeft <= 1 ? '#ff9500' : '#34c759',
  };

  return (
    <motion.div
      className="px-4 pt-5 pb-bottom-nav space-y-5"
      initial={{ x: '35%', opacity: 0 }}
      animate={{ x: 0,     opacity: 1 }}
      exit={{    x: '35%', opacity: 0 }}
      transition={{ type: 'spring', damping: 28, stiffness: 320 }}
    >
      {/* Section label */}
      <div>
        <p
          className="text-[10px] font-bold uppercase tracking-widest mb-1"
          style={{ color: 'var(--tg-hint)' }}
        >
          Предпросмотр
        </p>
        <p className="text-[22px] font-bold" style={{ color: 'var(--tg-text)' }}>
          Всё верно?
        </p>
        <p className="text-[13px] mt-0.5" style={{ color: 'var(--tg-hint)' }}>
          Проверь данные перед отправкой
        </p>
      </div>

      {/* Card */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{
          backgroundColor: 'var(--tg-secondary-bg)',
          border: '1px solid rgba(142,142,147,0.2)',
          boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
        }}
      >
        <div className="h-1.5" style={{ backgroundColor: st.color }} />
        <div className="p-4 space-y-3">

          {/* Subject + urgency row */}
          <div className="flex items-center justify-between gap-2">
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-[12px] font-semibold"
              style={{ backgroundColor: st.bg, color: st.color, border: `1px solid ${st.border}` }}
            >
              {st.emoji} {subject}
            </span>
            <span
              className="text-[12px] font-medium px-2.5 py-1 rounded-xl flex-shrink-0"
              style={urgencyStyle}
            >
              {urgencyLabel}
            </span>
          </div>

          {/* Description */}
          <p className="text-[14px] leading-relaxed" style={{ color: 'var(--tg-text)' }}>
            {description}
          </p>

          {/* Deadline */}
          <p className="text-[12px]" style={{ color: 'var(--tg-hint)' }}>
            {formatDeadlineLong(deadline)}
          </p>

          {/* Photo previews */}
          {photoPreviews.length > 0 && (
            <div className="flex gap-2 flex-wrap">
              {photoPreviews.map((url, i) => (
                <img
                  key={i}
                  src={url}
                  alt=""
                  className="w-[64px] h-[64px] rounded-xl object-cover"
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Confirm */}
      <button
        onClick={onConfirm}
        disabled={submitting}
        className="w-full py-4 rounded-2xl font-bold text-[15px] text-white
                   flex items-center justify-center gap-2
                   transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
        style={{ backgroundColor: 'var(--tg-accent)' }}
      >
        {submitting
          ? <><Loader2 size={18} className="animate-spin" /> Сохранение…</>
          : '✓ Подтвердить и добавить'
        }
      </button>

      {/* Cancel — back to form */}
      <button
        onClick={onCancel}
        disabled={submitting}
        className="w-full py-3.5 rounded-2xl font-semibold text-[15px]
                   flex items-center justify-center gap-2
                   transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
        style={{ backgroundColor: 'rgba(142,142,147,0.12)', color: 'var(--tg-text)' }}
      >
        ← Изменить
      </button>
    </motion.div>
  );
}
