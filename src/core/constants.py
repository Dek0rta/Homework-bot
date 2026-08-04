"""Общие константы: дни недели, расписание звонков, подписи кнопок."""

DAYS_RU = [
    "Понедельник", "Вторник", "Среда", "Четверг",
    "Пятница", "Суббота", "Воскресенье",
]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

MONTHS_SHORT = [
    "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]

# Расписание звонков 2025-2026 (начало каждого из 8 уроков)
LESSON_TIMES = [
    "8:15",   # 1 урок   8:15 – 8:55
    "9:15",   # 2 урок   9:15 – 9:55
    "10:10",  # 3 урок  10:10 – 10:50
    "11:05",  # 4 урок  11:05 – 11:45
    "12:00",  # 5 урок  12:00 – 12:40
    "12:50",  # 6 урок  12:50 – 13:30
    "13:40",  # 7 урок  13:40 – 14:20
    "14:30",  # 8 урок  14:30 – 15:10
]

# Типы чатов, которые считаются групповыми
GROUP_TYPES = {"group", "supergroup"}

# Подписи кнопок главной клавиатуры
BTN_SCHEDULE     = "📅 Моё расписание"
BTN_SET_SCHEDULE = "✏️ Изменить расписание"
BTN_CALENDAR     = "🔗 Google Calendar"
BTN_STATS        = "📊 Нагрузка"
BTN_WEBAPP       = "🌐 Открыть приложение"

BUTTON_TEXTS = {BTN_SCHEDULE, BTN_SET_SCHEDULE, BTN_CALENDAR, BTN_STATS}


def lesson_number(start_time: str) -> int:
    """Номер урока (1-based) по времени начала. Fallback — ближайший слот."""
    try:
        return LESSON_TIMES.index(start_time) + 1
    except ValueError:
        for i, t in enumerate(LESSON_TIMES, 1):
            if start_time <= t:
                return i
        return len(LESSON_TIMES)


def time_key(t: str) -> int:
    """Сортировочный ключ для времени «Ч:ММ» → минуты от полуночи."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)
