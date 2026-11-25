#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Публикация контента: реквизиты в Donations и правила (EN/RU/AR) в Rules. Всё закрепляется."""

import asyncio

import discord

from botctl import connect, norm_name

DONATIONS = """\
# 💰 Support the Project / Поддержка проекта

**EN** — Astory Remake is a fan passion project. Donations are always **voluntary** — \
they help us cover servers and development tools. Thank you for believing in the project! 💙

**RU** — Astory Remake — фанатский проект, который делается на энтузиазме. Донаты всегда \
**добровольны** — они идут на серверы и инструменты разработки. Спасибо, что верите в проект! 💙

🪙 **USDT (TRON / TRC20):**
`TGXRDuhWwfKvQHSNzwLG8KhSpDQ8zzr5NZ`

🔗 **Bybit Transfer:**
https://i.bybit.com/L5qaab7
"""

RULES_EN = """\
# 🌟 Welcome to Astory Remake Project!

We're rebuilding the classic MMORPG **Asda Story** — and you're a part of it. \
Just a few simple rules to keep this place cozy:

1. 🤝 **Be kind.** No insults, harassment or hate speech.
2. 📢 **No ads or self-promo** without staff permission (DMs included).
3. 🚫 **No spam**, flood or mention abuse.
4. 🌍 **Mind the language channels:** 💬┃general is for any language, dedicated channels for each one.
5. 🔞 **No NSFW** or shock content.
6. ⚖️ **No politics or religion** debates.
7. 🛡️ **Staff decisions are final.** Questions — DM the moderators, not the public chats.
8. 💙 **Found an issue?** 🎫┃support opens with the Closed Playtest; until then ping a moderator.

Breaking the rules: warning → timeout → ban. Enjoy your stay! ✨
"""

RULES_RU = """\
# 🌟 Добро пожаловать в Astory Remake Project!

Мы воссоздаём классическую MMORPG **Asda Story** — и ты часть этого. \
Несколько простых правил, чтобы всем было уютно:

1. 🤝 **Будь дружелюбен.** Без оскорблений, травли и разжигания.
2. 📢 **Реклама и самопиар** — только с разрешения команды (в личке тоже).
3. 🚫 **Без спама**, флуда и злоупотребления упоминаниями.
4. 🌍 **Соблюдай языковые каналы:** 💬┃general — для любого языка, для каждого языка есть свой канал.
5. 🔞 **Без NSFW** и шок-контента.
6. ⚖️ **Без политики и религии.**
7. 🛡️ **Решения команды окончательны.** Вопросы — модераторам в личку, а не в общий чат.
8. 💙 **Нашёл проблему?** 🎫┃support откроется вместе с закрытым плейтестом, пока пиши модераторам.

Нарушения: предупреждение → тайм-аут → бан. Приятного пребывания! ✨
"""

RULES_AR = """\
# 🌟 أهلاً بكم في Astory Remake Project!

نحن نعيد بناء لعبة **Asda Story** الكلاسيكية — وأنتم جزء من هذا المشروع. \
بعض القواعد البسيطة لنحافظ على أجواء لطيفة:

1. 🤝 **كن لطيفاً.** ممنوع الإهانات أو التحرش أو خطاب الكراهية.
2. 📢 **ممنوع الإعلانات أو الترويج الذاتي** دون إذن الإدارة (حتى في الرسائل الخاصة).
3. 🚫 **ممنوع السبام** أو الفلود أو إساءة استخدام المنشن.
4. 🌍 **احترم قنوات اللغات:** قناة 💬┃general لكل اللغات، ولكل لغة قناتها الخاصة.
5. 🔞 **ممنوع المحتوى غير اللائق.**
6. ⚖️ **ممنوع نقاشات السياسة والدين.**
7. 🛡️ **قرارات الإدارة نهائية.** للاستفسار راسل المشرفين خاصاً.
8. 💙 **وجدت مشكلة؟** قناة 🎫┃support ستفتح مع الاختبار المغلق، وحتى ذلك الحين راسل المشرفين.

المخالفات: تنبيه ← كتم مؤقت ← حظر. نتمنى لكم وقتاً ممتعاً! ✨
"""


async def main() -> None:
    client, guild = await connect()
    try:
        chans = {norm_name(c.name): c for c in await guild.fetch_channels()}
        no_ping = discord.AllowedMentions.none()

        donations = chans["donations"]
        if not [m async for m in donations.history(limit=1)]:
            msg = await donations.send(DONATIONS, allowed_mentions=no_ping)
            await msg.pin(reason="реквизиты")
            print(f"  Donations: {msg.jump_url}")
        else:
            print("  Donations: уже есть сообщения, пропуск")

        rules = chans["rules"]
        if not [m async for m in rules.history(limit=1)]:
            for text in (RULES_EN, RULES_RU, RULES_AR):
                assert len(text) <= 2000, "правила длиннее 2000 символов"
                await rules.send(text, allowed_mentions=no_ping)
            print("  Rules: опубликованы EN/RU/AR")
        else:
            print("  Rules: уже есть сообщения, пропуск")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
