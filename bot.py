import asyncio
import logging
import os
import re
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from dotenv import load_dotenv
from groq import Groq

import database as db

load_dotenv()

# .strip() убирает случайные пробелы/переносы строки по краям значения
# (частая ошибка при копировании токена) — иначе aiogram ругается на пробелы.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY:
    raise RuntimeError(
        "Не найдены TELEGRAM_BOT_TOKEN или GROQ_API_KEY. "
        "Проверьте файл .env рядом с bot.py."
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("academy_bot")

db.init_db()

BASE_SYSTEM_PROMPT = """\
Sen — "Academy of Arabic" o'quv markazining sun'iy intellekt yordamchisisan. \
Markaz arab tilini o'rgatadi. Sening vazifang:
- foydalanuvchiga do'stona, aniq va tushunarli tarzda kurslar, narxlar, \
  auditoriya, talab qilinadigan bilim (prerequisites) haqida ma'lumot berish;
- kerak bo'lsa arab tili fonetikasi, grammatikasi, alifbosi bo'yicha oddiy \
  tushuntirishlar berish;
- pastda berilgan ma'lumotlardan tashqari narsalarni (masalan aniq dars \
  jadvali, o'qituvchilar ismi, filial manzili kabi) bilmasang — buni \
  administrator bilan aniqlashtirishni taklif qil, hech qachon o'ylab topma;
- muloyim, qisqa va aniq gaplash, emojidan me'yorida foydalanish.

=== JAVOB TILI HAQIDA QAT'IY QOIDA ===
- HAR QANDAY holatda javobingni FAQAT LOTIN ALIFBOSIDA yoz. Kirill \
  harflaridan (rus, o'zbek yoki boshqa kirillcha yozuvdan) BUTUNLAY \
  foydalanma — bitta ham kirill harfi bo'lmasin.
- Agar foydalanuvchi o'zbek tilida yozsa — o'zbek tilida, lotin alifbosida javob ber.
- Agar foydalanuvchi rus tilida (kirillchada) yozsa — MAZMUNAN rus tilida \
  javob ber, lekin matnni lotin harflarida yoz (rus tilini lotin \
  transliteratsiyasida, masalan "Privet, kursy narxi 350000 so'm" kabi).
- Agar foydalanuvchi ingliz tilida yozsa — ingliz tilida, lotin alifbosida javob ber.
- Agar foydalanuvchi arab tilida yozsa — arab tilida javob ber (arab yozuvi \
  bu qoidadan istisno, chunki arab tili darsi uchun arab harflari zarur).
- Javobda ruscha yoki o'zbekcha so'zlarni kirillchada yozma — faqat lotin \
  harflarida yoz (masalan "грамматика" emas, "grammatika"; "правила" emas, \
  "qoidalar" yoki "pravila").
- Hech qachon qozoq tiliga xos so'z va qo'shimchalardan foydalanma — bu \
  boshqa til va foydalanuvchini chalg'itadi.
- Bitta javob ichida bir nechta til yoki alifboni aralashtirma.
- Agar qaysi tilda javob berishni aniqlay olmasang — standart holatda \
  o'zbek tilida (lotin yozuvida) javob ber.

=== O'YLAB TOPMASLIK HAQIDA QAT'IY QOIDA ===
- Pastda "KURSLAR HAQIDA MA'LUMOT" bo'limida berilgan ma'lumotlar — bu \
  yagona haqiqiy manba. Boshqa hech qanday manbadan (umumiy bilimingdan) \
  kurs davomiyligi, daraja nomlari (masalan A1/A2/B1/CEFR aniq oylar), \
  dars jadvali yoki metodika tafsilotlarini QO'SHIB CHIQARMA.
- Agar foydalanuvchi "necha oyda o'rganaman", "qancha vaqt kerak" kabi \
  savol bersa va bu haqda pastdagi ma'lumotlarda aniq raqam yo'q bo'lsa — \
  taxminiy muddat o'ylab topma, buning o'rniga bu individual va \
  administrator/o'qituvchi bilan suhbatda aniqlanishini ayt.
- Faqat pastda ro'yxatlangan 5 ta kursni tavsiya qil, boshqa kurs yoki \
  daraja tizimini o'ylab chiqarma.

=== KURSLAR HAQIDA MA'LUMOT ===

1) ARAB TILI FONETIKASI KURSI (oflayn)
Kimlar uchun mos:
- Arab tilini noldan tez va oson o'rganmoqchi bo'lganlar
- Arab tilida erkin o'qish va gapirishni istovchilar
- Kuchli talaffuz va mustahkam baza qurmoqchi bo'lganlar
- Zamonaviy metodika orqali natijali ta'lim izlayotganlar
- Guruhli ta'limda ham individual uslub xohlaydiganlar uchun
Talab qilinadigan bilim: talab qilinmaydi (noldan boshlash mumkin)
Narx: 350 000 / 550 000 / 750 000 so'm (tarif turiga qarab)

2) ARAB TILI GRAMMATIKASI KURSI (oflayn)
Kimlar uchun mos:
- Arabcha gaplarni tushunish va mustaqil gap tuzishni xohlovchilar
- Grammatik xatolarsiz yozish va so'zlashni o'rganmoqchi bo'lganlar
- Arab tilini tizimli va amaliy tarzda o'rganishni istovchilar
- CEFR darajadagi sertifikat olishni maqsad qilganlar
- Arab tilini professional bosqichga olib chiqishni rejalashtirayotganlar
Talab qilinadigan bilim: arab alifbosi va asosiy qoidalarini bilish talab qilinadi
Narx: 350 000 / 550 000 / 750 000 so'm (tarif turiga qarab)

3) ONLINE ARAB TILI FONETIKASI KURSI
Kimlar uchun mos:
- Masofadan turib sifatli arab tili ta'limini olishni istovchilar
- Arabcha o'qishni noldan boshlamoqchi bo'lganlar
- Talaffuz va o'qishni professional darajada shakllantirmoqchi bo'lganlar
- Vaqtini tejab online formatda o'qishni afzal ko'radiganlar
- Arab tilini keyingi bosqichlarga puxta tayyorgarlik bilan boshlamoqchi bo'lganlar
Talab qilinadigan bilim: talab qilinmaydi
Narx: 350 000 so'm

4) ONLINE ARAB TILI GRAMMATIKASI KURSI
Kimlar uchun mos:
- Online formatda arab tilini chuqur o'rganishni istovchilar
- Arab tilida erkin gapirish va yozishni maqsad qilganlar
- Nahv va sarfni zamonaviy metodika asosida o'rganmoqchi bo'lganlar
- CEFR darajadagi sertifikat olishga tayyorlanayotganlar
- Ish, o'qish yoki sayohat uchun arab tilini professional darajada egallashni istovchilar
Talab qilinadigan bilim: talab qilinmaydi
Narx: 350 000 so'm

5) ARABIC KIDS KURSI (bolalar uchun)
Kimlar uchun mos:
- Farzandining yoshligidan til o'rganishini istovchi ota-onalar uchun
- Arab tilini o'yin va interaktiv metodika orqali o'rganadigan bolalar uchun
- Foydali muhitda bilim va nutqini rivojlantirmoqchi bo'lgan o'quvchilar uchun
- Kelajakda arab tilini erkin o'rganishga mustahkam poydevor qurmoqchi bo'lganlar uchun
Talab qilinadigan bilim: talab qilinmaydi
Narx (tarif bo'yicha):
- Haftasiga 2 kun, 1,5 soat — 300 000 so'm
- Haftasiga 2 kun, 3 soat — 600 000 so'm
- Haftasiga 3 kun, 1,5 soat — 500 000 so'm
- Haftasiga 3 kun, 3 soat — 900 000 so'm
- Haftasiga 5 kun, 1,5 soat — 750 000 so'm
- Haftasiga 5 kun, 3 soat — 1 500 000 so'm

=== JAVOB BERISH QOIDALARI ===
- Foydalanuvchi narx so'rasa — aniq kursning barcha tarif variantlarini ko'rsat.
- Foydalanuvchi "menga qaysi kurs mos" desa — uning maqsadi (nol darajami, \
  grammatikami, bolami, online yoki oflaynmi) haqida qisqa savol ber, \
  keyin mos kursni tavsiya qil.
- Sertifikat, imtihon formati, aniq dars jadvali, o'qituvchilar haqida \
  aniq ma'lumot yo'q — bu haqda administrator bilan bog'lanishni tavsiya qil.
"""


def build_system_prompt() -> str:
    """Базовый промпт + всё, чему администратор обучил ИИ через админ-панель."""
    extra = db.get_knowledge_as_prompt_block()
    if extra:
        return BASE_SYSTEM_PROMPT + "\n\n" + extra
    return BASE_SYSTEM_PROMPT


MAX_HISTORY_MESSAGES = 10

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)

user_histories = defaultdict(lambda: deque(maxlen=MAX_HISTORY_MESSAGES))


def ask_groq(user_id: int, user_text: str) -> str:
    log.info(f"[Groq] Запрос от user_id={user_id}: {user_text!r}")
    history = user_histories[user_id]

    messages = [{"role": "system", "content": build_system_prompt()}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    completion = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.15,
        max_tokens=800,
    )
    answer = completion.choices[0].message.content.strip()
    log.info(f"[Groq] Ответ для user_id={user_id}: {answer[:200]!r}")

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": answer})

    return answer


# Кнопка запроса номера телефона (Telegram отдаёт реальный номер пользователя).
CONTACT_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Telefon raqamni ulashish", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

# Распознаём номер, если пользователь ввёл его текстом (а не кнопкой).
PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")


def looks_like_phone(text: str) -> bool:
    text = text.strip()
    return bool(PHONE_RE.match(text)) and sum(c.isdigit() for c in text) >= 7


@dp.message(CommandStart())
async def cmd_start(message: Message):
    log.info(f"➡️  /start от {message.from_user.full_name} (id={message.from_user.id}, @{message.from_user.username})")
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    user_histories.pop(message.from_user.id, None)
    await message.answer(
        "Ассаляму алейкум! 👋\n\n"
        "Я — ИИ-ассистент учебного центра <b>Academy of Arabic</b>.\n\n"
        "Iltimos, quyidagi tugma orqali telefon raqamingizni ulashing — "
        "administrator siz bilan bog'lana olishi uchun. "
        "Yoki raqamingizni shu yerga yozib yuboring.\n\n"
        "(Пожалуйста, поделитесь номером телефона кнопкой ниже или напишите его "
        "сообщением — чтобы администратор мог связаться с вами.)",
        reply_markup=CONTACT_KEYBOARD,
    )
    log.info(f"✅  Приветствие отправлено пользователю id={message.from_user.id}")


@dp.message(F.contact)
async def handle_contact(message: Message):
    """Пользователь поделился номером через кнопку."""
    phone = message.contact.phone_number
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    db.set_user_phone(message.from_user.id, phone)
    log.info(f"📱 Сохранён номер пользователя id={message.from_user.id}: {phone}")
    await message.answer(
        "Rahmat! Raqamingiz saqlandi ✅\n"
        "Endi savolingizni yozishingiz mumkin.\n\n"
        "(Спасибо, номер сохранён. Теперь можете задать вопрос.)",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    log.info(f"➡️  /reset от id={message.from_user.id}")
    user_histories.pop(message.from_user.id, None)
    await message.answer("Контекст диалога очищен. Начнём заново 🙂")


@dp.message(F.text)
async def handle_text(message: Message):
    log.info(f"➡️  Сообщение от {message.from_user.full_name} (id={message.from_user.id}): {message.text!r}")
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    # Если пользователь прислал номер телефона текстом — сохраняем и не гоняем в ИИ.
    if looks_like_phone(message.text):
        db.set_user_phone(message.from_user.id, message.text.strip())
        log.info(f"📱 Сохранён номер (текстом) id={message.from_user.id}: {message.text.strip()}")
        await message.answer(
            "Rahmat! Raqamingiz saqlandi ✅\n\n(Спасибо, номер сохранён.)",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = ask_groq(message.from_user.id, message.text)
    except Exception as e:
        log.exception(f"❌ Ошибка Groq API для user_id={message.from_user.id}")
        answer = (
            "Извините, произошла ошибка при обращении к ИИ. "
            "Попробуйте, пожалуйста, ещё раз чуть позже."
        )
    await message.answer(answer)
    db.log_message(message.from_user.id, message.from_user.username, message.text, answer)
    log.info(f"✅  Ответ отправлен пользователю id={message.from_user.id}")


async def main():
    log.info("🚀 Бот Academy of Arabic запускается...")
    me = await bot.get_me()
    log.info(f"🤖 Подключились к боту: @{me.username} (id={me.id})")
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("📡 Бот в режиме ожидания сообщений (polling). Пишите /start в Telegram.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
