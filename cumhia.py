import sqlite3
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, ReplyKeyboardMarkup, BotCommand, BotCommandScopeChat
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, PreCheckoutQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest

# --- CONFIG ---
TOKEN = "8176163809:AAHGSMvLo7Nu46FIuq0nsUPmlw35Fa68xeU"
ADMIN_ID = 6186002683 
BOT_USERNAME = "cumhiabot" 

CH_MUST_JOIN = -1003985940616  
CH_FREE = -1003999643564
CH_PAID_SHORT = -1003868352723
CH_LEAKS_PIC = -1003979963139
CH_LEAKS_VID = -1003673938011
CH_LONG_PREVIEW = -1003998268019
CH_LONG_PAID = -1003980327133
VIP_CHANNEL_ID = -1003837630506

SUPPORT_LINK = "https://t.me/Sparkcea"
CHANNEL_LINK = "https://t.me/cum_hia"

# --- DB HELPERS ---
def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect('cumhia_final.db')
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        used_free_leak INTEGER DEFAULT 0,
        referral_count INTEGER DEFAULT 0,
        unlocked_via_referral INTEGER DEFAULT 0,
        referred_by INTEGER
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS cms (key TEXT PRIMARY KEY, message_id INTEGER DEFAULT 1)''')
    db_query('''CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, date TEXT)''')
    for key in ["free", "short", "long_p", "long_v", "leaks_p", "leaks_v"]:
        db_query("INSERT OR IGNORE INTO cms (key, message_id) VALUES (?, ?)", (key, 1))

# --- NAVIGATION ---
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), True)
    if not user:
        ref_id = int(context.args[0]) if context.args and context.args[0].isdigit() else None
        db_query("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (uid, ref_id))
        if ref_id and ref_id != uid:
            # Credit the referrer +1
            db_query("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (ref_id,))
            try:
                await context.bot.send_message(ref_id, "🎉 *Someone joined via your link!* Your referral count went up.", parse_mode="Markdown")
            except:
                pass

    kb = [
        ["Daily Free Videos 🥵"],
        ["Her Leaks 🍑", "Long Video 💦"],
        ["Refer & Earn 🎁", "Join VIP Channel 💎"],
        ["Help / Support ℹ️"]
    ]
    await update.message.reply_text(
        "🔞 *WELCOME TO THE CUM HIA VAULT*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

# --- ADMIN TOOLS ---
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = " ".join(context.args)
    if not msg:
        return
    users = db_query("SELECT user_id FROM users", (), True)
    for u in users:
        try:
            await context.bot.send_message(u[0], f"📢 *HOT UPDATE*\n\n{msg}", parse_mode="Markdown")
        except:
            continue
    await update.message.reply_text("✅ Broadcast sent.")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    u_count = db_query("SELECT COUNT(*) FROM users", (), True)[0][0]
    p_sum = db_query("SELECT SUM(amount) FROM payments", (), True)[0][0] or 0
    await update.message.reply_text(f"📊 Stats: {u_count} users, {p_sum} stars.")

# --- MAIN HANDLER ---
async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    # Admin CMS mode: forward a message to set content IDs
    if uid == ADMIN_ID and 'mode' in context.user_data:
        origin = update.message.forward_origin
        if origin and hasattr(origin, 'message_id'):
            db_query("UPDATE cms SET message_id = ? WHERE key = ?", (origin.message_id, context.user_data['mode']))
            await update.message.reply_text(f"✅ ID Saved for [{context.user_data['mode']}]: {origin.message_id}")
            del context.user_data['mode']
            return

    # Ensure user exists
    user_row = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), True)
    if not user_row:
        db_query("INSERT INTO users (user_id) VALUES (?)", (uid,))
        user_row = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), True)
    user = user_row[0]
    # user columns: user_id, used_free_leak, referral_count, unlocked_via_referral, referred_by

    # ─────────────────────────────────────────────
    # DAILY FREE VIDEOS
    # ─────────────────────────────────────────────
    if text == "Daily Free Videos 🥵":
        mid = db_query("SELECT message_id FROM cms WHERE key = 'free'", (), True)[0][0]
        try:
            for i in range(2):
                await context.bot.copy_message(uid, CH_FREE, mid + i)
            kb = [[InlineKeyboardButton("Unlock 5 more spicy pack 🔞⭐", callback_data='buy_short')]]
            await context.bot.copy_message(uid, CH_FREE, mid + 2, reply_markup=InlineKeyboardMarkup(kb))
        except:
            await update.message.reply_text("🔥 Sending today's clips...")

    # ─────────────────────────────────────────────
    # HER LEAKS
    # Logic:
    #   - First time: must join CH_MUST_JOIN → gets one free leak video → used_free_leak = 1
    #   - After that: must pay 2 stars every time (no more freebies)
    # ─────────────────────────────────────────────
    elif text == "Her Leaks 🍑":
        used_free = user[1]  # used_free_leak column

        if used_free == 0:
            # Check channel membership in real-time
            is_member = False
            try:
                m = await context.bot.get_chat_member(CH_MUST_JOIN, uid)
                if m.status in ['member', 'administrator', 'creator']:
                    is_member = True
            except:
                pass

            if is_member:
                # They're in the channel — send the free leak and lock the freebie
                mid_v = db_query("SELECT message_id FROM cms WHERE key = 'leaks_v'", (), True)[0][0]
                try:
                    await context.bot.copy_message(uid, CH_LEAKS_VID, mid_v)
                except Exception as e:
                    await update.message.reply_text(f"⚠️ Error sending leak: {e}")
                    return
                db_query("UPDATE users SET used_free_leak = 1 WHERE user_id = ?", (uid,))
                await update.message.reply_text("🎁 *Enjoy your free leak!* Next time you'll need to unlock it.", parse_mode="Markdown")
            else:
                # Not in channel yet — show join prompt
                kb = [
                    [InlineKeyboardButton("Join @cum_hia 🔓", url=CHANNEL_LINK)],
                    [InlineKeyboardButton("I Joined! ✅", callback_data='check_join_leaks')]
                ]
                await update.message.reply_text(
                    "🔞 *Join our free channel to unlock your first leak for free!*\n\nAfter joining, tap ✅ below.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
        else:
            # Already used free leak — show teaser pic + pay button only
            mid_p = db_query("SELECT message_id FROM cms WHERE key = 'leaks_p'", (), True)[0][0]
            kb = [[InlineKeyboardButton("Unlock Full Leak (2 ⭐)", callback_data='inv_leaks')]]
            try:
                await context.bot.copy_message(uid, CH_LEAKS_PIC, mid_p, reply_markup=InlineKeyboardMarkup(kb))
            except:
                await update.message.reply_text(
                    "🔞 *Want the full leak?* Unlock it below.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )

    # ─────────────────────────────────────────────
    # LONG VIDEO
    # Logic:
    #   - Always show preview pic first (copy from CH_LONG_PREVIEW)
    #   - If unlocked_via_referral == 0 AND referral_count >= 1: show "Unlock with 1 Ref" button
    #   - After referral used (unlocked_via_referral = 1): only pay button shown forever
    #   - Pay option: 2 stars, always available
    # ─────────────────────────────────────────────
    elif text == "Long Video 💦":
        referral_count = user[2]       # referral_count
        used_ref_reward = user[3]      # unlocked_via_referral

        mid_p = db_query("SELECT message_id FROM cms WHERE key = 'long_p'", (), True)[0][0]

        # Build buttons
        pay_btn = InlineKeyboardButton("Watch Full (2 ⭐)", callback_data='inv_long')

        if used_ref_reward == 0 and referral_count >= 1:
            # Has a pending referral reward — offer both options
            ref_btn = InlineKeyboardButton("Unlock with 1 Ref 🔓", callback_data='ref_long')
            kb = InlineKeyboardMarkup([[pay_btn, ref_btn]])
        else:
            # No referral reward available (either already used or hasn't referred anyone)
            kb = InlineKeyboardMarkup([[pay_btn]])

        # Step 1: Send the preview pic/video with the buttons attached
        try:
            await context.bot.copy_message(uid, CH_LONG_PREVIEW, mid_p, reply_markup=kb)
        except Exception as e:
            # Fallback if preview copy fails
            await update.message.reply_text(
                "🎬 *The Main Attraction* — unlock the full video below.",
                parse_mode="Markdown",
                reply_markup=kb
            )

    # ─────────────────────────────────────────────
    # REFER & EARN
    # ─────────────────────────────────────────────
    elif text == "Refer & Earn 🎁":
        count = db_query("SELECT referral_count FROM users WHERE user_id = ?", (uid,), True)[0][0]
        used_ref = db_query("SELECT unlocked_via_referral FROM users WHERE user_id = ?", (uid,), True)[0][0]
        status = "✅ Reward available! Tap *Long Video 💦* to claim." if (count >= 1 and used_ref == 0) else ("🔒 Already used your referral reward." if used_ref == 1 else "📊 Refer 1 friend to unlock a premium video for free!")
        await update.message.reply_text(
            f"🎁 *Refer & Earn*\n\n{status}\n\nReferrals: `{count}/1`\n🔗 Your link:\n`https://t.me/{BOT_USERNAME}?start={uid}`",
            parse_mode="Markdown"
        )

    # ─────────────────────────────────────────────
    # VIP CHANNEL
    # ─────────────────────────────────────────────
    elif text == "Join VIP Channel 💎":
        kb = [[InlineKeyboardButton("Elite Access (15 ⭐)", callback_data='pay_vip')]]
        await update.message.reply_text("💎 *THE VIP VAULT:* Unlimited daily access.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif text == "Help / Support ℹ️":
        await update.message.reply_text(f"📩 Support: {SUPPORT_LINK}")


# --- CALLBACKS ---
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    # ── Check join for Her Leaks freebie ──
    if query.data == 'check_join_leaks':
        is_member = False
        try:
            m = await context.bot.get_chat_member(CH_MUST_JOIN, uid)
            if m.status in ['member', 'administrator', 'creator']:
                is_member = True
        except:
            pass

        if is_member:
            mid_v = db_query("SELECT message_id FROM cms WHERE key = 'leaks_v'", (), True)[0][0]
            try:
                await context.bot.copy_message(uid, CH_LEAKS_VID, mid_v)
            except Exception as e:
                await query.message.reply_text(f"⚠️ Error sending leak: {e}")
                return
            db_query("UPDATE users SET used_free_leak = 1 WHERE user_id = ?", (uid,))
            await query.message.reply_text("✅ *Membership confirmed! Your free leak is above.* Future leaks require payment.", parse_mode="Markdown")
        else:
            await query.message.reply_text("❌ You haven't joined @cum_hia yet! Join first then tap the button again.")

    # ── Payment triggers ──
    elif query.data == 'buy_short':
        await query.message.reply_invoice("Spicy 5-Pack", "Unlock 5 premium clips", "s_p", "XTR", [LabeledPrice("Unlock", 1)])

    elif query.data == 'inv_leaks':
        await query.message.reply_invoice("Full Leak", "Uncensored full leak video", "l_p", "XTR", [LabeledPrice("Unlock", 2)])

    elif query.data == 'inv_long':
        await query.message.reply_invoice("Full Movie", "High-def premium feature", "v_p", "XTR", [LabeledPrice("Unlock", 2)])

    elif query.data == 'pay_vip':
        await query.message.reply_invoice("VIP Pass", "30 Days Unlimited Access", "vip", "XTR", [LabeledPrice("Join", 15)])

    # ── Referral unlock for Long Video ──
    elif query.data == 'ref_long':
        user = db_query("SELECT referral_count, unlocked_via_referral FROM users WHERE user_id = ?", (uid,), True)[0]
        referral_count, used_ref = user[0], user[1]

        if used_ref == 1:
            await query.message.reply_text("❌ You've already used your referral reward. Please pay to watch.")
        elif referral_count >= 1:
            db_query("UPDATE users SET unlocked_via_referral = 1 WHERE user_id = ?", (uid,))
            mid = db_query("SELECT message_id FROM cms WHERE key = 'long_v'", (), True)[0][0]
            await query.message.reply_text("✅ *Referral Reward Unlocked!* Enjoy the full video. Future access requires payment.", parse_mode="Markdown")
            try:
                await context.bot.copy_message(uid, CH_LONG_PAID, mid)
            except Exception as e:
                await query.message.reply_text(f"⚠️ Error sending video: {e}")
        else:
            count = referral_count
            await query.message.reply_text(
                f"❌ You need 1 referral to unlock this for free.\n📊 Progress: `{count}/1`\n🔗 Your link: `https://t.me/{BOT_USERNAME}?start={uid}`",
                parse_mode="Markdown"
            )


# --- PAYMENTS ---
async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = update.message.successful_payment
    uid = update.message.chat_id
    db_query(
        "INSERT INTO payments (user_id, amount, date) VALUES (?, ?, ?)",
        (uid, p.total_amount, datetime.now().strftime("%Y-%m-%d"))
    )

    if p.invoice_payload == "s_p":
        mid = db_query("SELECT message_id FROM cms WHERE key = 'short'", (), True)[0][0]
        for i in range(5):
            try:
                await context.bot.copy_message(uid, CH_PAID_SHORT, mid + i)
            except:
                pass

    elif p.invoice_payload == "l_p":
        mid = db_query("SELECT message_id FROM cms WHERE key = 'leaks_v'", (), True)[0][0]
        try:
            await context.bot.copy_message(uid, CH_LEAKS_VID, mid)
        except Exception as e:
            await context.bot.send_message(uid, f"⚠️ Error delivering content: {e}")

    elif p.invoice_payload == "v_p":
        mid = db_query("SELECT message_id FROM cms WHERE key = 'long_v'", (), True)[0][0]
        try:
            await context.bot.copy_message(uid, CH_LONG_PAID, mid)
        except Exception as e:
            await context.bot.send_message(uid, f"⚠️ Error delivering content: {e}")

    elif p.invoice_payload == "vip":
        try:
            link = await context.bot.create_chat_invite_link(VIP_CHANNEL_ID, member_limit=1)
            await update.message.reply_text(f"🔥 *Your VIP Link (1-time use):*\n{link.invite_link}", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error creating VIP link: {e}")


# --- SETUP COMMANDS ---
async def post_init(application):
    await application.bot.set_my_commands([BotCommand("start", "Menu")])
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Menu"),
            BotCommand("stats", "Revenue"),
            BotCommand("broadcast", "Broadcast"),
            BotCommand("set_free", "Set Free Videos"),
            BotCommand("set_short", "Set 5-Pack"),
            BotCommand("set_long_p", "Set Long Preview"),
            BotCommand("set_long_v", "Set Long Video"),
            BotCommand("set_leaks_p", "Set Leak Teaser Pic"),
            BotCommand("set_leaks_v", "Set Leak Video"),
        ],
        scope=BotCommandScopeChat(chat_id=ADMIN_ID)
    )


if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", send_main_menu))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("stats", admin_stats))

    async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        # e.g. /set_long_p → key = "long_p"
        cmd = update.message.text.lstrip('/').replace('set_', '')
        context.user_data['mode'] = cmd
        await update.message.reply_text(f"📥 Forward a message to set content for: *{cmd}*", parse_mode="Markdown")

    for cmd in ["set_free", "set_short", "set_long_p", "set_long_v", "set_leaks_p", "set_leaks_v"]:
        app.add_handler(CommandHandler(cmd, set_mode))

    app.add_handler(MessageHandler(filters.TEXT | filters.FORWARDED, handle_all))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, success))

    app.run_polling()