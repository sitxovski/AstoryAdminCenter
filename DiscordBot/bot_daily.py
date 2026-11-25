#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""bot_daily.py — когда слать ежедневную сводку бота в staff-chat (★ ревизия 67 Н-3, 22.11.2026; oracle_bot.daily_report).

Было: daily_report = tasks.loop(hours=24) — первая итерация сразу при старте, поэтому КАЖДЫЙ перезапуск бота (и подъём вотчдогом после
падения) публиковал сводку. Стало: цикл проверяет раз в час, а сводка уходит, только если с прошлой прошло не меньше MIN_GAP_H часов; время
прошлой — state.json «daily_last_utc» (ISO UTC), пишется после отправки. Ритм «раз в сутки» прежний (23 ч + шаг проверки ≤ 1 ч ≈ сутки).
Отметки ещё нет (первый старт новой версии) — сводка НЕ шлётся, отметка ставится «сейчас»: перезапуск никогда не публикует неожиданно,
следующая сводка — через 23 ч. Побочных эффектов при импорте нет.
"""
import datetime as dt

MIN_GAP_H = 23
CHECK_MINUTES = 60


def parse(v):
    """ISO-строка отметки → aware UTC или None (пусто / мусор)."""
    if not v:
        return None
    try:
        t = dt.datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def decide(last_iso, now):
    """→ (слать ли сейчас, новая отметка ISO или None — не менять). now — aware UTC."""
    last = parse(last_iso)
    if last is None:
        return False, now.isoformat()              # отметки нет — не публиковать при старте, начать отсчёт
    if now - last >= dt.timedelta(hours=MIN_GAP_H):
        return True, None                          # отметку ставит вызывающий ПОСЛЕ успешной отправки
    return False, None
