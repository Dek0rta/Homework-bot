'use client';

import { useState, useEffect, useMemo }         from 'react';
import { AnimatePresence, motion }              from 'framer-motion';
import { useTelegram }                          from '@/hooks/useTelegram';
import { useHomework }                          from '@/hooks/useHomework';
import { useGrades }                            from '@/hooks/useGrades';
import { TabType, HomeworkWithStatus }          from '@/types';
import BottomNav                                from '@/components/layout/BottomNav';
import HomeworkList                             from '@/components/homework/HomeworkList';
import HomeworkModal                            from '@/components/homework/HomeworkModal';
import AddHomeworkForm                          from '@/components/homework/AddHomeworkForm';
import ScheduleView                             from '@/components/schedule/ScheduleView';
import LoadView                                 from '@/components/load/LoadView';
import GradesView                              from '@/components/grades/GradesView';
import Snackbar                                 from '@/components/ui/Snackbar';

interface SnackbarState {
  message:  string;
  hwId:     string | null;
}

export default function HomePage() {
  const [activeTab,  setActiveTab]  = useState<TabType>('schedule');
  const [editingHW,  setEditingHW]  = useState<HomeworkWithStatus | null>(null);
  const [previewHW,  setPreviewHW]  = useState<HomeworkWithStatus | null>(null);
  const [snackbar,   setSnackbar]   = useState<SnackbarState | null>(null);

  const { user, colorScheme, isReady, haptic } = useTelegram();

  const {
    homeworks, schedule, loading, error,
    toggleStatus, addNewHomework, updateExistingHomework, removeHomework,
    pendingCount,
  } = useHomework(user?.id ?? null);

  const {
    grades, targets, loading: gradesLoading,
    addGrade, removeGrade, setTarget,
  } = useGrades(user?.id ?? null);

  // Subjects for GradesView: unique from schedule + any subjects already in grades
  const gradeSubjects = useMemo(() => {
    const fromSchedule = [...new Set(schedule.map(l => l.subject))];
    const fromGrades   = [...new Set(grades.map(g => g.subject))];
    return [...new Set([...fromSchedule, ...fromGrades])].sort((a, b) => a.localeCompare(b, 'ru'));
  }, [schedule, grades]);

  // Sync Telegram dark mode
  useEffect(() => {
    document.documentElement.classList.toggle('dark', colorScheme === 'dark');
  }, [colorScheme]);

  const handleTabChange = (tab: TabType) => { haptic('light'); setActiveTab(tab); };
  const handleToggle    = (id: string)   => { haptic('medium'); toggleStatus(id); };
  const handleEdit      = (hw: HomeworkWithStatus) => { haptic('light'); setEditingHW(hw); };

  // ── Loading splash ─────────────────────────────────────────────────────────
  if (!isReady) {
    return (
      <div
        className="flex items-center justify-center min-h-screen"
        style={{ backgroundColor: 'var(--tg-bg)' }}
      >
        <div
          className="w-9 h-9 rounded-full border-[3px] animate-spin"
          style={{ borderColor: 'var(--tg-accent)', borderTopColor: 'transparent' }}
        />
      </div>
    );
  }

  // ── Edit overlay ────────────────────────────────────────────────────────────
  if (editingHW) {
    return (
      <div className="flex flex-col h-screen overflow-hidden" style={{ backgroundColor: 'var(--tg-bg)' }}>
        <header
          className="flex-shrink-0 px-4 pt-3 pb-3 border-b"
          style={{ backgroundColor: 'var(--tg-secondary-bg)', borderColor: 'rgba(142,142,147,0.2)' }}
        >
          <h1 className="text-[17px] font-semibold" style={{ color: 'var(--tg-text)' }}>
            Редактировать задание
          </h1>
        </header>
        <main className="flex-1 overflow-y-auto">
          <AddHomeworkForm
            initialData={editingHW}
            onCancel={() => setEditingHW(null)}
            onSubmit={async data => {
              await updateExistingHomework(editingHW.id, data);
              haptic('success');
              setEditingHW(null);
            }}
            onDelete={async () => {
              await removeHomework(editingHW.id);
              haptic('success');
              setEditingHW(null);
            }}
          />
        </main>
      </div>
    );
  }

  // ── Tab titles ─────────────────────────────────────────────────────────────
  const TITLES: Record<TabType, string> = {
    schedule: 'Дневник',
    debts:    'Мои долги',
    add:      'Новое задание',
    load:     'Нагрузка класса',
    grades:   'Мои оценки',
  };

  const debtHomeworks = homeworks.filter(hw => !hw.isDone);

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ backgroundColor: 'var(--tg-bg)' }}>

      {/* ── Header ── */}
      <header
        className="flex-shrink-0 px-4 pt-3 pb-3 border-b"
        style={{ backgroundColor: 'var(--tg-secondary-bg)', borderColor: 'rgba(142,142,147,0.2)' }}
      >
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <h1
              className="text-[17px] font-semibold leading-tight truncate"
              style={{ color: 'var(--tg-text)' }}
            >
              {TITLES[activeTab]}
            </h1>
            {user && (
              <p className="text-[12px] truncate" style={{ color: 'var(--tg-hint)' }}>
                {[user.first_name, user.last_name].filter(Boolean).join(' ')}
              </p>
            )}
          </div>

          {activeTab === 'debts' && !loading && (
            <span className="text-[13px] ml-2 flex-shrink-0" style={{ color: 'var(--tg-hint)' }}>
              {debtHomeworks.length} шт.
            </span>
          )}
        </div>
      </header>

      {/* ── Content (all tabs stay mounted; framer-motion opacity) ── */}
      <main className="flex-1 overflow-hidden relative">

        {/* Schedule */}
        <motion.div
          className="absolute inset-0"
          animate={{ opacity: activeTab === 'schedule' ? 1 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ pointerEvents: activeTab === 'schedule' ? 'auto' : 'none' }}
        >
          <ScheduleView
            homeworks={homeworks}
            schedule={schedule}
            loading={loading}
            onToggle={handleToggle}
            onOpen={hw => setPreviewHW(hw)}
            onAddForSubject={() => setActiveTab('add')}
          />
        </motion.div>

        {/* Debts */}
        <motion.div
          className="absolute inset-0 overflow-y-auto"
          animate={{ opacity: activeTab === 'debts' ? 1 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ pointerEvents: activeTab === 'debts' ? 'auto' : 'none' }}
        >
          <HomeworkList
            homeworks={debtHomeworks}
            loading={loading}
            error={error}
            onToggle={handleToggle}
            onEdit={handleEdit}
            emptyMessage="Все задания выполнены!"
          />
        </motion.div>

        {/* Load */}
        <motion.div
          className="absolute inset-0"
          animate={{ opacity: activeTab === 'load' ? 1 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ pointerEvents: activeTab === 'load' ? 'auto' : 'none' }}
        >
          <LoadView homeworks={homeworks} loading={loading} />
        </motion.div>

        {/* Add homework */}
        <motion.div
          className="absolute inset-0 overflow-y-auto"
          animate={{ opacity: activeTab === 'add' ? 1 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ pointerEvents: activeTab === 'add' ? 'auto' : 'none' }}
        >
          <AddHomeworkForm
            onSubmit={async data => {
              const newHw = await addNewHomework(data);
              haptic('success');
              setSnackbar({
                message: 'Задание добавлено в список класса!',
                hwId:    newHw.id,
              });
              setActiveTab('schedule');
            }}
          />
        </motion.div>

        {/* Grades */}
        <motion.div
          className="absolute inset-0"
          animate={{ opacity: activeTab === 'grades' ? 1 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ pointerEvents: activeTab === 'grades' ? 'auto' : 'none' }}
        >
          <GradesView
            grades={grades}
            targets={targets}
            loading={gradesLoading}
            subjects={gradeSubjects}
            onAddGrade={(subject, value) => { haptic('medium'); addGrade(subject, value); }}
            onDeleteGrade={id => { haptic('medium'); removeGrade(id); }}
            onSetTarget={(subject, target) => { haptic('light'); setTarget(subject, target); }}
          />
        </motion.div>

      </main>

      {/* ── Preview modal (schedule tap) ── */}
      {previewHW && (
        <HomeworkModal
          homework={previewHW}
          onClose={() => setPreviewHW(null)}
          onToggle={() => { handleToggle(previewHW.id); setPreviewHW(null); }}
          onEdit={() => { setPreviewHW(null); handleEdit(previewHW); }}
        />
      )}

      {/* ── Undo snackbar ── */}
      <div
        className="fixed left-0 right-0 z-50 flex justify-center px-4 pointer-events-none"
        style={{ bottom: 'calc(60px + env(safe-area-inset-bottom, 0px) + 10px)' }}
      >
        <AnimatePresence>
          {snackbar && (
            <motion.div
              className="pointer-events-auto"
              initial={{ y: 48, opacity: 0, scale: 0.95 }}
              animate={{ y: 0,  opacity: 1, scale: 1    }}
              exit={{    y: 48, opacity: 0, scale: 0.95 }}
              transition={{ type: 'spring', damping: 22, stiffness: 300 }}
            >
              <Snackbar
                message={snackbar.message}
                action={snackbar.hwId ? {
                  label: 'Отменить',
                  onClick: () => {
                    removeHomework(snackbar.hwId!);
                    haptic('warning');
                  },
                } : undefined}
                onDismiss={() => setSnackbar(null)}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Bottom nav ── */}
      <BottomNav
        activeTab={activeTab}
        onTabChange={handleTabChange}
        pendingCount={pendingCount}
      />
    </div>
  );
}
