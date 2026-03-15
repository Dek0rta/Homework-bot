'use client';

import { useState, useEffect }           from 'react';
import { useTelegram }                   from '@/hooks/useTelegram';
import { useHomework }                   from '@/hooks/useHomework';
import { TabType, HomeworkWithStatus }   from '@/types';
import BottomNav                         from '@/components/layout/BottomNav';
import HomeworkList                      from '@/components/homework/HomeworkList';
import HomeworkModal                     from '@/components/homework/HomeworkModal';
import AddHomeworkForm                   from '@/components/homework/AddHomeworkForm';
import ScheduleView                      from '@/components/schedule/ScheduleView';

export default function HomePage() {
  const [activeTab,     setActiveTab]     = useState<TabType>('schedule');
  const [editingHW,     setEditingHW]     = useState<HomeworkWithStatus | null>(null);
  const [previewHW,     setPreviewHW]     = useState<HomeworkWithStatus | null>(null);
  const { user, colorScheme, isReady, haptic } = useTelegram();

  const {
    homeworks, schedule, loading, error,
    toggleStatus, addNewHomework, updateExistingHomework, removeHomework,
    pendingCount,
  } = useHomework(user?.id ?? null);

  // Sync Telegram dark mode
  useEffect(() => {
    document.documentElement.classList.toggle('dark', colorScheme === 'dark');
  }, [colorScheme]);

  const handleTabChange = (tab: TabType) => { haptic('light'); setActiveTab(tab); };
  const handleToggle    = (id: string)   => { haptic('medium'); toggleStatus(id); };
  const handleEdit      = (hw: HomeworkWithStatus) => { haptic('light'); setEditingHW(hw); };

  // ── Loading splash ────────────────────────────────────────────────────────
  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-screen" style={{ backgroundColor: 'var(--tg-bg)' }}>
        <div
          className="w-9 h-9 rounded-full border-[3px] animate-spin"
          style={{ borderColor: 'var(--tg-accent)', borderTopColor: 'transparent' }}
        />
      </div>
    );
  }

  // ── Edit overlay ──────────────────────────────────────────────────────────
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

  // ── Tab titles ────────────────────────────────────────────────────────────
  const TITLES: Record<TabType, string> = {
    schedule: 'Дневник',
    debts:    'Мои долги',
    add:      'Новое задание',
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

      {/* ── Content ── */}
      <main className="flex-1 overflow-hidden">
        {activeTab === 'schedule' && (
          <ScheduleView
            homeworks={homeworks}
            schedule={schedule}
            loading={loading}
            onToggle={handleToggle}
            onOpen={hw => setPreviewHW(hw)}
            onAddForSubject={() => setActiveTab('add')}
          />
        )}

        {activeTab === 'debts' && (
          <div className="h-full overflow-y-auto">
            <HomeworkList
              homeworks={debtHomeworks}
              loading={loading}
              error={error}
              onToggle={handleToggle}
              onEdit={handleEdit}
              emptyMessage="Все задания выполнены!"
            />
          </div>
        )}

        {activeTab === 'add' && (
          <div className="h-full overflow-y-auto">
            <AddHomeworkForm
              onSubmit={async data => {
                await addNewHomework(data);
                haptic('success');
                setActiveTab('schedule');
              }}
            />
          </div>
        )}
      </main>

      {/* ── Preview modal (from schedule tap) ── */}
      {previewHW && (
        <HomeworkModal
          homework={previewHW}
          onClose={() => setPreviewHW(null)}
          onToggle={() => { handleToggle(previewHW.id); setPreviewHW(null); }}
          onEdit={() => { setPreviewHW(null); handleEdit(previewHW); }}
        />
      )}

      {/* ── Bottom nav ── */}
      <BottomNav
        activeTab={activeTab}
        onTabChange={handleTabChange}
        pendingCount={pendingCount}
      />
    </div>
  );
}
