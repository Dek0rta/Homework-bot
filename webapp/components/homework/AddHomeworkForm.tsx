'use client';

import { useState, useRef, useEffect } from 'react';
import { Camera, X, Loader2, CheckCircle2 } from 'lucide-react';
import { AddHomeworkData } from '@/types';
import { SUBJECTS, getSubjectStyle } from '@/lib/subjects';
import { todayISO } from '@/lib/dateUtils';

interface AddHomeworkFormProps {
  onSubmit: (data: AddHomeworkData) => Promise<void>;
}

export default function AddHomeworkForm({ onSubmit }: AddHomeworkFormProps) {
  const [subject,     setSubject]     = useState('');
  const [description, setDescription] = useState('');
  const [deadline,    setDeadline]    = useState('');
  const [photos,      setPhotos]      = useState<File[]>([]);
  const [previews,    setPreviews]    = useState<string[]>([]);
  const [submitting,  setSubmitting]  = useState(false);
  const [error,       setError]       = useState<string | null>(null);
  const [success,     setSuccess]     = useState(false);

  const fileRef = useRef<HTMLInputElement>(null);
  const today   = todayISO();

  // Cleanup blob URLs on unmount
  useEffect(() => {
    return () => previews.forEach(URL.revokeObjectURL);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addPhotos = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (photos.length + files.length > 5) {
      setError('Максимум 5 фотографий');
      return;
    }
    const urls = files.map(f => URL.createObjectURL(f));
    setPhotos(prev => [...prev, ...files]);
    setPreviews(prev => [...prev, ...urls]);
    // Reset input so same file can be re-selected
    if (fileRef.current) fileRef.current.value = '';
  };

  const removePhoto = (i: number) => {
    URL.revokeObjectURL(previews[i]);
    setPhotos(prev => prev.filter((_, idx) => idx !== i));
    setPreviews(prev => prev.filter((_, idx) => idx !== i));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!subject)           { setError('Выбери предмет'); return; }
    if (!description.trim()) { setError('Добавь описание задания'); return; }
    if (!deadline)           { setError('Укажи дедлайн'); return; }

    setSubmitting(true);
    try {
      await onSubmit({ subject, description: description.trim(), deadline, photos });
      setSuccess(true);
    } catch {
      setError('Не удалось сохранить. Попробуй ещё раз.');
    } finally {
      setSubmitting(false);
    }
  };

  // ── Success screen ──────────────────────────────────────────────────────
  if (success) {
    return (
      <div className="flex flex-col items-center justify-center py-20 px-6 text-center min-h-[60vh]">
        <CheckCircle2
          size={64}
          className="mb-5"
          style={{ color: 'var(--tg-accent)' }}
        />
        <p className="text-[18px] font-bold mb-1" style={{ color: 'var(--tg-text)' }}>
          Задание добавлено!
        </p>
        <p className="text-[13px]" style={{ color: 'var(--tg-hint)' }}>
          Все одноклассники его видят
        </p>
      </div>
    );
  }

  // ── Form ────────────────────────────────────────────────────────────────
  return (
    <form onSubmit={handleSubmit} className="px-4 pt-4 pb-bottom-nav space-y-5">

      {/* Subject chips */}
      <div>
        <Label text="Предмет" />
        <div className="flex flex-wrap gap-2">
          {SUBJECTS.map(s => {
            const st      = getSubjectStyle(s);
            const selected = subject === s;
            return (
              <button
                key={s}
                type="button"
                onClick={() => setSubject(s)}
                className="px-3 py-1.5 rounded-xl text-[13px] font-medium
                           transition-all duration-150 active:scale-95"
                style={{
                  backgroundColor: selected ? st.color : 'var(--tg-secondary-bg)',
                  color:           selected ? '#fff'    : 'var(--tg-hint)',
                }}
              >
                {st.emoji} {s}
              </button>
            );
          })}
        </div>
      </div>

      {/* Description */}
      <div>
        <Label text="Описание задания" />
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Что нужно сделать? Параграфы, задачи, страницы…"
          rows={4}
          className="w-full px-4 py-3 rounded-2xl text-[14px] resize-none
                     border focus:outline-none transition-colors"
          style={{
            backgroundColor: 'var(--tg-secondary-bg)',
            color:           'var(--tg-text)',
            borderColor:     'rgba(142,142,147,0.25)',
          }}
        />
      </div>

      {/* Deadline */}
      <div>
        <Label text="Дедлайн" />
        <input
          type="date"
          value={deadline}
          min={today}
          onChange={e => setDeadline(e.target.value)}
          className="w-full px-4 py-3 rounded-2xl text-[14px] border
                     focus:outline-none transition-colors"
          style={{
            backgroundColor: 'var(--tg-secondary-bg)',
            color:           'var(--tg-text)',
            borderColor:     'rgba(142,142,147,0.25)',
          }}
        />
      </div>

      {/* Photos */}
      <div>
        <Label text={`Фото (необязательно · ${photos.length}/5)`} />
        <div className="flex flex-wrap gap-2">
          {previews.map((url, i) => (
            <div key={i} className="relative w-[72px] h-[72px] rounded-2xl overflow-hidden">
              <img src={url} alt="" className="w-full h-full object-cover" />
              <button
                type="button"
                onClick={() => removePhoto(i)}
                className="absolute top-1 right-1 w-5 h-5 bg-black/60 rounded-full
                           flex items-center justify-center"
              >
                <X size={10} color="#fff" />
              </button>
            </div>
          ))}

          {photos.length < 5 && (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="w-[72px] h-[72px] rounded-2xl border-2 border-dashed
                         flex flex-col items-center justify-center gap-1
                         transition-opacity active:opacity-60"
              style={{ borderColor: 'rgba(142,142,147,0.4)', color: 'var(--tg-hint)' }}
            >
              <Camera size={20} />
              <span className="text-[9px] font-medium">Добавить</span>
            </button>
          )}
        </div>

        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          onChange={addPhotos}
          className="hidden"
        />
      </div>

      {/* Error */}
      {error && (
        <div
          className="px-4 py-3 rounded-2xl text-[13px]"
          style={{ backgroundColor: 'rgba(255,59,48,0.12)', color: '#ff3b30' }}
        >
          {error}
        </div>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={submitting}
        className="w-full py-4 rounded-2xl font-bold text-[15px] text-white
                   flex items-center justify-center gap-2
                   transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
        style={{ backgroundColor: 'var(--tg-accent)' }}
      >
        {submitting ? (
          <>
            <Loader2 size={18} className="animate-spin" />
            Сохранение…
          </>
        ) : (
          'Добавить задание'
        )}
      </button>
    </form>
  );
}

function Label({ text }: { text: string }) {
  return (
    <p
      className="text-[10px] font-bold uppercase tracking-widest mb-2"
      style={{ color: 'var(--tg-hint)' }}
    >
      {text}
    </p>
  );
}
