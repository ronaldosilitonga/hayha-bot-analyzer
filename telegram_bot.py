#!/usr/bin/env python3
"""
MVP Step 3 (Robust) — Telegram Bot with timeouts & better error handling
"""

import os
import re
import requests
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# ================== KONFIGURASI ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "MASUKKAN_TOKEN_BOT_KAMU_DISINI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
# =================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=25.0)

SCORING_PROMPT = """Kamu adalah degen berpengalaman yang menilai token memecoin dengan narasi tech.
Tugasmu menilai seberapa bagus narasi tech-nya untuk potensi short-term.

Fokus utama: Hook & Clarity + Sellability.
Jangan buru-buru men-penalty chain.
GitHub tidak ada hampir tidak mempengaruhi skor.
Jika website tidak ada sama sekali = red flag.

Data:
{data}

Output format:
**Score:** 0.XX
**Status Data:** Website [ada/tidak] | Twitter [ada/tidak] | GitHub [ada/tidak]
**Alasan singkat:** (2-3 kalimat)
**Kekuatan:**
- ...
**Red flags / kelemahan:**
- ...
**Kesimpulan:** layak dipantau / marginal / skip
"""

def get_token_data(ca: str):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
    try:
        response = requests.get(url, timeout=12)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"DexScreener error: {e}")
        return None

def is_noise(text: str) -> bool:
    if len(text) < 40:
        return True
    alpha_ratio = len(re.findall(r"[a-zA-Z]", text)) / max(len(text), 1)
    return alpha_ratio < 0.55

def scrape_website(url: str, max_chars: int = 1000) -> str:
    if not url:
        return "Tidak ada website"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        texts = []
        for elem in soup.find_all(["h1", "h2", "h3", "p"]):
            text = elem.get_text(separator=" ", strip=True)
            if not is_noise(text):
                texts.append(text)

        content = re.sub(r"\s+", " ", " ".join(texts)).strip()
        if not content:
            return "Tidak berhasil mengambil teks bersih"
        return content[:max_chars] + ("..." if len(content) > max_chars else "")
    except Exception as e:
        logger.warning(f"Scrape failed {url}: {e}")
        return f"Gagal scrape website"

def format_number(num):
    if not num:
        return "N/A"
    try:
        num = float(num)
        if num >= 1_000_000:
            return f"${num/1_000_000:.2f}M"
        elif num >= 1_000:
            return f"${num/1_000:.1f}K"
        return f"${num:.0f}"
    except:
        return "N/A"

def score_narrative(token_info: str) -> str:
    if not client:
        return "LLM tidak aktif (API key kosong)."
    try:
        prompt = SCORING_PROMPT.format(data=token_info)
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
            timeout=20
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return f"Scoring gagal / timeout: {str(e)[:120]}"

def build_reply(data, ca):
    if not data or not data.get("pairs"):
        return f"❌ Tidak ada data untuk CA:\n`{ca}`"

    pair = data["pairs"][0]
    base = pair.get("baseToken", {})
    info = pair.get("info", {})

    website_url = info.get("websites", [{}])[0].get("url") if info.get("websites") else None
    twitter_url = next((s["url"] for s in info.get("socials", []) if s.get("type") == "twitter"), None)

    website_text = scrape_website(website_url)

    fdv = format_number(pair.get("fdv"))
    mcap = format_number(pair.get("marketCap"))
    liq = format_number(pair.get("liquidity", {}).get("usd"))
    vol = format_number(pair.get("volume", {}).get("h24"))

    llm_input = f"""Token: {base.get('symbol')} ({base.get('name')})
CA: {ca}
FDV: {fdv} | MCap: {mcap} | Liq: {liq}
Website: {website_url or 'Tidak ada'}
Twitter: {twitter_url or 'Tidak ada'}
Ringkasan: {website_text}
"""

    score_result = score_narrative(llm_input)

    text = f"""*{base.get('symbol', 'N/A')}* — {base.get('name', 'N/A')}

*CA:* `{ca}`
*Chain:* {pair.get('chainId', 'N/A')}

*FDV:* {fdv}
*Market Cap:* {mcap}
*Liquidity:* {liq}
*Volume 24h:* {vol}

*Website:* {website_url or 'Tidak ada'}
*Twitter:* {twitter_url or 'Tidak ada'}

*Ringkasan Website:*
{website_text[:600]}

---
*Narrative Score:*
{score_result}
"""
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Kirim CA untuk analisis + scoring narasi.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ca = update.message.text.strip()
    if not ((ca.startswith("0x") and len(ca) >= 40) or len(ca) >= 32):
        await update.message.reply_text("Format CA tidak valid.")
        return

    msg = await update.message.reply_text("Mengambil data...")

    try:
        data = get_token_data(ca)
        reply = build_reply(data, ca)
        if len(reply) > 4000:
            reply = reply[:4000] + "\n...(dipotong)"
        await msg.edit_text(reply, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.exception("Handle message error")
        await msg.edit_text(f"Terjadi error saat memproses CA:\n`{ca}`\n\n{str(e)[:200]}")

def main():
    if not BOT_TOKEN or "MASUKKAN" in BOT_TOKEN:
        print("ERROR: BOT_TOKEN belum diisi")
        return

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot Robust version running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
