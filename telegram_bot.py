#!/usr/bin/env python3
"""
MVP Step 3 (Fixed Markdown) — Telegram Bot
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "MASUKKAN_TOKEN_BOT_KAMU_DISINI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=25.0)

def escape_md(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', str(text))

SCORING_PROMPT = """Kamu adalah degen berpengalaman yang menilai token memecoin dengan narasi tech.
Tugasmu hanya menilai kualitas narasi tech-nya (bukan fundamental jangka panjang).

Fokus utama (yang benar-benar mempengaruhi skor):
1. Hook & Clarity — apakah mudah dipahami dan menarik dalam 1-2 kalimat?
2. Sellability — apakah orang lain mudah “run” / shill narasi ini?
3. Tech Plausibility — apakah klaimnya setidaknya masuk akal untuk degen?

Yang TIDAK boleh menurunkan skor secara signifikan:
- Tidak ada GitHub
- Tidak ada info tim / partner / audit
- Tidak ada tokenomics detail
- FDV / liquidity rendah
- Chain tertentu (termasuk Robinhood Chain)
- Twitter belum terlalu aktif

Jika website ada dan narasinya jelas, itu sudah cukup untuk skor menengah ke atas.
Jika website tidak ada sama sekali → baru jadi red flag besar.

Data yang kamu terima:
{data}

Output format (wajib):
**Score:** 0.XX
**Status Data:** Website [ada/tidak] | Twitter [ada/tidak] | GitHub [ada/tidak]
**Alasan singkat:** (fokus ke hook & sellability)
**Kekuatan:**
- ...
**Red flags / kelemahan:** (hanya yang berkaitan dengan narasi, bukan market/tim)
**Kesimpulan:** layak dipantau / marginal / skip
"""

def get_token_data(ca: str):
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{ca}", timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"DexScreener: {e}")
        return None

def is_noise(text: str) -> bool:
    if len(text) < 40:
        return True
    return len(re.findall(r"[a-zA-Z]", text)) / max(len(text), 1) < 0.55

def scrape_website(url: str, max_chars: int = 800) -> str:
    if not url:
        return "Tidak ada website"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        texts = [el.get_text(" ", strip=True) for el in soup.find_all(["h1","h2","h3","p"]) if not is_noise(el.get_text(" ", strip=True))]
        content = re.sub(r"\s+", " ", " ".join(texts)).strip()
        return (content[:max_chars] + "...") if len(content) > max_chars else (content or "Tidak ada teks bersih")
    except Exception as e:
        logger.warning(f"Scrape error: {e}")
        return "Gagal mengambil website"

def format_number(num):
    if not num:
        return "N/A"
    try:
        n = float(num)
        if n >= 1_000_000: return f"${n/1_000_000:.2f}M"
        if n >= 1_000: return f"${n/1_000:.1f}K"
        return f"${n:.0f}"
    except:
        return "N/A"

def score_narrative(info: str) -> str:
    if not client:
        return "LLM tidak aktif (API key kosong)."
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": SCORING_PROMPT.format(data=info)}],
            temperature=0.4,
            max_tokens=600,
            timeout=25
        )
        result = resp.choices[0].message.content
        if not result or not result.strip():
            return "LLM mengembalikan respons kosong. Coba lagi atau ganti model."
        return result.strip()
    except Exception as e:
        logger.error(f"LLM scoring error: {e}")
        return f"Scoring gagal: {str(e)[:150]}"

def build_reply(data, ca):
    if not data or not data.get("pairs"):
        return f"Tidak ada data untuk CA: {ca}"

    pair = data["pairs"][0]
    base = pair.get("baseToken", {})
    info = pair.get("info", {})

    website_url = (info.get("websites") or [{}])[0].get("url")
    twitter_url = next((s["url"] for s in info.get("socials", []) if s.get("type") == "twitter"), None)

    website_text = scrape_website(website_url)
    fdv = format_number(pair.get("fdv"))
    mcap = format_number(pair.get("marketCap"))
    liq = format_number(pair.get("liquidity", {}).get("usd"))
    vol = format_number(pair.get("volume", {}).get("h24"))

    llm_input = f"""Token: {base.get('symbol')} ({base.get('name')})
CA: {ca}
FDV: {fdv}
Website: {website_url or 'Tidak ada'}
Twitter: {twitter_url or 'Tidak ada'}
Ringkasan Website:
{website_text[:500]}
"""
    score = score_narrative(llm_input)

    # Pakai plain text supaya tidak error Markdown
    text = f"""{base.get('symbol', 'N/A')} — {base.get('name', 'N/A')}

CA: {ca}
Chain: {pair.get('chainId', 'N/A')}

FDV: {fdv}
Market Cap: {mcap}
Liquidity: {liq}
Volume 24h: {vol}

Website: {website_url or 'Tidak ada'}
Twitter: {twitter_url or 'Tidak ada'}

Ringkasan Website:
{website_text[:280]}...

---
Narrative Score:
{score}
"""
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Kirim CA untuk analisis + scoring narasi.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ca = update.message.text.strip()
    if not ((ca.startswith("0x") and len(ca) >= 40) or len(ca) >= 32):
        await update.message.reply_text("Format CA tidak valid.")
        return

    status = await update.message.reply_text("Mengambil data... [v3]")
    try:
        data = get_token_data(ca)
        if not data or not data.get("pairs"):
            await status.edit_text(f"Tidak ada data untuk CA: {ca}")
            return

        pair = data["pairs"][0]
        base = pair.get("baseToken", {})
        info = pair.get("info", {})

        website_url = (info.get("websites") or [{}])[0].get("url")
        twitter_url = next((s["url"] for s in info.get("socials", []) if s.get("type") == "twitter"), None)
        website_text = scrape_website(website_url) or ""

        fdv = format_number(pair.get("fdv"))
        mcap = format_number(pair.get("marketCap"))
        liq = format_number(pair.get("liquidity", {}).get("usd"))
        vol = format_number(pair.get("volume", {}).get("h24"))

        # Pesan 1 — data dasar (pendek)
        short_web = (website_text[:350] + "...") if len(website_text) > 350 else website_text
        msg1 = (
            f"{base.get('symbol', 'N/A')} — {base.get('name', 'N/A')}\n\n"
            f"CA: {ca}\n"
            f"Chain: {pair.get('chainId', 'N/A')}\n\n"
            f"FDV: {fdv}\n"
            f"Market Cap: {mcap}\n"
            f"Liquidity: {liq}\n"
            f"Volume 24h: {vol}\n\n"
            f"Website: {website_url or 'Tidak ada'}\n"
            f"Twitter: {twitter_url or 'Tidak ada'}\n\n"
            f"Ringkasan Website:\n{short_web}"
        )
        await status.edit_text(msg1[:4000])

        # Pesan 2 — score
        llm_input = (
            f"Token: {base.get('symbol')}\n"
            f"Website: {website_url or 'Tidak ada'}\n"
            f"Twitter: {twitter_url or 'Tidak ada'}\n"
            f"Ringkasan: {website_text[:700]}"
        )
        score = score_narrative(llm_input) or "Tidak ada hasil scoring."
        await update.message.reply_text(("Narrative Score:\n\n" + score)[:4000])

    except Exception as e:
        logger.exception("Error")
        await status.edit_text(f"Error: {str(e)[:250]}")

def main():
    if not BOT_TOKEN or "MASUKKAN" in BOT_TOKEN:
        print("BOT_TOKEN belum diisi")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot running (plain text mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
