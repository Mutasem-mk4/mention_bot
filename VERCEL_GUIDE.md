# دليل النقل إلى Vercel 🔼

بما أنك اخترت الانتقال لـ Vercel، إليك الخطوات لأن طريقة عمله تختلف قليلاً (يستخدم Webhooks بدلاً من Polling).

## 1. التجهيز
لقد قمت أنا بتجهيز الملفات اللازمة:
*   `api/webhook.py`: هذا الملف الذي يستقبل الرسائل من تيليجرام.
*   `vercel.json`: إعدادات السيرفر.
*   `requirements.txt`: المكتبات المطلوبة.

---

## 2. رفع الكود لـ Vercel
1.  ادخل على [Vercel.com](https://vercel.com/) وسجل الدخول (بواسطة GitHub).
2.  اضغط **Add info** -> **Project**.
3.  اختر مشروع البوت (`mention_bot`) من القائمة واضغط **Import**.
4.  في خانة **Environment Variables** أضف:
    *   `BOT_TOKEN`: نفس التوكن القديم.
    *   `MONGO_URI`: نفس رابط قاعدة البيانات.
5.  اضغط **Deploy**.

---

## 3. ربط البوت (أهم خطوة!) 🔗
بعد أن يصبح الموقع Live، سيظهر لك رابط (Domain)، مثلاً:
`https://mention-bot.vercel.app`

عليك إخبار تيليجرام بهذا الرابط. افتح المتصفح وادخل على هذا الرابط (بعد تعديل التوكن والرابط):

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<YOUR_VERCEL_URL>/api/webhook
```

1.  استبدل `<TOKEN>` بتوكن البوت.
2.  استبدل `<YOUR_VERCEL_URL>` برابط موقعك على Vercel.
3.  اضغط Enter.

إذا ظهرت لك رسالة `Webhook was set`، مبروك! البوت يعمل الآن 24/7 مجاناً وبدون توقف. 🎉
