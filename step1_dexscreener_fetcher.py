#!/usr/bin/env python3
"""
MVP Step 1: Ambil data token dari DexScreener hanya dengan CA
"""

import requests
import json
import sys
from datetime import datetime

def get_token_data(ca: str):
    """Ambil data token dari DexScreener API"""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error saat mengambil data: {e}")
        return None

def format_number(num):
    """Format angka supaya lebih mudah dibaca"""
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

def print_token_info(data, ca):
    """Cetak informasi token yang penting"""
    if not data or "pairs" not in data or not data["pairs"]:
        print(f"\n❌ Tidak ada data untuk CA: {ca}")
        print("Token mungkin belum terindeks di DexScreener atau CA salah.")
        return
    
    # Ambil pair pertama (biasanya yang paling liquid)
    pair = data["pairs"][0]
    base = pair.get("baseToken", {})
    info = pair.get("info", {})
    
    print("\n" + "="*60)
    print(f"TOKEN INFO — {base.get('symbol', 'N/A')}")
    print("="*60)
    print(f"Nama          : {base.get('name', 'N/A')}")
    print(f"Ticker        : {base.get('symbol', 'N/A')}")
    print(f"CA            : {ca}")
    print(f"Chain         : {pair.get('chainId', 'N/A')}")
    print(f"DEX           : {pair.get('dexId', 'N/A')}")
    print("-"*60)
    print(f"Price USD     : ${pair.get('priceUsd', 'N/A')}")
    print(f"Liquidity     : {format_number(pair.get('liquidity', {}).get('usd'))}")
    print(f"FDV           : {format_number(pair.get('fdv'))}")
    print(f"Market Cap    : {format_number(pair.get('marketCap'))}")
    print(f"Volume 24h    : {format_number(pair.get('volume', {}).get('h24'))}")
    print("-"*60)
    
    # Social links
    websites = info.get("websites", [])
    socials = info.get("socials", [])
    
    print("Website       :", websites[0]["url"] if websites else "Tidak ada")
    
    twitter = next((s["url"] for s in socials if s.get("type") == "twitter"), None)
    print("Twitter       :", twitter if twitter else "Tidak ada")
    
    telegram = next((s["url"] for s in socials if s.get("type") == "telegram"), None)
    print("Telegram      :", telegram if telegram else "Tidak ada")
    
    print("-"*60)
    print(f"DexScreener   : {pair.get('url', 'N/A')}")
    print(f"Pair Created  : {datetime.fromtimestamp(pair.get('pairCreatedAt', 0)/1000).strftime('%Y-%m-%d %H:%M') if pair.get('pairCreatedAt') else 'N/A'}")
    print("="*60)
    
    # Tampilkan jumlah pair yang ditemukan
    print(f"\nDitemukan {len(data['pairs'])} pair untuk token ini.")

def main():
    if len(sys.argv) > 1:
        ca = sys.argv[1].strip()
    else:
        # Default ke salah satu CA yang pernah dibahas (bisa diganti)
        ca = input("Masukkan CA token: ").strip()
    
    if not ca:
        print("CA tidak boleh kosong.")
        return
    
    print(f"\nMengambil data untuk CA: {ca}")
    print("Mohon tunggu...\n")
    
    data = get_token_data(ca)
    if data:
        print_token_info(data, ca)
        
        # Opsional: simpan raw JSON untuk debugging
        # with open(f"raw_{ca[:10]}.json", "w") as f:
        #     json.dump(data, f, indent=2)
        # print("\nRaw data disimpan untuk referensi.")

if __name__ == "__main__":
    main()
