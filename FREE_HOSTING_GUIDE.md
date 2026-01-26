# دليل الاستضافة المجانية 100% (Render + MongoDB) 💸🚀

هذه الطريقة تضمن لك:
1.  **استضافة مجانية** للبوت (على Render).
2.  **حفظ دائم للبيانات** (على MongoDB) حتى لا تضيع عند إعادة التشغيل.
3.  **عمل دائم 24/7** (باستخدام UptimeRobot).

---

## الخطوة 1: تجهيز قاعدة البيانات (MongoDB) 🗄️
نحتاج لمكان نحفظ فيه أسماء الأعضاء لأنه Render بيمسح الملفات.

1.  ادخل على موقع [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) وسجل حساب مجاني.
2.  أنشئ Cluster جديد (اختر الخيار المجاني **Shared** -> **FREE**).
3.  أنشئ مستخدم للقاعدة (User):
    *   اذهب إلى **Database Access** -> **Add New Database User**.
    *   اختر اسم وباسوورد (تذكرهم جيداً!).
4.  اسمح بالاتصال من أي مكان:
    *   اذهب إلى **Network Access** -> **Add IP Address**.
    *   اختر **Allow Access from Anywhere** (0.0.0.0/0).
5.  احصل على رابط الاتصال:
    *   اذهب إلى **Database** -> **Connect** -> **Drivers**.
    *   انسخ الرابط الذي يشبه:
        `mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority`
    *   **هام:** استبدل `<username>` و `<password>` ببياناتك. هذا هو `MONGO_URI` الخاص بك.

---

## الخطوة 2: رفع البوت على Render ☁️

1.  اعمل حساب على [GitHub](https://github.com/) وارفع ملفات البوت عليه (في Repository جديد).
    *   الملفات المطلوبة: `bot.py` و `requirements.txt`.
2.  ادخل على [Render](https://render.com/) وسجل حساب.
3.  اضغط **New +** واختر **Web Service**.
4.  اربطه بحساب GitHub واختر الـ Repository تبعك.
5.  في الإعدادات:
    *   **Runtime:** Python 3
    *   **Build Command:** `pip install -r requirements.txt`
    *   **Start Command:** `python bot.py`
6.  **أهم خطوة (Environment Variables):**
    *   اضف `BOT_TOKEN` وضع توكن البوت.
    *   اضف `MONGO_URI` وضع رابط قاعدة البيانات الذي نسخته في الخطوة 1.

---

## الخطوة 3: كيف تخليه ما ينام؟ (UptimeRobot) ⏰
استضافات الريندر المجانية بتدخل في وضع النوم (Sleep) إذا ما حدا استخدمها.
*   ملاحظة: هذا ينطبق فقط على **Web Service**.
*   الحل: سجل في [UptimeRobot](https://uptimerobot.com/) واعمل Monitor جديد يفتح رابط موقعك كل 5 دقائق.
*   **تريك بسيط:** عشان يكون عندك رابط، لازم تضيف كود بسيط في `bot.py` يشغل سيرفر ويب وهمي (Flask).

**إذا بدك أضيف لك كود "سيرفر الويب الوهمي" عشان يزبط مع UptimeRobot خبرني!** (حالياً سيعمل بدون Flask لكن قد ينام إذا لم تستخدمه لفترة).
