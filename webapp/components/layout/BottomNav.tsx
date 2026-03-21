'use client';

import { CalendarDays, AlertCircle, PlusCircle, BarChart2, GraduationCap } from 'lucide-react';
import { TabType } from '@/types';

interface BottomNavProps {
  activeTab:    TabType;
  onTabChange:  (tab: TabType) => void;
  pendingCount: number;
}

const TABS = [
  { id: 'schedule' as TabType, label: 'Дневник',  Icon: CalendarDays    },
  { id: 'debts'    as TabType, label: 'Долги',    Icon: AlertCircle     },
  { id: 'grades'   as TabType, label: 'Оценки',   Icon: GraduationCap   },
  { id: 'load'     as TabType, label: 'Нагрузка', Icon: BarChart2       },
  { id: 'add'      as TabType, label: 'Добавить', Icon: PlusCircle      },
];

export default function BottomNav({ activeTab, onTabChange, pendingCount }: BottomNavProps) {
  return (
    <nav
      className="flex-shrink-0 flex border-t pb-safe"
      style={{ backgroundColor: 'var(--tg-secondary-bg)', borderColor: 'rgba(142,142,147,0.2)' }}
    >
      {TABS.map(({ id, label, Icon }) => {
        const active = activeTab === id;
        return (
          <button
            key={id}
            onClick={() => onTabChange(id)}
            className="flex-1 flex flex-col items-center justify-center gap-1 py-2.5 active:opacity-60"
          >
            {/* Icon + badge wrapper */}
            <span
              className="relative transition-transform duration-200"
              style={{ transform: active ? 'scale(1.12)' : 'scale(1)' }}
            >
              <Icon
                size={22}
                strokeWidth={active ? 2.4 : 1.6}
                style={{
                  color:      active ? 'var(--tg-accent)' : 'var(--tg-hint)',
                  transition: 'color 0.2s ease',
                  display:    'block',
                }}
              />
              {id === 'debts' && pendingCount > 0 && (
                <span
                  className="absolute -top-1.5 -right-2 min-w-[16px] h-[16px] px-[3px]
                             rounded-full text-[9px] font-bold leading-[16px] text-center
                             text-white animate-tab-badge"
                  style={{ backgroundColor: '#ff3b30' }}
                >
                  {pendingCount > 99 ? '99+' : pendingCount}
                </span>
              )}
            </span>

            <span
              className="text-[10px] font-medium"
              style={{
                color:      active ? 'var(--tg-accent)' : 'var(--tg-hint)',
                transition: 'color 0.2s ease',
              }}
            >
              {label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
