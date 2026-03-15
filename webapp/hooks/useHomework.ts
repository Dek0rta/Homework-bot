'use client';

import { useState, useEffect, useCallback } from 'react';
import { HomeworkWithStatus, AddHomeworkData } from '@/types';
import {
  fetchHomework,
  fetchUserStatuses,
  setHomeworkStatus,
  addHomework,
} from '@/lib/api';

export function useHomework(userId: number | null) {
  const [homeworks, setHomeworks] = useState<HomeworkWithStatus[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  // ── Load all homework + this user's statuses ──────────────────────────────
  const loadData = useCallback(async () => {
    if (userId === null) return;
    setLoading(true);
    setError(null);
    try {
      const [hws, statuses] = await Promise.all([
        fetchHomework(),
        fetchUserStatuses(userId),
      ]);

      const merged: HomeworkWithStatus[] = hws.map(hw => ({
        ...hw,
        isDone: statuses[hw.id] ?? false,
      }));

      // Sort: overdue undone → active undone (by deadline) → done
      merged.sort((a, b) => {
        if (a.isDone !== b.isDone) return a.isDone ? 1 : -1;
        return new Date(a.deadline).getTime() - new Date(b.deadline).getTime();
      });

      setHomeworks(merged);
    } catch {
      setError('Не удалось загрузить задания. Проверь соединение.');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => { loadData(); }, [loadData]);

  // ── Toggle done/undone (optimistic update) ────────────────────────────────
  const toggleStatus = useCallback(
    async (homeworkId: string) => {
      if (userId === null) return;

      // Find current state before mutation
      const prev = homeworks.find(h => h.id === homeworkId);
      if (!prev) return;

      const nextDone = !prev.isDone;

      // Optimistic
      setHomeworks(list =>
        list.map(hw => hw.id === homeworkId ? { ...hw, isDone: nextDone } : hw),
      );

      try {
        await setHomeworkStatus(userId, homeworkId, nextDone);
      } catch {
        // Revert on failure
        setHomeworks(list =>
          list.map(hw => hw.id === homeworkId ? { ...hw, isDone: prev.isDone } : hw),
        );
      }
    },
    [userId, homeworks],
  );

  // ── Add new homework ──────────────────────────────────────────────────────
  const addNewHomework = useCallback(
    async (data: AddHomeworkData) => {
      if (userId === null) throw new Error('No user');
      const newHw = await addHomework(userId, data);
      const withStatus: HomeworkWithStatus = { ...newHw, isDone: false };
      setHomeworks(list => [withStatus, ...list]);
      return newHw;
    },
    [userId],
  );

  const pendingCount = homeworks.filter(hw => !hw.isDone).length;

  return {
    homeworks,
    loading,
    error,
    toggleStatus,
    addNewHomework,
    reload: loadData,
    pendingCount,
  };
}
