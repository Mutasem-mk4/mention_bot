"""
Telegram Userbot - @all Mention
يوزربوت لعمل منشن لجميع أعضاء المجموعة
استخدم @all لمنشن الجميع - 5 أعضاء في كل رسالة
"""

import os
import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ChatMembersFilter
from dotenv import load_dotenv

# تحميل المتغيرات البيئية
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# إنشاء العميل
app = Client("mention_userbot", api_id=API_ID, api_hash=API_HASH)


@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    """أمر البداية"""
    await message.reply_text(
        "🤖 مرحباً! أنا يوزربوت المنشن\n\n"
        "📋 كيفية الاستخدام:\n"
        "• أرسل @all في أي مجموعة لمنشن جميع الأعضاء\n"
        "• يتم المنشن لـ 5 أعضاء في كل رسالة\n\n"
        "⚠️ ملاحظة: يعمل فقط في المجموعات التي أنت عضو فيها"
    )


@app.on_message(filters.regex(r"@all") & filters.group)
async def mention_all(client, message):
    """منشن لجميع أعضاء المجموعة"""
    chat_id = message.chat.id
    sender_id = message.from_user.id
    
    await message.reply_text("📢 جاري جمع الأعضاء...")
    
    # جمع جميع الأعضاء
    members = []
    try:
        async for member in client.get_chat_members(chat_id):
            user = member.user
            # تجاهل البوتات والمرسل نفسه
            if user.is_bot or user.id == sender_id:
                continue
            members.append({
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name or "User"
            })
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")
        return
    
    if len(members) == 0:
        await message.reply_text("📭 لا يوجد أعضاء لعمل منشن لهم!")
        return
    
    total_members = len(members)
    batch_size = 5
    
    # تقسيم الأعضاء إلى مجموعات من 5
    for i in range(0, total_members, batch_size):
        batch = members[i:i + batch_size]
        mentions = []
        
        for member in batch:
            if member["username"]:
                mentions.append(f"@{member['username']}")
            else:
                mentions.append(f"[{member['first_name']}](tg://user?id={member['id']})")
        
        batch_num = (i // batch_size) + 1
        total_batches = (total_members + batch_size - 1) // batch_size
        
        text = f"📣 ({batch_num}/{total_batches}): " + " ".join(mentions)
        
        await message.reply_text(text)
        
        # انتظار قصير بين الرسائل
        if i + batch_size < total_members:
            await asyncio.sleep(1)
    
    await message.reply_text(f"✅ تم منشن {total_members} عضو!")


print("🚀 جاري تشغيل اليوزربوت...")
print("📌 استخدم @all في أي مجموعة لمنشن الجميع")
app.run()
