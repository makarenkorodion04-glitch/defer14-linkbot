import json
import os
from datetime import datetime, timezone

import requests

API = "https://api.telegram.org"
TOKEN = os.environ["BOT_TOKEN"]
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "defer14").lower().lstrip("@")
INTERVAL_SECONDS = int(os.environ.get("SEND_INTERVAL_HOURS", "3")) * 3600
DATA_FILE = "data.json"

DEFAULT_CONTENT = "Твоё сообщение здесь"


def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data.setdefault("users", [])
    data.setdefault("content", DEFAULT_CONTENT)
    data.setdefault("last_sent", 0)
    data.setdefault("pending", False)
    data.setdefault("offset", 0)
    return data


def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def call(method, **params):
    try:
        r = requests.post(f"{API}/bot{TOKEN}/{method}", json=params, timeout=40)
        return r.json()
    except Exception as e:
        print("API error", method, e)
        return {"ok": False}


def panel_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📊 Статистика", "callback_data": "stat"}],
            [{"text": "👁 Показать сообщение", "callback_data": "showcontent"}],
            [{"text": "✏️ Изменить сообщение", "callback_data": "editcontent"}],
            [{"text": "🚀 Отправить сейчас", "callback_data": "sendnow"}],
        ]
    }


def is_admin(username):
    return (username or "").lower().lstrip("@") == ADMIN_USERNAME


def broadcast(content):
    data = load()
    sent = 0
    for chat in data["users"]:
        if call("sendMessage", chat_id=chat, text=content).get("ok"):
            sent += 1
    return sent


def panel_text(data):
    return (
        "👑 Админ-панель\n\n"
        f"📝 Сообщение: {data['content']}\n"
        f"👥 Подписчиков: {len(data['users'])}\n"
        "⏱ Интервал рассылки: 3 ч"
    )


def get_updates(offset):
    res = call(
        "getUpdates",
        offset=offset,
        timeout=0,
        allowed_updates=["message", "callback_query"],
    )
    return res.get("result", []) if res.get("ok") else []


def process_updates(updates, data):
    new_offset = data["offset"]
    for upd in updates:
        new_offset = max(new_offset, upd.get("update_id", 0) + 1)
        if "message" in upd:
            msg = upd["message"]
            chat = msg.get("chat", {}).get("id")
            user = msg.get("from", {}) or {}
            username = (user.get("username") or "").lower().lstrip("@")
            text = (msg.get("text") or "").strip()
            if text.startswith("/start"):
                if chat not in data["users"]:
                    data["users"].append(chat)
                data["pending"] = False
                call(
                    "sendMessage",
                    chat_id=chat,
                    text="Привет! Ты подписан на рассылку.\nНовые сообщения будут приходить каждые 3 часа.",
                )
            elif text == "/link":
                call("sendMessage", chat_id=chat, text=data["content"])
            elif text == "/cancel":
                data["pending"] = False
                call("sendMessage", chat_id=chat, text="Отменено.")
            elif text == "/panel":
                if is_admin(username):
                    call(
                        "sendMessage",
                        chat_id=chat,
                        text=panel_text(data),
                        reply_markup=panel_keyboard(),
                    )
            elif data.get("pending") and is_admin(username):
                if text:
                    data["content"] = text
                    data["pending"] = False
                    call(
                        "sendMessage",
                        chat_id=chat,
                        text="✅ Сообщение сохранено и будет рассылаться:\n\n" + text,
                        reply_markup=panel_keyboard(),
                    )
        elif "callback_query" in upd:
            cq = upd["callback_query"]
            user = cq.get("from", {}) or {}
            username = (user.get("username") or "").lower().lstrip("@")
            chat = cq.get("message", {}).get("chat", {}).get("id")
            cb = cq.get("data", "")
            call("answerCallbackQuery", callback_query_id=cq.get("id"))
            if not is_admin(username):
                continue
            if cb == "stat":
                call(
                    "sendMessage",
                    chat_id=chat,
                    text="📊 Статистика\n\n"
                    f"👥 Подписчиков: {len(data['users'])}\n"
                    "⏱ Рассылка каждые 3 ч\n"
                    f"📝 Сообщение: {data['content']}",
                    reply_markup=panel_keyboard(),
                )
            elif cb == "showcontent":
                call(
                    "sendMessage",
                    chat_id=chat,
                    text=f"📝 Текущее сообщение:\n{data['content']}",
                    reply_markup=panel_keyboard(),
                )
            elif cb == "editcontent":
                data["pending"] = True
                call(
                    "sendMessage",
                    chat_id=chat,
                    text="✏️ Пришли текстом новое сообщение. Отмена — /cancel",
                )
            elif cb == "sendnow":
                sent = broadcast(data["content"])
                data["last_sent"] = datetime.now(timezone.utc).timestamp()
                call(
                    "sendMessage",
                    chat_id=chat,
                    text=f"🚀 Отправлено подписчикам: {sent}",
                    reply_markup=panel_keyboard(),
                )
    data["offset"] = max(data["offset"], new_offset)
    return data


def main():
    data = load()
    data = process_updates(get_updates(data["offset"]), data)
    now = datetime.now(timezone.utc).timestamp()
    if (
        data["users"]
        and data["content"].strip()
        and (now - data["last_sent"]) >= INTERVAL_SECONDS
    ):
        sent = broadcast(data["content"])
        data["last_sent"] = now
        print("Broadcast sent:", sent)
    save(data)
    print("Done. offset:", data["offset"])


if __name__ == "__main__":
    main()