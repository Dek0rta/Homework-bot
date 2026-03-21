export interface Homework {
  id: string;
  subject: string;
  description: string;
  /** ISO date "YYYY-MM-DD" */
  deadline: string;
  /** Array of photo URLs or base64 data-URIs */
  photos: string[];
  createdAt: string;
  /** Telegram user_id of the creator */
  createdBy: number;
  /** AI subject-detection confidence 0–1; null if added manually */
  aiConfidence?: number | null;
}

export interface HomeworkWithStatus extends Homework {
  /** Individual per-user status — NOT shared globally */
  isDone: boolean;
}

export type TabType = 'schedule' | 'debts' | 'add' | 'load' | 'grades';

export interface Grade {
  id: string;
  userId: number;
  subject: string;
  value: 2 | 3 | 4 | 5;
  /** ISO date "YYYY-MM-DD" */
  date: string;
  note?: string | null;
}

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  language_code?: string;
}

export interface AddHomeworkData {
  subject: string;
  description: string;
  /** ISO date "YYYY-MM-DD" */
  deadline: string;
  photos?: File[];
  /** Existing photos to keep when editing (base64 / URLs) */
  keepPhotos?: string[];
}

export interface ScheduleLesson {
  /** 0 = Monday … 5 = Saturday */
  dayOfWeek: number;
  /** 1-based lesson number */
  lessonNumber: number;
  /** "HH:MM" */
  startTime: string;
  subject: string;
}
