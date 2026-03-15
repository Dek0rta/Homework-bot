/**
 * API layer — switches between real backend and mock data.
 * Set NEXT_PUBLIC_API_URL in .env to point at the real bot backend.
 * Leave it empty (or set to "mock") to use built-in demo data.
 */

import { Homework, AddHomeworkData } from '@/types';
import { MOCK_HOMEWORK } from './mockData';

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const USE_MOCK = !API_URL || API_URL === 'mock';

function sleep(ms: number) {
  return new Promise(r => setTimeout(r, ms));
}

// ── Homework ─────────────────────────────────────────────────────────────────

export async function fetchHomework(): Promise<Homework[]> {
  if (USE_MOCK) {
    await sleep(450);
    return [...MOCK_HOMEWORK];
  }
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
      id: `local-${Date.now()}`,
      subject: data.subject,
      description: data.description,
      deadline: data.deadline,
      photos: [],
      createdAt: new Date().toISOString(),
      createdBy: userId,
    };
    // Prepend so it shows up at the top
    MOCK_HOMEWORK.unshift(newHw);
    return newHw;
  }

  const formData = new FormData();
  formData.append('subject', data.subject);
  formData.append('description', data.description);
  formData.append('deadline', data.deadline);
  formData.append('userId', String(userId));
  data.photos?.forEach(p => formData.append('photos', p));

  const res = await fetch(`${API_URL}/api/homework`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error(`addHomework: ${res.status}`);
  return res.json();
}

// ── Per-user status (Global data, Local state) ────────────────────────────────

/**
 * Returns a map of { homeworkId: isDone } for the given user.
 * In mock mode — reads from localStorage so state survives refresh.
 */
export async function fetchUserStatuses(
  userId: number,
): Promise<Record<string, boolean>> {
  if (USE_MOCK) {
    await sleep(150);
    try {
      const raw = localStorage.getItem(`hw_status_${userId}`);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }
  const res = await fetch(`${API_URL}/api/status/${userId}`);
  if (!res.ok) return {};
  return res.json();
}

/**
 * Persists one homework status for the given user.
 * Architecture: only THIS user's status changes — others are unaffected.
 */
export async function setHomeworkStatus(
  userId: number,
  homeworkId: string,
  isDone: boolean,
): Promise<void> {
  if (USE_MOCK) {
    await sleep(100);
    try {
      const key = `hw_status_${userId}`;
      const current: Record<string, boolean> = JSON.parse(
        localStorage.getItem(key) ?? '{}',
      );
      current[homeworkId] = isDone;
      localStorage.setItem(key, JSON.stringify(current));
    } catch {
      // ignore storage errors
    }
    return;
  }

  await fetch(`${API_URL}/api/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, homeworkId, isDone }),
  });
}
