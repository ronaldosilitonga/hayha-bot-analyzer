#!/usr/bin/env python3
"""
MVP Step 2 (Improved) — Telegram Bot + Cleaner Social Extractor
"""

import os
import re
import requests
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "MASUKKAN_TOKEN_BOT_KAMU_DISINI")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_token_data(ca: str):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching DexScreener: {e}")
        return None

def is_noise(text: str) -> bool:
    """Filter teks yang kemungkinan noise / ciphertext / terlalu acak"""
    if len(text) < 40:
        return True
    alpha_ratio = len(re.findall(r"[a-zA-Z]", text)) / max(len(text), 1)
    if alpha_ratio < 0.55:
        return True
    # Deteksi pola base64-like yang panjang
    if re.search(r"[A-Za-z0-9+/]{25,}={0,2}", text) and alpha_ratio < 0.75:
        return True
    return False

def scrape_website(url: str, max_chars: int = 1200) -> str:
    if not url:
        return "Tidak ada website"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "canvas"]):
            tag.decompose()

        texts = []
        for elem in soup.find_all(["h1", "h2", "h3", "p"]):
            text = elem.get_text(separator=" ", strip=True)
            if not is_noise(text):
                texts.append(text)

        if len(" ".join(texts)) < 250:
            for elem in soup.find_all("li"):
                text = elem.get_text(separator=" ", strip=True)
                if not is_noise(text) and len(text) > 50:
                    texts.append(text)

        content = " ".join(texts)
        content = re.sub(r"\s+", " ", content).strip()

        if not content:
            return "Tidak berhasil mengambil teks yang bersih dari website"

        if len(content) > max_chars:
            content = content[:max_chars].rsplit(" ", 1)[0] + "..."

        return content
    except Exception as e:
        logger.warning(f"Gagal scrape website {url}: {e}")
        return f"Gagal mengambil website ({str(e)[:100]})"

def get_twitter_info(twitter_url: str) -> str:
    if not twitter_url:
        return "Tidak ada Twitter"
    return f"{twitter_url}\n(Info bio/tweet belum diambil otomatis di versi ini)"

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
    website_url = websites[0]["url"] if websites else None
    socials = info.get("socials", [])
    twitter_url = next((s["url"] for s in socials if s.get("type") == "twitter"), None)
    telegram_url = next((s["url"] for s in socials if s.get("type") == "telegram"), None)

    website_text = scrape_website(website_url)
    twitter_info = get_twitter_info(twitter_url)

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

*Website:* {website_url or 'Tidak ada'}
*Twitter:* {twitter_url or 'Tidak ada'}
*Telegram:* {telegram_url or 'Tidak ada'}

*Ringkasan Website:*
{website_text}

*Twitter Info:*
{twitter_info}

*Pair Created:* {created}
"""
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Kirim CA token untuk melihat data + ringkasan website.\n\n"
        "Contoh:\n`0x1e786d31934fc64f450ee47e3f61b41516312f4e`",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ca = update.message.text.strip()

    if not ((ca.startswith("0x") and len(ca) >= 40) or len(ca) >= 32):
        await update.message.reply_text("Format CA tidak valid.")
        return

    msg = await update.message.reply_text("Mengambil data dan menganalisis website...")

    data = get_token_data(ca)
    reply = build_reply(data, ca)

    if len(reply) > 4000:
        reply = reply[:4000] + "\n\n...(dipotong)"

    await msg.edit_text(reply, parse_mode="Markdown", disable_web_page_preview=True)

def main():
    if not BOT_TOKEN or BOT_TOKEN == "MASUKKAN_TOKEN_BOT_KAMU_DISINI":
        print("ERROR: BOT_TOKEN belum diisi!")
        return

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot Step 2 (Improved) sedang berjalan...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
