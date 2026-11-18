# David Trade

A Telegram bot with three main buttons: **Forex Basics** (five short lessons), **Trade Journal** (save and browse practice notes), and **Forex Quiz** (four questions with instant feedback).

## Run the bot

1. Create the bot with [BotFather](https://t.me/BotFather). Try `DavidTradeGuideBot` if available, and set a profile image.
2. Set `BOT_TOKEN` as a secret environment variable on your machine or hosting provider.
3. Start one long-running process with `python bot.py`. Use Python 3.11 or newer. The bot uses the standard library and long polling, so it needs no web server. Use a token with no active webhook.
4. Open the bot in a private Telegram chat. Send `/start` and try all three buttons.

The bot sets its name, profile descriptions, and command list at startup. The journal stores submitted notes, chat IDs, message IDs, and timestamps in SQLite. Set `JOURNAL_DB` to a file on a persistent volume when deploying. The local default is `data/journal.sqlite3`. If the process restarts while a user is composing a draft, they can tap **Add Entry** again. Saved entries remain in the database.

Before submitting a Telegram ad, confirm the profile image and description are visible, test the bot on mobile and desktop, and make sure the ad describes the lessons, practice journal, or quiz available in the bot. See the [Telegram Ads guidelines](https://ads.telegram.org/guidelines).
