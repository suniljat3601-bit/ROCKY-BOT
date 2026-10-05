import os

import sqlite3

from datetime import datetime, timezone

from telegram import Update

from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN", "")

ADMIN_IDS = {

    int(x.strip())

    for x in os.getenv("ADMIN_IDS", "").split(",")

    if x.strip().isdigit()

}

DB_PATH = "rocky.db"

def db():

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    conn.execute("""

        CREATE TABLE IF NOT EXISTS users (

            user_id INTEGER PRIMARY KEY,

            username TEXT,

            name TEXT NOT NULL,

            balance INTEGER DEFAULT 0

        )

    """)

    conn.execute("""

        CREATE TABLE IF NOT EXISTS transactions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER,

            amount INTEGER,

            balance_after INTEGER,

            action TEXT,

            admin_id INTEGER,

            created_at TEXT

        )

    """)

    conn.commit()

    return conn

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user:

        return False

    # ADMIN_IDS वाले users हमेशा admin रहेंगे

    if user.id in ADMIN_IDS:

        return True

    chat = update.effective_chat

    # Group/Supergroup में सभी Telegram admins

    if chat and chat.type in ("group", "supergroup"):

        try:

            member = await context.bot.get_chat_member(

                chat.id,

                user.id

            )

            return member.status in ("administrator", "creator")

        except Exception:

            return False

    return False

def save_user(user):

    conn = db()

    conn.execute("""

        INSERT INTO users(user_id, username, name)

        VALUES (?, ?, ?)

        ON CONFLICT(user_id) DO UPDATE SET

        username=excluded.username,

        name=excluded.name

    """, (

        user.id,

        user.username or "",

        user.full_name

    ))

    conn.commit()

    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    save_user(update.effective_user)

    await update.message.reply_text(

        "🤖 ROCKY Bot is active!\n\n"

        "Use /help to see commands."

    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(

        "🤖 ROCKY BOT\n\n"

        "/balance - Check your balance\n"

        "/balance @username - Check user's balance\n"

        "/add @username 500 - Add coins (Admin)\n"

        "/remove @username 200 - Remove coins (Admin)\n"

        "/update @username 1000 - Set balance (Admin)\n"

        "/list - Show all users (Admin)\n"

        "/history @username - Transaction history\n"

        "/myid - Show your Telegram ID\n"

        "/help - Show commands"

    )

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(

        f"Your Telegram ID: {update.effective_user.id}"

    )

def find_user(value):

    conn = db()

    if value.startswith("@"):

        row = conn.execute(

            "SELECT * FROM users WHERE lower(username)=?",

            (value[1:].lower(),)

        ).fetchone()

    elif value.isdigit():

        row = conn.execute(

            "SELECT * FROM users WHERE user_id=?",

            (int(value),)

        ).fetchone()

    else:

        row = None

    conn.close()

    return row

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    save_user(update.effective_user)

    if context.args:

        row = find_user(context.args[0])

        if not row:

            await update.message.reply_text(

                "❌ User not found."

            )

            return

    else:

        row = find_user(str(update.effective_user.id))

    await update.message.reply_text(

        f"💰 Balance: {row['balance']} coins"

    )

async def change(

    update: Update,

    context: ContextTypes.DEFAULT_TYPE,

    action

):

    if not await is_admin(update, context):

        await update.message.reply_text(

            "⛔ Admin only."

        )

        return

    if len(context.args) != 2:

        await update.message.reply_text(

            f"Usage: /{action} @username amount"

        )

        return

    row = find_user(context.args[0])

    if not row:

        await update.message.reply_text(

            "❌ User not found.\n"

            "Ask the user to use /start first."

        )

        return

    try:

        amount = int(context.args[1])

        if amount <= 0:

            raise ValueError

    except ValueError:

        await update.message.reply_text(

            "❌ Amount must be a positive number."

        )

        return

    old_balance = row["balance"]

    if action == "add":

        new_balance = old_balance + amount

        transaction_amount = amount

    else:

        new_balance = old_balance - amount

        transaction_amount = -amount

    if new_balance < 0:

        await update.message.reply_text(

            "❌ Balance cannot go below 0."

        )

        return

    conn = db()

    conn.execute(

        "UPDATE users SET balance=? WHERE user_id=?",

        (

            new_balance,

            row["user_id"]

        )

    )

    conn.execute("""

        INSERT INTO transactions

        (

            user_id,

            amount,

            balance_after,

            action,

            admin_id,

            created_at

        )

        VALUES (?, ?, ?, ?, ?, ?)

    """, (

        row["user_id"],

        transaction_amount,

        new_balance,

        action,

        update.effective_user.id,

        datetime.now(timezone.utc).isoformat()

    ))

    conn.commit()

    conn.close()

    await update.message.reply_text(

        f"✅ Balance updated!\n\n"

        f"Old: {old_balance}\n"

        f"Change: {transaction_amount:+}\n"

        f"New balance: {new_balance}"

    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await change(update, context, "add")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await change(update, context, "remove")

async def update_balance(

    update: Update,

    context: ContextTypes.DEFAULT_TYPE

):

    if not await is_admin(update, context):

        await update.message.reply_text(

            "⛔ Admin only."

        )

        return

    if len(context.args) != 2:

        await update.message.reply_text(

            "Usage: /update @username amount"

        )

        return

    row = find_user(context.args[0])

    if not row:

        await update.message.reply_text(

            "❌ User not found."

        )

        return

    try:

        new_balance = int(context.args[1])

        if new_balance < 0:

            raise ValueError

    except ValueError:

        await update.message.reply_text(

            "❌ Invalid balance."

        )

        return

    old_balance = row["balance"]

    conn = db()

    conn.execute(

        "UPDATE users SET balance=? WHERE user_id=?",

        (

            new_balance,

            row["user_id"]

        )

    )

    conn.execute("""

        INSERT INTO transactions

        (

            user_id,

            amount,

            balance_after,

            action,

            admin_id,

            created_at

        )

        VALUES (?, ?, ?, 'update', ?, ?)

    """, (

        row["user_id"],

        new_balance - old_balance,

        new_balance,

        update.effective_user.id,

        datetime.now(timezone.utc).isoformat()

    ))

    conn.commit()

    conn.close()

    await update.message.reply_text(

        f"✅ Balance set to {new_balance} coins."

    )

async def list_users(

    update: Update,

    context: ContextTypes.DEFAULT_TYPE

):

    if not await is_admin(update, context):

        await update.message.reply_text(

            "⛔ Admin only."

        )

        return

    conn = db()

    rows = conn.execute(

        """

        SELECT username, name, balance

        FROM users

        ORDER BY balance DESC

        """

    ).fetchall()

    conn.close()

    if not rows:

        await update.message.reply_text(

            "No users yet."

        )

        return

    text = "👥 USER BALANCES\n\n"

    for i, row in enumerate(rows, 1):

        name = (

            f"@{row['username']}"

            if row["username"]

            else row["name"]

        )

        text += (

            f"{i}. {name} — "

            f"{row['balance']} coins\n"

        )

    await update.message.reply_text(text)

async def history(

    update: Update,

    context: ContextTypes.DEFAULT_TYPE

):

    if context.args:

        row = find_user(context.args[0])

        if not row:

            await update.message.reply_text(

                "❌ User not found."

            )

            return

        user_id = row["user_id"]

    else:

        user_id = update.effective_user.id

    conn = db()

    rows = conn.execute("""

        SELECT

            amount,

            balance_after,

            action,

            created_at

        FROM transactions

        WHERE user_id=?

        ORDER BY id DESC

        LIMIT 20

    """, (user_id,)).fetchall()

    conn.close()

    if not rows:

        await update.message.reply_text(

            "📜 No transaction history."

        )

        return

    text = "📜 TRANSACTION HISTORY\n\n"

    for row in rows:

        text += (

            f"{row['action'].upper()}: "

            f"{row['amount']:+}\n"

            f"Balance: {row['balance_after']}\n"

            f"{row['created_at'][:19]}\n\n"

        )

    await update.message.reply_text(text)

def main():

    if not TOKEN:

        raise RuntimeError(

            "BOT_TOKEN is missing."

        )

    db().close()

    app = (

        Application

        .builder()

        .token(TOKEN)

        .build()

    )

    app.add_handler(

        CommandHandler("start", start)

    )

    app.add_handler(

        CommandHandler("help", help_cmd)

    )

    app.add_handler(

        CommandHandler("myid", myid)

    )

    app.add_handler(

        CommandHandler("balance", balance)

    )

    app.add_handler(

        CommandHandler("add", add)

    )

    app.add_handler(

        CommandHandler("remove", remove)

    )

    app.add_handler(

        CommandHandler("update", update_balance)

    )

    app.add_handler(

        CommandHandler("list", list_users)

    )

    app.add_handler(

        CommandHandler("history", history)

    )

    print("ROCKY Bot is running...")

    app.run_polling(

        drop_pending_updates=True

    )

if __name__ == "__main__":

    main()
