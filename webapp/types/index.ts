export interface Homework {
  id: string;
  subject: string;
  description: string;
  /** ISO date "YYYY-MM-DD" */
  deadline: string;
  /** Array of public photo URLs */
  photos: string[];
  createdAt: string;
  /** Telegram user_id of the creator */
  createdBy: number;
}

export interface HomeworkWithStatus extends Homework {
  /** Individual per-user status — NOT shared globally */
  isDone: boolean;
}

export type TabType = 'all' | 'debts' | 'add';

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
}
