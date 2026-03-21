'use client';

import { useState, useEffect, useCallback } from 'react';
import { Grade } from '@/types';
import {
  fetchGrades,
  addGrade      as apiAddGrade,
  deleteGrade   as apiDeleteGrade,
  fetchGradeTargets,
  setGradeTarget as apiSetTarget,
} from '@/lib/api';

export function useGrades(userId: number | null) {
  const [grades,  setGrades]  = useState<Grade[]>([]);
  const [targets, setTargets] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (userId === null) return;
    setLoading(true);
    Promise.all([fetchGrades(userId), fetchGradeTargets(userId)])
      .then(([g, t]) => { setGrades(g); setTargets(t); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [userId]);

  // ── Add (optimistic) ────────────────────────────────────────────────────────
  const addGrade = useCallback(
    async (subject: string, value: 2 | 3 | 4 | 5, note?: string) => {
      if (userId === null) return;
      const tempId  = `temp-${Date.now()}`;
      const optimistic: Grade = {
        id:      tempId,
        userId,
        subject,
        value,
        date:    new Date().toISOString().split('T')[0],
        note:    note ?? null,
      };
      setGrades(prev => [optimistic, ...prev]);
      try {
        const saved = await apiAddGrade(userId, subject, value, note);
        setGrades(prev => prev.map(g => g.id === tempId ? saved : g));
      } catch {
        setGrades(prev => prev.filter(g => g.id !== tempId));
      }
    },
    [userId],
  );

  // ── Remove (optimistic) ─────────────────────────────────────────────────────
  const removeGrade = useCallback(
    async (gradeId: string) => {
      if (userId === null) return;
      const snapshot = grades.find(g => g.id === gradeId);
      setGrades(prev => prev.filter(g => g.id !== gradeId));
      try {
        await apiDeleteGrade(userId, gradeId);
      } catch {
        if (snapshot) setGrades(prev => [snapshot, ...prev]);
      }
    },
    [userId, grades],
  );

  // ── Set target (optimistic) ─────────────────────────────────────────────────
  const setTarget = useCallback(
    async (subject: string, target: number) => {
      if (userId === null) return;
      const prev = targets[subject];
      setTargets(t => ({ ...t, [subject]: target }));
      try {
        await apiSetTarget(userId, subject, target);
      } catch {
        setTargets(t => {
          const next = { ...t };
          if (prev !== undefined) next[subject] = prev;
          else delete next[subject];
          return next;
        });
      }
    },
    [userId, targets],
  );

  return { grades, targets, loading, addGrade, removeGrade, setTarget };
}
