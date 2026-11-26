#!/usr/bin/env python3
"""
MVP Step 1 (Continuous) — Telegram Bot
Kirim CA ke bot, bot balas dengan data dari DexScreener
"""

import os
import requests
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================== KONFIGURASI ==================
# Isi token bot kamu di sini, atau set sebagai environment variable BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN", "MASUKKAN_TOKEN_BOT_KAMU_DISINI")

# =================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_token_data(ca: str):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return None

def format_number(num):
    if num is None:
        return "N/A"
    try:
        num = float(num)
        if num >= 1_000_000:
            return f"${num/1_000_000:.2f}M"
        elif num >= 1_000:
            return f"${num/1_000:.1f}K"
        else:
            return f"${num:.2f}"
    except:
        return str(num)

def build_reply(data, ca):
    if not data or "pairs" not in data or not data["pairs"]:
        return f"❌ Tidak ada data untuk CA:\n`{ca}`\n\nToken mungkin belum terindeks di DexScreener."

    pair = data["pairs"][0]
    base = pair.get("baseToken", {})
    info = pair.get("info", {})

    websites = info.get("websites", [])
    socials = info.get("socials", [])
    twitter = next((s["url"] for s in socials if s.get("type") == "twitter"), None)
    telegram = next((s["url"] for s in socials if s.get("type") == "telegram"), None)

    created = "N/A"
    if pair.get("pairCreatedAt"):
        created = datetime.fromtimestamp(pair["pairCreatedAt"] / 1000).strftime("%Y-%m-%d %H:%M")

    text = f"""*{base.get('symbol', 'N/A')}* — {base.get('name', 'N/A')}

*CA:* `{ca}`
*Chain:* {pair.get('chainId', 'N/A')}

*Price:* ${pair.get('priceUsd', 'N/A')}
*Liquidity:* {format_number(pair.get('liquidity', {}).get('usd'))}
*FDV:* {format_number(pair.get('fdv'))}
*Volume 24h:* {format_number(pair.get('volume', {}).get('h24'))}

*Website:* {websites[0]['url'] if websites else 'Tidak ada'}
*Twitter:* {twitter if twitter else 'Tidak ada'}
*Telegram:* {telegram if telegram else 'Tidak ada'}

*Pair Created:* {created}
*DexScreener:* {pair.get('url', 'N/A')}
"""
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Kirim CA token (contract address) untuk melihat data dari DexScreener.\n\n"
        "Contoh:\n`0xc256e0fb1f93164b8e499746bba593a8e40a7eef`",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ca = update.message.text.strip()
    
    # Validasi sederhana
    if not (ca.startswith("0x") and len(ca) >= 40) and not (len(ca) >= 32):
        await update.message.reply_text("Format CA tidak valid. Kirim contract address yang benar.")
        return

    await update.message.reply_text("Mengambil data...")

    data = get_token_data(ca)
    reply = build_reply(data, ca)
    
    await update.message.reply_text(reply, parse_mode="Markdown", disable_web_page_preview=True)

def main():
    if BOT_TOKEN == "MASUKKAN_TOKEN_BOT_KAMU_DISINI" or not BOT_TOKEN:
        print("ERROR: BOT_TOKEN belum diisi!")
        print("Set environment variable BOT_TOKEN atau edit langsung di script.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot sedang berjalan...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
