# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""Разделы админ-центра. Импорт пакета регистрирует операции разделов (load_all); сам по себе ничего не делает."""


def load_all():
    """Импортировать все разделы (регистрация операций в core.ops.REGISTRY)."""
    from . import panel_users, status, players, feed, items, itemedit, accounts, online, rename, progress, jobchange, password, accountnew, charrestore, charmove, itemgive, gifts, titles, skills, pets, quests, social, soulmate, friends, clan, live, charrest, charcopy, itemrecover, dupes, accountclose, gmflag, discordlinks, shopcs, stack, maint, events, dbbackup, dbstand, bakdrop, econ, acdaily, autoblock, namereview, cases, gp7adjust, reports, chatlog, attendance, releases, crashes, outbox, notify, community, notes  # noqa: F401
