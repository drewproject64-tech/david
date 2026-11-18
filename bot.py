"""David Trade, a private-chat Telegram bot. Requires Python 3.11+."""
import json
import logging
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DESCRIPTION = "Learn forex basics, keep a practice trade journal, and test your knowledge with interactive quizzes inside Telegram."
WELCOME = "Welcome to David Trade. Choose a tool below to learn forex basics, record a practice trade, or take a quick quiz."
LESSONS = (
    ("Currency pairs", "EUR/USD expresses the price of one euro in US dollars. In a practice quote of 1.0800, one euro is priced at 1.08 US dollars."),
    ("Pips", "A pip is a standard unit of price movement. For many pairs it is 0.0001. For many yen pairs it is 0.01."),
    ("Spreads", "The spread is the difference between the ask and bid. A bid of 1.0800 and an ask of 1.0802 give a two-pip spread on EUR/USD."),
    ("Leverage", "Leverage lets a trader control a position larger than the margin posted. It magnifies gains and losses relative to that margin."),
    ("Order types", "A market order seeks immediate execution at available prices. A limit order specifies a price or better and may not fill. A stop order can execute at a different price after activation."),
)
QUIZ = (
    ("What does EUR/USD quote?", ("Dollars per euro", "Euros per dollar", "The spread alone"), 0, "EUR is the base currency and USD is the quote currency."),
    ("What is the spread?", ("The account balance", "The bid-ask difference", "The position size"), 1, "The spread is the ask price minus the bid price."),
    ("What can leverage magnify relative to margin?", ("Only gains", "Only losses", "Gains and losses"), 2, "Leverage increases exposure relative to posted margin."),
    ("Which order specifies a price or better?", ("Market order", "Limit order", "Any order"), 1, "A limit sets a price boundary, and the order may never fill."),
)
MENU = [("Forex Basics", "lessons"), ("Trade Journal", "journal"), ("Forex Quiz", "quiz:0")]
BACK = ("Main Menu", "menu")
JOURNAL = [("Add Entry", "add"), ("View Entries", "view"), BACK]


def keyboard(buttons):
    return {"inline_keyboard": [[{"text": label, "callback_data": data}] for label, data in buttons]}


class TelegramError(Exception):
    def __init__(self, code, retry_after=0):
        super().__init__(f"Telegram request failed with status {code}")
        self.code = code
        self.retry_after = retry_after


class DavidTrade:
    def __init__(self, token, db):
        self.token = token
        self.db = db
        self.pending = set()
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS entries (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, message_id)
            )""")

    def api(self, method, **params):
        request = Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.load(response)
        except HTTPError as error:
            with error:
                try:
                    detail = json.load(error)
                except ValueError:
                    detail = {}
            raise TelegramError(error.code, detail.get("parameters", {}).get("retry_after", 0)) from None
        except (URLError, OSError, ValueError):
            raise TelegramError(503) from None
        if not payload["ok"]:
            raise TelegramError(payload["error_code"])
        return payload["result"]

    def send(self, chat, text, buttons=()):
        params = {"chat_id": chat, "text": text, "link_preview_options": {"is_disabled": True}}
        if buttons:
            params["reply_markup"] = keyboard(buttons)
        self.api("sendMessage", **params)

    def message(self, msg):
        if msg["chat"]["type"] != "private":
            return
        chat = msg["chat"]["id"]
        body = msg.get("text", "").strip()
        command = body.split(maxsplit=1)[0].split("@", 1)[0] if body else ""
        if command in {"/start", "/menu", "/help", "/cancel"}:
            self.pending.discard(chat)
            self.send(chat, WELCOME, MENU)
        elif chat in self.pending:
            if not body or len(body) > 500 or body.startswith("/"):
                self.send(chat, "Send a practice note of 1 to 500 characters, or use /cancel.")
                return
            with self.db:
                self.db.execute(
                    "INSERT OR IGNORE INTO entries (chat_id, message_id, note) VALUES (?, ?, ?)",
                    (chat, msg["message_id"], body),
                )
            self.send(chat, "Practice trade saved.", JOURNAL)
            self.pending.discard(chat)
        else:
            self.send(chat, WELCOME, MENU)

    def callback(self, query):
        try:
            self.api("answerCallbackQuery", callback_query_id=query["id"])
        except TelegramError as error:
            if error.code != 400:
                raise
        msg = query.get("message")
        if not msg or msg["chat"]["type"] != "private":
            return
        chat = msg["chat"]["id"]
        data = query.get("data", "")
        lesson_buttons = [(title, f"lesson:{i}") for i, (title, _) in enumerate(LESSONS)]
        self.pending.discard(chat)
        if data == "menu":
            self.send(chat, WELCOME, MENU)
        elif data == "lessons":
            self.send(chat, "Choose a forex lesson.", [*lesson_buttons, BACK])
        elif data == "journal":
            self.send(chat, "Record and review simulated trades in your practice journal.", JOURNAL)
        elif data == "add":
            self.send(chat, "Send one practice note with the pair, why you entered, the outcome, and what you learned. Use up to 500 characters. Type /cancel to return.")
            self.pending.add(chat)
        elif data.startswith("view"):
            _, _, cursor = data.partition(":")
            if cursor and (not cursor.isascii() or not cursor.isdecimal() or len(cursor) > 16):
                return
            params = (chat, int(cursor)) if cursor else (chat,)
            before = " AND message_id < ?" if cursor else ""
            rows = self.db.execute(
                "SELECT message_id, created_at, note FROM entries WHERE chat_id = ?"
                + before + " ORDER BY message_id DESC LIMIT 6",
                params,
            ).fetchall()
            buttons = [("Older Entries", f"view:{rows[4][0]}")] if len(rows) > 5 else []
            notes = [f"{date} UTC\n{note}" for _, date, note in rows[:5]]
            self.send(chat, "\n\n".join(notes) or "No practice entries here yet.", [*buttons, *JOURNAL])
        else:
            for i, (title, lesson) in enumerate(LESSONS):
                if data == f"lesson:{i}":
                    self.send(chat, f"{title}\n\n{lesson}", [("All Lessons", "lessons"), BACK])
                    return
            for i, (question, options, correct, explanation) in enumerate(QUIZ):
                if data == f"quiz:{i}":
                    buttons = [(option, f"answer:{i}:{j}") for j, option in enumerate(options)]
                    self.send(chat, f"Question {i + 1} of {len(QUIZ)}\n\n{question}", [*buttons, BACK])
                    return
                for j in range(len(options)):
                    if data == f"answer:{i}:{j}":
                        result = "Correct." if j == correct else f"Correct answer: {options[correct]}."
                        next_button = ("Next Question", f"quiz:{i + 1}") if i + 1 < len(QUIZ) else ("Restart Quiz", "quiz:0")
                        self.send(chat, f"{result} {explanation}", [next_button, BACK])
                        return
            self.send(chat, WELCOME, MENU)

    def run(self):
        self.api("setMyName", name="David Trade")
        self.api("setMyDescription", description=DESCRIPTION)
        self.api("setMyShortDescription", short_description="Forex lessons, a practice trade journal, and an interactive quiz.")
        self.api("setMyCommands", commands=[
            {"command": command, "description": description}
            for command, description in (
                ("start", "Open David Trade"), ("menu", "Show the main menu"),
                ("help", "Show the available tools"), ("cancel", "Cancel a draft entry"),
            )
        ])
        offset = None
        while True:
            try:
                updates = self.api("getUpdates", offset=offset, timeout=30, allowed_updates=["message", "callback_query"])
                for update in updates:
                    try:
                        if "message" in update:
                            self.message(update["message"])
                        elif "callback_query" in update:
                            self.callback(update["callback_query"])
                    except TelegramError as error:
                        if error.code not in {400, 403}:
                            raise
                        logging.warning("Could not respond to update %s (%s)", update["update_id"], error.code)
                    offset = update["update_id"] + 1
            except TelegramError as error:
                if error.code != 429 and error.code < 500:
                    raise
                logging.warning("%s. Retrying.", error)
                time.sleep(max(3, error.retry_after))


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN in the environment.")
    path = Path(os.environ.get("JOURNAL_DB", "data/journal.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        DavidTrade(token, db).run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except TelegramError as error:
        raise SystemExit(str(error)) from None
