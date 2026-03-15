import { Homework } from '@/types';
import { todayISO } from '@/lib/dateUtils';

function daysFromNow(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().split('T')[0];
}

const today = todayISO();

export const MOCK_HOMEWORK: Homework[] = [
  {
    id: '1',
    subject: 'Физика',
    description:
      'Лабораторная работа №4 «Изучение закона сохранения механической энергии». ' +
      'Оформить отчёт по образцу, записать формулы, сделать таблицу измерений и вывод.',
    deadline: today,
    photos: [],
    createdAt: new Date(Date.now() - 3 * 86_400_000).toISOString(),
    createdBy: 100_000_001,
  },
  {
    id: '2',
    subject: 'Математика',
    description:
      'Параграф 18, задачи 1–12. Решить квадратные уравнения по теореме Виета. ' +
      'Оформить решение в тетради, показать проверку для каждого уравнения.',
    deadline: daysFromNow(1),
    photos: [],
    createdAt: new Date(Date.now() - 86_400_000).toISOString(),
    createdBy: 100_000_001,
  },
  {
    id: '3',
    subject: 'Химия',
    description:
      'Листочек с задачами по теме «Молярная масса». Решить все задачи, показать ' +
      'ход решения. Повторить формулы расчёта количества вещества и молярного объёма.',
    deadline: daysFromNow(1),
    photos: [],
    createdAt: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    createdBy: 100_000_002,
  },
  {
    id: '4',
    subject: 'Литература',
    description:
      'Прочитать главы 8–12 романа «Война и мир» (Том 2). Написать краткий анализ ' +
      'образа Наташи Ростовой (1–2 страницы): характер, поступки, роль в сюжете.',
    deadline: daysFromNow(5),
    photos: [],
    createdAt: new Date(Date.now() - 4 * 86_400_000).toISOString(),
    createdBy: 100_000_001,
  },
  {
    id: '5',
    subject: 'Английский',
    description:
      'Unit 6, Ex. 3, 4, 5 (стр. 78–79). Письменный перевод текста "Smart Cities". ' +
      'Выучить 20 новых слов из словаря урока, подготовиться к словарному диктанту.',
    deadline: daysFromNow(3),
    photos: [],
    createdAt: new Date(Date.now() - 86_400_000).toISOString(),
    createdBy: 100_000_003,
  },
  {
    id: '6',
    subject: 'История',
    description:
      'Параграфы 22–23. Составить сравнительную таблицу «Причины и последствия ' +
      'Первой мировой войны». Подготовить устный пересказ, возможен опрос.',
    deadline: daysFromNow(7),
    photos: [],
    createdAt: new Date(Date.now() - 5 * 86_400_000).toISOString(),
    createdBy: 100_000_002,
  },
  {
    id: '7',
    subject: 'Русский',
    description:
      'Упражнение 245: расставить знаки препинания в сложноподчинённых предложениях, ' +
      'выделить грамматические основы. Повторить правила пунктуации перед союзом «что».',
    deadline: daysFromNow(-2),
    photos: [],
    createdAt: new Date(Date.now() - 7 * 86_400_000).toISOString(),
    createdBy: 100_000_001,
  },
  {
    id: '8',
    subject: 'Биология',
    description:
      'Параграф 31 «Экосистемы». Составить схему пищевых цепочек леса (не менее 5). ' +
      'Ответить письменно на вопросы 1–4 в конце параграфа.',
    deadline: daysFromNow(10),
    photos: [],
    createdAt: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    createdBy: 100_000_003,
  },
];
