'use client';

import { useState, useEffect, useCallback } from 'react';
import { HomeworkWithStatus, AddHomeworkData, ScheduleLesson } from '@/types';
import {
  fetchHomework,
  fetchUserStatuses,
  setHomeworkStatus,
  addHomework,
  updateHomework,
  deleteHomework,
  fetchSchedule,
} from '@/lib/api';

export function useHomework(userId: number | null) {
  const [homeworks, setHomeworks] = useState<HomeworkWithStatus[]>([]);
  const [schedule,  setSchedule]  = useState<ScheduleLesson[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);

  // ── Load ──────────────────────────────────────────────────────────────────
  const loadData = useCallback(async () => {
    if (userId === null) return;
    setLoading(true);
    setError(null);
    try {
      const [hws, statuses, sched] = await Promise.all([
        fetchHomework(),
        fetchUserStatuses(userId),
        fetchSchedule(),
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
      setSchedule(sched);
    } catch {
      setError('Не удалось загрузить задания. Проверь соединение.');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => { loadData(); }, [loadData]);

  // ── Toggle done / undone (optimistic) ────────────────────────────────────
  const toggleStatus = useCallback(
    async (homeworkId: string) => {
      if (userId === null) return;
      const prev = homeworks.find(h => h.id === homeworkId);
      if (!prev) return;
      const nextDone = !prev.isDone;
      setHomeworks(list =>
        list.map(hw => hw.id === homeworkId ? { ...hw, isDone: nextDone } : hw),
      );
      try {
        await setHomeworkStatus(userId, homeworkId, nextDone);
      } catch {
        setHomeworks(list =>
          list.map(hw => hw.id === homeworkId ? { ...hw, isDone: prev.isDone } : hw),
        );
      }
    },
    [userId, homeworks],
  );

  // ── Add ───────────────────────────────────────────────────────────────────
  const addNewHomework = useCallback(
    async (data: AddHomeworkData) => {
      if (userId === null) throw new Error('No user');
      const newHw = await addHomework(userId, data);
      setHomeworks(list => [{ ...newHw, isDone: false }, ...list]);
      return newHw;
    },
    [userId],
  );

  // ── Edit ──────────────────────────────────────────────────────────────────
  const updateExistingHomework = useCallback(
    async (id: string, data: AddHomeworkData) => {
      if (userId === null) throw new Error('No user');
      const updated = await updateHomework(id, userId, data);
      setHomeworks(list =>
        list.map(hw => hw.id === id ? { ...updated, isDone: hw.isDone } : hw),
      );
      return updated;
    },
    [userId],
  );

  // ── Delete ────────────────────────────────────────────────────────────────
  const removeHomework = useCallback(async (id: string) => {
    await deleteHomework(id);
    setHomeworks(list => list.filter(hw => hw.id !== id));
  }, []);

  const pendingCount = homeworks.filter(hw => !hw.isDone).length;

  return {
    homeworks,
    schedule,
    loading,
    error,
    toggleStatus,
    addNewHomework,
    updateExistingHomework,
    removeHomework,
    reload: loadData,
    pendingCount,
  };
}
