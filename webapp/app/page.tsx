'use client';

import { useState, useEffect } from 'react';
import { useTelegram }         from '@/hooks/useTelegram';
import { useHomework }         from '@/hooks/useHomework';
import { TabType }             from '@/types';
import BottomNav               from '@/components/layout/BottomNav';
import HomeworkList            from '@/components/homework/HomeworkList';
import AddHomeworkForm         from '@/components/homework/AddHomeworkForm';

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabType>('all');
  const { user, colorScheme, isReady, haptic } = useTelegram();

  const {
    homeworks,
    loading,
    error,
    toggleStatus,
    addNewHomework,
    pendingCount,
  } = useHomework(user?.id ?? null);

  // Sync Telegram color scheme → <html class="dark">
  useEffect(() => {
    document.documentElement.classList.toggle('dark', colorScheme === 'dark');
  }, [colorScheme]);

  const handleTabChange = (tab: TabType) => {
    haptic('light');
    setActiveTab(tab);
  };

  const handleToggle = (id: string) => {
    haptic('medium');
    toggleStatus(id);
  };

  // ── Loading splash ────────────────────────────────────────────────────────
  if (!isReady) {
    return (
      <div
        className="flex items-center justify-center min-h-screen"
        style={{ backgroundColor: 'var(--tg-bg)' }}
      >
        <div
          className="w-9 h-9 rounded-full border-[3px] border-t-transparent animate-spin"
          style={{ borderColor: 'var(--tg-accent)', borderTopColor: 'transparent' }}
        />
      </div>
    );
  }

  const displayedHomeworks =
    activeTab === 'debts' ? homeworks.filter(hw => !hw.isDone) : homeworks;

  // ── Titles ────────────────────────────────────────────────────────────────
  const TITLES: Record<TabType, string> = {
    all:   'Все задания',
    debts: 'Мои долги',
    add:   'Новое задание',
  };

  return (
    <div
      className="flex flex-col h-screen overflow-hidden"
      style={{ backgroundColor: 'var(--tg-bg)' }}
    >
      {/* ── Header ── */}
      <header
        className="flex-shrink-0 px-4 pt-3 pb-3 border-b"
        style={{
          backgroundColor: 'var(--tg-secondary-bg)',
          borderColor: 'rgba(142,142,147,0.2)',
        }}
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

          {activeTab !== 'add' && !loading && (
            <span
              className="text-[13px] ml-2 flex-shrink-0"
              style={{ color: 'var(--tg-hint)' }}
            >
              {displayedHomeworks.length} шт.
            </span>
          )}
        </div>
      </header>

      {/* ── Scrollable content ── */}
      <main
        className="flex-1 overflow-y-auto overscroll-none"
        style={{ WebkitOverflowScrolling: 'touch' } as React.CSSProperties}
      >
        {activeTab === 'add' ? (
          <AddHomeworkForm
            onSubmit={async data => {
              await addNewHomework(data);
              haptic('success');
              setActiveTab('all');
            }}
          />
        ) : (
          <HomeworkList
            homeworks={displayedHomeworks}
            loading={loading}
            error={error}
            onToggle={handleToggle}
            emptyMessage={
              activeTab === 'debts'
                ? 'Все задания выполнены!'
                : 'Заданий пока нет'
            }
          />
        )}
      </main>

      {/* ── Bottom nav ── */}
      <BottomNav
        activeTab={activeTab}
        onTabChange={handleTabChange}
        pendingCount={pendingCount}
      />
    </div>
  );
}
