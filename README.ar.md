<div align="center">

[English](README.md) · [Русский](README.ru.md) · **العربية**

### ❤️ هل أعجبك المشروع؟ ادعم هذا العمل الشاق على [**Boosty**](https://boosty.to/sitxovski_yurii)

# Astory Admin Center

**لوحة ويب لإدارة خادم لعبة Astory — اللاعبون، ومكافحة الغش، والفعاليات، والإصدارات، والمجتمع في مكان واحد**

[Astory Client](https://github.com/sitxovski/AstoryClient) · [Astory Server](https://github.com/sitxovski/AstoryServer) · [Astory Admin Center](https://github.com/sitxovski/AstoryAdminCenter)

</div>

---

<div dir="rtl">

> ⚠️ تنبيه. هذه الحزمة وحدها (وليس المشروع بأكمله) أُعدّت باستخدام Claude Code، وقد تحتوي على بعض الأخطاء. أما المشروع نفسه فقد طُوِّر يدويًا بالكامل. للحصول على المساعدة، راسلني على Discord ‏(@sitxovski).

## ما الذي تقدّمه اللوحة؟

- 👤 **اللاعبون** — الحسابات، والشخصيات، والمخزون، وسجلّ كل عنصر، والبحث عن العناصر المكرّرة، ومن المتصل الآن
- 🛡️ **مكافحة الغش** — السجلّ، والتقرير اليومي، والحظر التلقائي، والقضايا، وسجلّ الدردشة، ومراجعة الأسماء
- 🎉 **اللعبة** — فعاليات الخبرة والغنائم، والتصنيفات، ووضع الصيانة، والمتاجر وبيانات اللعبة مع إمكانية التراجع
- 🚀 **الإصدارات** — حالة الإصدارات، وأعطال العميل، وملاحظات كل إصدار
- 💬 **المجتمع** — الإعلانات والأوامر في Discord، وبلاغات اللاعبين، وتنبيهات لمالك الخادم عبر Telegram
- 📜 **الأمان** — الأدوار، وتسجيل الدخول بخطوتين، وسجلّ تدقيق لكل إجراء مع إمكانية التراجع عنه

تعمل اللوحة على خادم اللعبة (HTTPS)، وتُنشر من حاسوبك عبر SSH. ويشبه مظهرها نوافذ اللعبة.

## البدء السريع

1. **التثبيت** — شغّل `Prerequisites\install_prerequisites.bat` على حاسوبك، و`... -Server` على الخادم ([التفاصيل](Prerequisites/README.md)).
2. **الإعداد** — شغّل `_setup\configure.bat` (عنوان الخادم، ومفتاح SSH، ومعرّفات Discord — [من أين تحصل عليها](_setup/SETUP.md)).
   شغّله في النسخ **الثلاث** كلها (AstoryClient وAstoryServer وAstoryAdminCenter): تستخدم اللوحة والبوت الملفين `AstoryClient\Tools\asda_paths.py`
   و`AstoryServer\Tools\Anticheat\db_connect.py`؛ تُحفظ إجاباتك، فلا تسألك النسخ الأخرى إلا عن الجديد.
3. **النشر** — `python deploy\deploy_admin_center.py --skip-selftest`
   يتولى النشر نسخ اللوحة إلى الخادم وتثبيت كائنات SQL الخاصة بها (`sql\*.sql`) تلقائيًا — لا حاجة لتشغيلها يدويًا.
   (من دون `--skip-selftest` يشغّل النشر أولًا الاختبار الذاتي دون اتصال، ويتطلب ذلك وجود SQL Server **LocalDB** على حاسوبك،
   ويتخطى الفحوص التي تحتاج إلى ملفات بيئة التطوير الخاصة بالمؤلف — راجع [Prerequisites](Prerequisites/README.md#3-deploy--build)).
   بعد أول نشر شغّل على الخادم `AstoryServer\Prerequisites\setup_server.ps1 -SyncAdminBridge` ثم أعد تشغيل الخادم — فهو يمنح خوادم اللعبة مفاتيح جسر اللوحة.
4. **فتح اللوحة** — شغّل `bat\AdminCenter.bat` ← *tunnel*، ثم افتح `https://localhost:17890/`

الدليل الكامل: [`GUIDE.md`](GUIDE.md) (باللغة الروسية).

تعمل اللوحة مع [Astory Server](https://github.com/sitxovski/AstoryServer) (الخادم الذي تديره)
ومع [Astory Client](https://github.com/sitxovski/AstoryClient) (الإصدارات وتقارير الأعطال).

## المؤلف

صاحب المشروع: **@sitxovski** ‏(Discord).

يمكنك استخدامه بحرية لأي غرض ودون أي قيود — [رخصة MIT](LICENSE). **فقط اذكر المؤلف الأصلي — @sitxovski ‏(Discord) —
وضع رابطًا لهذا المستودع عند نسخ أي جزء منه أو تفريعه (fork) أو إعادة استخدامه.**

</div>

---

<div align="center">

### ❤️ ادعم هذا العمل الشاق على [**Boosty**](https://boosty.to/sitxovski_yurii)

</div>
