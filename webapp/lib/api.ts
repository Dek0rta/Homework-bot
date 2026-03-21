/**
 * API layer — switches between real backend and mock data.
 * Set NEXT_PUBLIC_API_URL in .env to enable real backend.
 * Leave empty / "mock" for built-in demo data.
 */

import { Homework, AddHomeworkData, ScheduleLesson, Grade } from '@/types';
import { MOCK_HOMEWORK, MOCK_SCHEDULE }               from './mockData';
import { compressToBase64 }                           from './imageUtils';

const API_URL  = process.env.NEXT_PUBLIC_API_URL;
const USE_MOCK = !API_URL || API_URL === 'mock';

function sleep(ms: number) {
  return new Promise(r => setTimeout(r, ms));
}

async function compressPhotos(files: File[]): Promise<string[]> {
  return Promise.all(files.map(f => compressToBase64(f)));
}

// ── Homework ─────────────────────────────────────────────────────────────────

export async function fetchHomework(): Promise<Homework[]> {
  if (USE_MOCK) { await sleep(400); return [...MOCK_HOMEWORK]; }
  const res = await fetch(`${API_URL}/api/homework`);
  if (!res.ok) throw new Error(`fetchHomework: ${res.status}`);
  return res.json();
}

export async function addHomework(
  userId: number,
  data: AddHomeworkData,
): Promise<Homework> {
  if (USE_MOCK) {
    await sleep(600);
    const newHw: Homework = {
      id:          `local-${Date.now()}`,
      subject:     data.subject,
      description: data.description,
      deadline:    data.deadline,
      photos:      [],
      createdAt:   new Date().toISOString(),
      createdBy:   userId,
    };
    MOCK_HOMEWORK.unshift(newHw);
    return newHw;
  }

  const photos = data.photos?.length ? await compressPhotos(data.photos) : [];
  const res = await fetch(`${API_URL}/api/homework`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({
      subject:     data.subject,
      description: data.description,
      deadline:    data.deadline,
      userId,
      photos,
    }),
  });
  if (!res.ok) throw new Error(`addHomework: ${res.status}`);
  return res.json();
}

export async function updateHomework(
  id: string,
  _userId: number,
  data: AddHomeworkData,
): Promise<Homework> {
  if (USE_MOCK) {
    await sleep(400);
    const idx = MOCK_HOMEWORK.findIndex(h => h.id === id);
    if (idx !== -1) {
      MOCK_HOMEWORK[idx] = {
        ...MOCK_HOMEWORK[idx],
        subject:     data.subject,
        description: data.description,
        deadline:    data.deadline,
      };
      return MOCK_HOMEWORK[idx];
    }
    throw new Error('not found');
  }

  const newPhotos  = data.photos?.length    ? await compressPhotos(data.photos) : [];
  const keepPhotos = data.keepPhotos ?? [];
  const photos     = [...keepPhotos, ...newPhotos];

  const res = await fetch(`${API_URL}/api/homework/${id}`, {
    method:  'PUT',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({
      subject:     data.subject,
      description: data.description,
      deadline:    data.deadline,
      photos,
    }),
  });
  if (!res.ok) throw new Error(`updateHomework: ${res.status}`);
  return res.json();
}

export async function deleteHomework(id: string): Promise<void> {
  if (USE_MOCK) {
    await sleep(300);
    const idx = MOCK_HOMEWORK.findIndex(h => h.id === id);
    if (idx !== -1) MOCK_HOMEWORK.splice(idx, 1);
    return;
  }
  await fetch(`${API_URL}/api/homework/${id}`, { method: 'DELETE' });
}

// ── Per-user status ───────────────────────────────────────────────────────────

export async function fetchUserStatuses(
  userId: number,
): Promise<Record<string, boolean>> {
  if (USE_MOCK) {
    await sleep(150);
    try {
      const raw = localStorage.getItem(`hw_status_${userId}`);
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  }
  const res = await fetch(`${API_URL}/api/status/${userId}`);
  if (!res.ok) return {};
  return res.json();
}

export async function setHomeworkStatus(
  userId: number,
  homeworkId: string,
  isDone: boolean,
): Promise<void> {
  if (USE_MOCK) {
    await sleep(100);
    try {
      const key     = `hw_status_${userId}`;
      const current: Record<string, boolean> = JSON.parse(localStorage.getItem(key) ?? '{}');
      current[homeworkId] = isDone;
      localStorage.setItem(key, JSON.stringify(current));
    } catch { /* ignore */ }
    return;
  }
  await fetch(`${API_URL}/api/status`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ userId, homeworkId, isDone }),
  });
}

// ── Grades ────────────────────────────────────────────────────────────────────

const _gradesKey  = (uid: number) => `grades_${uid}`;
const _targetsKey = (uid: number) => `grade_targets_${uid}`;

export async function fetchGrades(userId: number): Promise<Grade[]> {
  if (USE_MOCK) {
    await sleep(150);
    try {
      const raw = localStorage.getItem(_gradesKey(userId));
      return raw ? JSON.parse(raw) : [];
    } catch { return []; }
  }
  const res = await fetch(`${API_URL}/api/grades/${userId}`);
  if (!res.ok) return [];
  return res.json();
}

export async function addGrade(
  userId: number,
  subject: string,
  value: 2 | 3 | 4 | 5,
  note?: string,
): Promise<Grade> {
  if (USE_MOCK) {
    await sleep(200);
    const grade: Grade = {
      id:      `grade-${Date.now()}`,
      userId,
      subject,
      value,
      date:    new Date().toISOString().split('T')[0],
      note:    note || null,
    };
    try {
      const raw      = localStorage.getItem(_gradesKey(userId));
      const existing: Grade[] = raw ? JSON.parse(raw) : [];
      existing.unshift(grade);
      localStorage.setItem(_gradesKey(userId), JSON.stringify(existing));
    } catch { /* ignore */ }
    return grade;
  }
  const res = await fetch(`${API_URL}/api/grades`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ userId, subject, value, note }),
  });
  if (!res.ok) throw new Error(`addGrade: ${res.status}`);
  return res.json();
}

export async function deleteGrade(userId: number, gradeId: string): Promise<void> {
  if (USE_MOCK) {
    await sleep(100);
    try {
      const raw = localStorage.getItem(_gradesKey(userId));
      if (raw) {
        const grades: Grade[] = JSON.parse(raw);
        localStorage.setItem(_gradesKey(userId), JSON.stringify(grades.filter(g => g.id !== gradeId)));
      }
    } catch { /* ignore */ }
    return;
  }
  await fetch(`${API_URL}/api/grades/${gradeId}`, { method: 'DELETE' });
}

export async function fetchGradeTargets(userId: number): Promise<Record<string, number>> {
  if (USE_MOCK) {
    await sleep(100);
    try {
      const raw = localStorage.getItem(_targetsKey(userId));
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  }
  const res = await fetch(`${API_URL}/api/grade-targets/${userId}`);
  if (!res.ok) return {};
  return res.json();
}

export async function setGradeTarget(
  userId: number,
  subject: string,
  target: number,
): Promise<void> {
  if (USE_MOCK) {
    await sleep(100);
    try {
      const raw      = localStorage.getItem(_targetsKey(userId));
      const existing: Record<string, number> = raw ? JSON.parse(raw) : {};
      existing[subject] = target;
      localStorage.setItem(_targetsKey(userId), JSON.stringify(existing));
    } catch { /* ignore */ }
    return;
  }
  await fetch(`${API_URL}/api/grade-targets`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ userId, subject, target }),
  });
}

// ── Schedule ─────────────────────────────────────────────────────────────────

export async function fetchSchedule(): Promise<ScheduleLesson[]> {
  if (USE_MOCK) {
    await sleep(200);
    return [...MOCK_SCHEDULE];
  }
  try {
    const res = await fetch(`${API_URL}/api/schedule`);
    if (!res.ok) return [];
    const data: ScheduleLesson[] = await res.json();
    // Fall back to mock if server returned empty array
    return data.length > 0 ? data : [...MOCK_SCHEDULE];
  } catch {
    return [...MOCK_SCHEDULE];
  }
}
