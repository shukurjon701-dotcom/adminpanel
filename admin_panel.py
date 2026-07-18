"""
admin_panel.py — веб-админ-панель для Academy of Arabic bot.

Запуск:  python3 admin_panel.py
Откройте: http://localhost:8000  (логин/пароль — см. .env)

Разделы:
- Дашборд: сколько пользователей всего / онлайн сейчас / сообщений сегодня
- Пользователи: список с username, именем, датой первого/последнего визита
- Запросы: лента последних вопросов пользователей и ответов ИИ
- Обучение ИИ: добавить знания текстом, документом (.txt/.pdf/.docx) или
  картинкой (через модель Groq с поддержкой изображений) — сохраняется в
  базу знаний, которую bot.py подмешивает в системный промпт.
"""

import os
import secrets

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn
from dotenv import load_dotenv
from groq import Groq

import database as db

load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8000"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview")

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

app = FastAPI(title="Academy of Arabic — Admin Panel")
security = HTTPBasic()

db.init_db()


def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Academy of Arabic — Admin Panel</title>
<style>
  :root { --bg:#0f1117; --card:#171a23; --accent:#4f8cff; --text:#e6e8ee; --muted:#8b92a5; --green:#3ecf8e; --border:#262a37; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--text); }
  header { padding:20px 32px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; }
  header h1 { font-size:18px; margin:0; }
  nav { display:flex; gap:8px; }
  nav button { background:none; border:1px solid var(--border); color:var(--muted); padding:8px 16px; border-radius:8px; cursor:pointer; font-size:14px; }
  nav button.active { background:var(--accent); color:white; border-color:var(--accent); }
  main { padding:32px; max-width:1100px; margin:0 auto; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:32px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px; }
  .card .value { font-size:32px; font-weight:700; }
  .card .label { color:var(--muted); font-size:13px; margin-top:4px; }
  table { width:100%; border-collapse:collapse; background:var(--card); border-radius:12px; overflow:hidden; }
  th, td { text-align:left; padding:12px 16px; border-bottom:1px solid var(--border); font-size:14px; }
  th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; }
  .dot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; }
  .dot.online { background:var(--green); } .dot.offline { background:var(--muted); }
  .section { display:none; } .section.active { display:block; }
  .msg-text { color:var(--text); } .msg-answer { color:var(--muted); font-size:13px; margin-top:4px; }
  textarea, input[type=text] { width:100%; background:#10131b; border:1px solid var(--border); color:var(--text); border-radius:8px; padding:10px; font-family:inherit; font-size:14px; }
  textarea { min-height:120px; resize:vertical; }
  .form-card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:24px; margin-bottom:24px; }
  .form-card h3 { margin-top:0; }
  .form-row { margin-bottom:14px; }
  label { display:block; margin-bottom:6px; color:var(--muted); font-size:13px; }
  button.primary { background:var(--accent); color:white; border:none; padding:10px 20px; border-radius:8px; cursor:pointer; font-size:14px; }
  button.danger { background:#e5484d; color:white; border:none; padding:6px 12px; border-radius:6px; cursor:pointer; font-size:12px; }
  .badge { font-size:11px; padding:2px 8px; border-radius:20px; background:#262a37; color:var(--muted); }
  #status { font-size:13px; color:var(--muted); margin-top:8px; }
</style>
</head>
<body>
<header>
  <h1>🕌 Academy of Arabic — Admin Panel</h1>
  <nav>
    <button class="tab active" data-tab="dashboard">Дашборд</button>
    <button class="tab" data-tab="users">Пользователи</button>
    <button class="tab" data-tab="messages">Запросы</button>
    <button class="tab" data-tab="training">Обучение ИИ</button>
  </nav>
</header>
<main>

  <section id="dashboard" class="section active">
    <div class="cards">
      <div class="card"><div class="value" id="stat-online">—</div><div class="label">Онлайн сейчас (5 мин)</div></div>
      <div class="card"><div class="value" id="stat-total-users">—</div><div class="label">Всего пользователей</div></div>
      <div class="card"><div class="value" id="stat-today">—</div><div class="label">Сообщений сегодня</div></div>
      <div class="card"><div class="value" id="stat-total-msgs">—</div><div class="label">Всего сообщений</div></div>
    </div>
    <h3>Последние запросы</h3>
    <table><tbody id="dashboard-recent"></tbody></table>
  </section>

  <section id="users" class="section">
    <table>
      <thead><tr><th>Статус</th><th>Username</th><th>Имя</th><th>ID</th><th>Первый визит</th><th>Последний визит</th><th>Сообщений</th></tr></thead>
      <tbody id="users-table"></tbody>
    </table>
  </section>

  <section id="messages" class="section">
    <table>
      <thead><tr><th>Пользователь</th><th>Сообщение / Ответ</th><th>Время</th></tr></thead>
      <tbody id="messages-table"></tbody>
    </table>
  </section>

  <section id="training" class="section">
    <div class="form-card">
      <h3>📝 Добавить знание текстом</h3>
      <div class="form-row"><label>Заголовок</label><input type="text" id="text-title" placeholder="Например: Адреса филиалов"></div>
      <div class="form-row"><label>Содержание</label><textarea id="text-content" placeholder="Впишите информацию, которую должен запомнить ИИ..."></textarea></div>
      <button class="primary" onclick="submitText()">Сохранить</button>
    </div>

    <div class="form-card">
      <h3>📄 Добавить знание из файла (.txt / .pdf / .docx)</h3>
      <div class="form-row"><input type="file" id="doc-file" accept=".txt,.pdf,.docx"></div>
      <button class="primary" onclick="submitDoc()">Загрузить и обучить</button>
    </div>

    <div class="form-card">
      <h3>🖼️ Добавить знание из картинки</h3>
      <div class="form-row"><input type="file" id="img-file" accept="image/*"></div>
      <button class="primary" onclick="submitImage()">Загрузить и распознать</button>
      <div id="status"></div>
    </div>

    <h3>База знаний</h3>
    <table>
      <thead><tr><th>Тип</th><th>Заголовок</th><th>Содержание</th><th>Добавлено</th><th></th></tr></thead>
      <tbody id="knowledge-table"></tbody>
    </table>
  </section>

</main>

<script>
const AUTH_HEADER = {};

document.querySelectorAll('.tab').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
  };
});

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('ru-RU');
}

async function loadStats() {
  const r = await fetch('/api/stats'); const s = await r.json();
  document.getElementById('stat-online').textContent = s.online_now;
  document.getElementById('stat-total-users').textContent = s.total_users;
  document.getElementById('stat-today').textContent = s.messages_today;
  document.getElementById('stat-total-msgs').textContent = s.total_messages;
}

async function loadUsers() {
  const r = await fetch('/api/users'); const users = await r.json();
  document.getElementById('users-table').innerHTML = users.map(u => `
    <tr>
      <td><span class="dot ${u.online ? 'online' : 'offline'}"></span>${u.online ? 'Онлайн' : 'Оффлайн'}</td>
      <td>${u.username ? '@' + u.username : '—'}</td>
      <td>${u.full_name || '—'}</td>
      <td>${u.telegram_id}</td>
      <td>${fmtDate(u.first_seen)}</td>
      <td>${fmtDate(u.last_seen)}</td>
      <td>${u.message_count}</td>
    </tr>`).join('');
}

async function loadMessages() {
  const r = await fetch('/api/messages'); const msgs = await r.json();
  const rowsHtml = msgs.map(m => `
    <tr>
      <td>${m.username ? '@' + m.username : m.telegram_id}</td>
      <td><div class="msg-text">🙋 ${escapeHtml(m.text)}</div><div class="msg-answer">🤖 ${escapeHtml((m.answer||'').slice(0,200))}</div></td>
      <td>${fmtDate(m.created_at)}</td>
    </tr>`).join('');
  document.getElementById('messages-table').innerHTML = rowsHtml;
  document.getElementById('dashboard-recent').innerHTML = rowsHtml.split('</tr>').slice(0,8).join('</tr>');
}

function escapeHtml(str) {
  const d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML;
}

async function loadKnowledge() {
  const r = await fetch('/api/knowledge'); const items = await r.json();
  document.getElementById('knowledge-table').innerHTML = items.map(k => `
    <tr>
      <td><span class="badge">${k.source_type}</span></td>
      <td>${escapeHtml(k.title)}</td>
      <td>${escapeHtml(k.content.slice(0,150))}${k.content.length>150?'…':''}</td>
      <td>${fmtDate(k.created_at)}</td>
      <td><button class="danger" onclick="deleteKnowledge(${k.id})">Удалить</button></td>
    </tr>`).join('');
}

async function deleteKnowledge(id) {
  if (!confirm('Удалить эту запись из базы знаний?')) return;
  await fetch('/api/knowledge/' + id, { method: 'DELETE' });
  loadKnowledge();
}

async function submitText() {
  const title = document.getElementById('text-title').value.trim();
  const content = document.getElementById('text-content').value.trim();
  if (!title || !content) return alert('Заполните заголовок и содержание');
  const fd = new FormData(); fd.append('title', title); fd.append('content', content);
  await fetch('/api/knowledge/text', { method: 'POST', body: fd });
  document.getElementById('text-title').value = '';
  document.getElementById('text-content').value = '';
  loadKnowledge();
}

async function submitDoc() {
  const file = document.getElementById('doc-file').files[0];
  if (!file) return alert('Выберите файл');
  const fd = new FormData(); fd.append('file', file);
  const status = document.getElementById('status');
  status.textContent = 'Загрузка и обработка...';
  const r = await fetch('/api/knowledge/document', { method: 'POST', body: fd });
  status.textContent = r.ok ? 'Готово ✅' : 'Ошибка при обработке файла';
  loadKnowledge();
}

async function submitImage() {
  const file = document.getElementById('img-file').files[0];
  if (!file) return alert('Выберите картинку');
  const fd = new FormData(); fd.append('file', file);
  const status = document.getElementById('status');
  status.textContent = 'Распознаём изображение через ИИ...';
  const r = await fetch('/api/knowledge/image', { method: 'POST', body: fd });
  status.textContent = r.ok ? 'Готово ✅' : 'Ошибка при распознавании';
  loadKnowledge();
}

function refreshAll() { loadStats(); loadUsers(); loadMessages(); loadKnowledge(); }
refreshAll();
setInterval(refreshAll, 5000);
</script>
</body>
</html>
"""


@app.get("/health")
async def health():
    """Публичный эндпоинт без авторизации.

    Нужен, чтобы сервис-пингер (UptimeRobot) раз в несколько минут дёргал URL
    и Render не усыплял бесплатный инстанс — тогда Telegram-бот работает 24/7.
    """
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def dashboard(user: str = Depends(check_auth)):
    return DASHBOARD_HTML


@app.get("/api/stats")
async def api_stats(user: str = Depends(check_auth)):
    return db.get_stats()


@app.get("/api/users")
async def api_users(user: str = Depends(check_auth)):
    return db.get_users()


@app.get("/api/messages")
async def api_messages(user: str = Depends(check_auth)):
    return db.get_recent_messages()


@app.get("/api/knowledge")
async def api_knowledge(user: str = Depends(check_auth)):
    return db.get_knowledge()


@app.delete("/api/knowledge/{knowledge_id}")
async def api_delete_knowledge(knowledge_id: int, user: str = Depends(check_auth)):
    db.delete_knowledge(knowledge_id)
    return {"ok": True}


@app.post("/api/knowledge/text")
async def api_add_text(title: str = Form(...), content: str = Form(...), user: str = Depends(check_auth)):
    db.add_knowledge(title=title, content=content, source_type="text")
    return {"ok": True}


@app.post("/api/knowledge/document")
async def api_add_document(file: UploadFile = File(...), user: str = Depends(check_auth)):
    raw = await file.read()
    name = file.filename or "document"
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""

    if ext == "txt":
        text = raw.decode("utf-8", errors="ignore")
    elif ext == "pdf":
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    elif ext == "docx":
        from docx import Document
        import io
        document = Document(io.BytesIO(raw))
        text = "\n".join(p.text for p in document.paragraphs)
    else:
        raise HTTPException(status_code=400, detail="Поддерживаются только .txt, .pdf, .docx")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Не удалось извлечь текст из файла")

    db.add_knowledge(title=name, content=text[:8000], source_type="document")
    return {"ok": True}


@app.post("/api/knowledge/image")
async def api_add_image(file: UploadFile = File(...), user: str = Depends(check_auth)):
    if not groq_client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY не задан")

    import base64
    raw = await file.read()
    b64 = base64.b64encode(raw).decode()
    mime = file.content_type or "image/jpeg"

    completion = groq_client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Опиши подробно, что изображено на картинке, и извлеки весь читаемый текст, если он есть. Ответ дай на узбекском языке."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        max_tokens=1000,
    )
    description = completion.choices[0].message.content.strip()
    db.add_knowledge(title=file.filename or "image", content=description, source_type="image")
    return {"ok": True, "description": description}


if __name__ == "__main__":
    print(f"🖥️  Admin panel: http://localhost:{ADMIN_PORT}  (логин: {ADMIN_USERNAME})")
    uvicorn.run(app, host="0.0.0.0", port=ADMIN_PORT)
