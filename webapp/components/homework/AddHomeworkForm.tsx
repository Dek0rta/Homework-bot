'use client';

import { useState, useRef, useEffect }           from 'react';
import { AnimatePresence, motion }               from 'framer-motion';
import { Camera, X, Loader2, CheckCircle2, Trash2, AlertCircle } from 'lucide-react';
import { AddHomeworkData, Homework }             from '@/types';
import { SUBJECTS, getSubjectStyle }             from '@/lib/subjects';
import { todayISO, getNextSchoolDay }            from '@/lib/dateUtils';
import PreviewCard                               from './PreviewCard';

interface AddHomeworkFormProps {
  onSubmit:          (data: AddHomeworkData) => Promise<void>;
  /** If provided — form is in EDIT mode */
  initialData?:      Homework;
  /** Called when user confirms deletion (edit mode only) */
  onDelete?:         () => Promise<void>;
  /** Called to cancel edit without saving */
  onCancel?:         () => void;
  /**
   * Per-field AI confidence (0–1).
   * Fields with confidence < 0.8 receive a yellow "double-check" warning.
   */
  fieldConfidence?:  Partial<Record<'subject' | 'description' | 'deadline', number>>;
}

export default function AddHomeworkForm({
  onSubmit,
  initialData,
  onDelete,
  onCancel,
  fieldConfidence,
}: AddHomeworkFormProps) {
  const isEdit = !!initialData;

  const [subject,     setSubject]     = useState(initialData?.subject     ?? '');
  const [description, setDescription] = useState(initialData?.description ?? '');
  const [deadline,    setDeadline]    = useState(
    initialData?.deadline ?? (!isEdit ? getNextSchoolDay() : ''),
  );
  const [keepPhotos,  setKeepPhotos]  = useState<string[]>(initialData?.photos ?? []);
  const [newFiles,    setNewFiles]    = useState<File[]>([]);
  const [newPreviews, setNewPreviews] = useState<string[]>([]);
  const [submitting,  setSubmitting]  = useState(false);
  const [deleting,    setDeleting]    = useState(false);
  const [error,       setError]       = useState<string | null>(null);
  const [success,     setSuccess]     = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const fileRef = useRef<HTMLInputElement>(null);
  const today   = todayISO();

  useEffect(() => () => newPreviews.forEach(URL.revokeObjectURL), []);

  const totalPhotos = keepPhotos.length + newFiles.length;

  const addPhotos = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (totalPhotos + files.length > 5) { setError('Максимум 5 фотографий'); return; }
    const urls = files.map(f => URL.createObjectURL(f));
    setNewFiles(prev    => [...prev, ...files]);
    setNewPreviews(prev => [...prev, ...urls]);
    if (fileRef.current) fileRef.current.value = '';
  };

  const removeKeepPhoto = (i: number) =>
    setKeepPhotos(prev => prev.filter((_, idx) => idx !== i));

  const removeNewPhoto = (i: number) => {
    URL.revokeObjectURL(newPreviews[i]);
    setNewFiles(prev    => prev.filter((_, idx) => idx !== i));
    setNewPreviews(prev => prev.filter((_, idx) => idx !== i));
  };

  // ── Validate → show preview (add mode) or submit directly (edit mode) ───
  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!subject)            { setError('Выбери предмет');          return; }
    if (!description.trim()) { setError('Добавь описание задания'); return; }
    if (!deadline)           { setError('Укажи дедлайн');           return; }
    if (!isEdit) {
      setShowPreview(true);
    } else {
      handleFinalSubmit();
    }
  };

  // ── Final API call (invoked from preview confirm or edit submit) ─────────
  const handleFinalSubmit = async () => {
    setSubmitting(true);
    try {
      await onSubmit({
        subject,
        description: description.trim(),
        deadline,
        photos:      newFiles,
        keepPhotos,
      });
      if (!isEdit) setSuccess(true);
    } catch {
      setError('Не удалось сохранить. Попробуй ещё раз.');
      setShowPreview(false);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!onDelete || !window.confirm('Удалить это задание?')) return;
    setDeleting(true);
    try { await onDelete(); }
    catch { setError('Не удалось удалить.'); setDeleting(false); }
  };

  /** True when the AI is unsure about a field (confidence below 0.8) */
  const lowConf = (f: 'subject' | 'description' | 'deadline') =>
    fieldConfidence?.[f] !== undefined && (fieldConfidence[f] as number) < 0.8;

  // ── Success screen ────────────────────────────────────────────────────────
  if (success) {
    return (
      <div className="flex flex-col items-center justify-center py-20 px-6 text-center min-h-[60vh]">
        <motion.div
          initial={{ scale: 0.4, opacity: 0 }}
          animate={{ scale: 1,   opacity: 1 }}
          transition={{ type: 'spring', damping: 14, stiffness: 280 }}
        >
          <CheckCircle2 size={64} className="mb-5" style={{ color: 'var(--tg-accent)' }} />
        </motion.div>
        <p className="text-[18px] font-bold mb-1" style={{ color: 'var(--tg-text)' }}>
          Задание добавлено!
        </p>
        <p className="text-[13px]" style={{ color: 'var(--tg-hint)' }}>
          Все одноклассники его видят
        </p>
      </div>
    );
  }

  // ── Form / Preview (animated swap) ───────────────────────────────────────
  return (
    <div className="relative overflow-hidden">
      <AnimatePresence mode="wait" initial={false}>

        {showPreview ? (
          <PreviewCard
            key="preview"
            subject={subject}
            description={description}
            deadline={deadline}
            photoPreviews={[...keepPhotos, ...newPreviews]}
            onConfirm={handleFinalSubmit}
            onCancel={() => { setError(null); setShowPreview(false); }}
            submitting={submitting}
          />
        ) : (
          <motion.form
            key="form"
            onSubmit={handleFormSubmit}
            className="px-4 pt-4 pb-bottom-nav space-y-5"
            initial={{ x: '-25%', opacity: 0 }}
            animate={{ x: 0,      opacity: 1 }}
            exit={{    x: '-25%', opacity: 0 }}
            transition={{ type: 'spring', damping: 28, stiffness: 320 }}
          >

            {/* Cancel in edit mode */}
            {isEdit && onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="text-[14px] font-medium"
                style={{ color: 'var(--tg-accent)' }}
              >
                ← Назад
              </button>
            )}

            {/* ── Subject ── */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Label text="Предмет" />
                {lowConf('subject') && <ConfidenceHint />}
              </div>
              <div
                className="flex flex-wrap gap-2 p-2 rounded-2xl transition-all duration-200"
                style={lowConf('subject') ? {
                  border:          '2px solid rgba(255,204,0,0.65)',
                  backgroundColor: 'rgba(255,204,0,0.05)',
                } : {}}
              >
                {SUBJECTS.map(s => {
                  const st       = getSubjectStyle(s);
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
                        color:           selected ? '#fff'   : 'var(--tg-hint)',
                      }}
                    >
                      {st.emoji} {s}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* ── Description ── */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Label text="Описание задания" />
                {lowConf('description') && <ConfidenceHint />}
              </div>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Что нужно сделать? Параграфы, задачи, страницы…"
                rows={4}
                className="w-full px-4 py-3 rounded-2xl text-[14px] resize-none border focus:outline-none transition-all duration-200"
                style={{
                  backgroundColor: 'var(--tg-secondary-bg)',
                  color:           'var(--tg-text)',
                  borderColor:     lowConf('description') ? 'rgba(255,204,0,0.65)' : 'rgba(142,142,147,0.25)',
                  borderWidth:     lowConf('description') ? '2px' : '1px',
                }}
              />
            </div>

            {/* ── Deadline ── */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Label text="Дедлайн" />
                {lowConf('deadline') && <ConfidenceHint />}
              </div>
              <input
                type="date"
                value={deadline}
                min={isEdit ? undefined : today}
                onChange={e => setDeadline(e.target.value)}
                className="w-full px-4 py-3 rounded-2xl text-[14px] border focus:outline-none transition-all duration-200"
                style={{
                  backgroundColor: 'var(--tg-secondary-bg)',
                  color:           'var(--tg-text)',
                  borderColor:     lowConf('deadline') ? 'rgba(255,204,0,0.65)' : 'rgba(142,142,147,0.25)',
                  borderWidth:     lowConf('deadline') ? '2px' : '1px',
                }}
              />
            </div>

            {/* ── Photos ── */}
            <div>
              <Label text={`Фото (${totalPhotos}/5)`} />
              <div className="flex flex-wrap gap-2 mt-2">

                {keepPhotos.map((src, i) => (
                  <div key={`k-${i}`} className="relative w-[72px] h-[72px] rounded-2xl overflow-hidden">
                    <img src={src} alt="" className="w-full h-full object-cover" />
                    <button
                      type="button"
                      onClick={() => removeKeepPhoto(i)}
                      className="absolute top-1 right-1 w-5 h-5 bg-black/60 rounded-full flex items-center justify-center"
                    >
                      <X size={10} color="#fff" />
                    </button>
                  </div>
                ))}

                {newPreviews.map((url, i) => (
                  <div key={`n-${i}`} className="relative w-[72px] h-[72px] rounded-2xl overflow-hidden">
                    <img src={url} alt="" className="w-full h-full object-cover" />
                    <button
                      type="button"
                      onClick={() => removeNewPhoto(i)}
                      className="absolute top-1 right-1 w-5 h-5 bg-black/60 rounded-full flex items-center justify-center"
                    >
                      <X size={10} color="#fff" />
                    </button>
                  </div>
                ))}

                {totalPhotos < 5 && (
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
              <input ref={fileRef} type="file" accept="image/*" multiple onChange={addPhotos} className="hidden" />
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

            {/* Submit: edit → save directly; add → go to preview */}
            <button
              type="submit"
              disabled={submitting || deleting}
              className="w-full py-4 rounded-2xl font-bold text-[15px] text-white
                         flex items-center justify-center gap-2
                         transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
              style={{ backgroundColor: 'var(--tg-accent)' }}
            >
              {submitting
                ? <><Loader2 size={18} className="animate-spin" /> Сохранение…</>
                : isEdit ? 'Сохранить изменения' : 'Далее →'
              }
            </button>

            {/* Delete (edit mode only) */}
            {isEdit && onDelete && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting || submitting}
                className="w-full py-3.5 rounded-2xl font-semibold text-[15px]
                           flex items-center justify-center gap-2
                           transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
                style={{ backgroundColor: 'rgba(255,59,48,0.12)', color: '#ff3b30' }}
              >
                {deleting
                  ? <><Loader2 size={16} className="animate-spin" /> Удаление…</>
                  : <><Trash2 size={16} /> Удалить задание</>
                }
              </button>
            )}
          </motion.form>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Label({ text }: { text: string }) {
  return (
    <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--tg-hint)' }}>
      {text}
    </p>
  );
}

/** Yellow chip shown when AI confidence is below threshold */
function ConfidenceHint() {
  return (
    <div className="relative group inline-flex items-center">
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-semibold cursor-help"
        style={{ backgroundColor: 'rgba(255,204,0,0.15)', color: '#b8860b' }}
      >
        <AlertCircle size={11} />
        Проверь
      </span>
      {/* Tooltip */}
      <div
        className="absolute bottom-full left-0 mb-1.5 px-3 py-2 rounded-xl text-[12px]
                   whitespace-nowrap pointer-events-none shadow-lg z-50
                   opacity-0 group-hover:opacity-100 transition-opacity duration-150"
        style={{ backgroundColor: '#1c1c1e', color: '#fff' }}
      >
        ИИ не уверен — пожалуйста, проверь это поле
      </div>
    </div>
  );
}
