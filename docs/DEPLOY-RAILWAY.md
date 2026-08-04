# Деплой «Виртуальная школа» на Railway.app

## Предварительные требования

- Аккаунт на [railway.app](https://railway.app)
- Репозиторий на GitHub с папкой `webapp/` (или отдельный репо только с этим кодом)

---

## Шаг 1 — Создать новый проект

1. Войди в Railway → **New Project → Deploy from GitHub repo**
2. Выбери нужный репозиторий
3. Если весь код лежит в подпапке (`webapp/`), на следующем шаге укажи Root Directory

---

## Шаг 2 — Настроить Root Directory (если нужно)

В настройках сервиса Railway:

```
Settings → Source → Root Directory → webapp
```

Nixpacks автоматически определит Next.js и запустит:
```
npm install && npm run build
npm run start          # = next start -p $PORT
```

---

## Шаг 3 — Переменные окружения

В разделе **Variables** добавь:

| Переменная              | Значение                                    | Обязательно |
|-------------------------|---------------------------------------------|-------------|
| `NEXT_PUBLIC_API_URL`   | URL вашего Python-бота (REST API)           | Нет*        |
| `NODE_ENV`              | `production`                                | Авто        |
| `PORT`                  | Задаётся Railway автоматически              | —           |

> *Если `NEXT_PUBLIC_API_URL` не задан — приложение работает в режиме **mock-данных** (демо).
> Для продакшна нужен REST-бэкенд (см. раздел «Бэкенд API»).

---

## Шаг 4 — Деплой

Нажми **Deploy** или просто сделай `git push` — Railway подхватит изменения автоматически.

После сборки Railway покажет публичный URL вида:
```
https://virtual-school-webapp-production.up.railway.app
```

---

## Шаг 5 — Подключить к Telegram-боту

1. Открой [@BotFather](https://t.me/BotFather)
2. Выбери своего бота → **Bot Settings → Menu Button → Edit menu button URL**
3. Вставь URL из Railway

Или в коде бота при отправке WebApp-кнопки:
```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

kb = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(
        text="📚 Открыть школу",
        web_app=WebAppInfo(url="https://YOUR_URL.railway.app")
    )
]])
```

---

## Бэкенд API (опционально)

Чтобы данные были реальными, Python-бот должен предоставить REST API:

### GET `/api/homework`
```json
[
  {
    "id": "1",
    "subject": "Математика",
    "description": "Задачи 1-10",
    "deadline": "2025-03-20",
    "photos": [],
    "createdAt": "2025-03-15T10:00:00Z",
    "createdBy": 123456789
  }
]
```

### POST `/api/homework`
```
multipart/form-data:
  subject, description, deadline, userId, photos[]
```

### GET `/api/status/{userId}`
```json
{ "hw_id_1": true, "hw_id_2": false }
```

### POST `/api/status`
```json
{ "userId": 123, "homeworkId": "1", "isDone": true }
```

> Добавить FastAPI к существующему боту — ~50 строк кода в отдельном файле.

---

## Локальная разработка

```bash
cd webapp
npm install
cp .env.example .env.local
# Оставь NEXT_PUBLIC_API_URL пустым для mock-режима
npm run dev
# → http://localhost:3000
```

---

## Структура файлов

```
webapp/
├── app/
│   ├── layout.tsx          # Root layout, подключает Telegram SDK
│   ├── page.tsx            # Главная страница (tabs)
│   └── globals.css         # CSS переменные Telegram + Tailwind
├── components/
│   ├── layout/
│   │   └── BottomNav.tsx   # Нижняя навигация
│   └── homework/
│       ├── HomeworkCard.tsx  # Карточка задания с чекбоксом
│       ├── HomeworkList.tsx  # Список с группировкой
│       ├── HomeworkModal.tsx # Bottom sheet деталей + лайтбокс
│       └── AddHomeworkForm.tsx # Форма добавления ДЗ
├── hooks/
│   ├── useTelegram.ts      # Telegram WebApp SDK + haptic
│   └── useHomework.ts      # Загрузка данных + optimistic updates
├── lib/
│   ├── api.ts              # API слой (real/mock)
│   ├── subjects.ts         # Цвета/эмодзи предметов
│   ├── dateUtils.ts        # Форматирование дат (без зависимостей)
│   └── mockData.ts         # Demo-данные для прототипа
├── types/index.ts          # TypeScript типы
├── .env.example            # Пример переменных окружения
└── README_RAILWAY.md       # Этот файл
```
