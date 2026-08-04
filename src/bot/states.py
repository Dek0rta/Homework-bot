"""FSM-состояния бота."""

from aiogram.fsm.state import State, StatesGroup


class ScheduleSetup(StatesGroup):
    choosing_day         = State()  # выбор дня в редакторе расписания
    entering_lesson_name = State()  # ввод названия предмета для слота


class CalendarAuth(StatesGroup):
    waiting_for_code = State()


class HomeworkConfirm(StatesGroup):
    choosing_day = State()
