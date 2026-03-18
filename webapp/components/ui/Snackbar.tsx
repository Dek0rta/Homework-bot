'use client';

import { useEffect } from 'react';
import { CheckCircle2 } from 'lucide-react';

interface SnackbarProps {
  message:  string;
  action?:  { label: string; onClick: () => void };
  onDismiss: () => void;
  duration?: number;
}

export default function Snackbar({ message, action, onDismiss, duration = 4000 }: SnackbarProps) {
  useEffect(() => {
    const t = setTimeout(onDismiss, duration);
    return () => clearTimeout(t);
  }, [onDismiss, duration]);

  return (
    <div
      className="flex items-center gap-3 px-4 py-3.5 rounded-2xl shadow-xl"
      style={{ backgroundColor: '#1c1c1e', color: '#fff', minWidth: '260px', maxWidth: '360px' }}
    >
      <CheckCircle2 size={18} style={{ color: '#34c759', flexShrink: 0 }} />
      <span className="text-[14px] flex-1 leading-tight">{message}</span>
      {action && (
        <button
          onClick={() => { action.onClick(); onDismiss(); }}
          className="text-[14px] font-bold flex-shrink-0 ml-1 active:opacity-60 transition-opacity"
          style={{ color: '#0a84ff' }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
