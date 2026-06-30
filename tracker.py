import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

PRODUCTS_FILE = "products.json"
STATE_FILE = "last_price.json"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def load_products():
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_price(url):
    # כותרות מלאות כדי לעקוף את החסימה של אורבניקה
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    print(f"-> Sending request to: {url}")
    r = requests.get(url, headers=headers, timeout=20)
    print(f"-> Response status code: {r.status_code}")
    
    if r.status_code != 200:
        raise Exception(f"Failed to fetch page. Status code: {r.status_code}")
        
    soup = BeautifulSoup(r.text, "html.parser")

    # ניסיון חילוץ מתגי meta של אורבניקה
    price_meta = soup.find("meta", property="product:price:amount") or soup.find("meta", itemprop="price")
    
    if price_meta and price_meta.get("content"):
        price_text = price_meta["content"]
        print(f"-> Found price in meta tags: {price_text}")
    else:
        # סלקטורים חלופיים
        selectors = [
            ".price-wrapper [data-price-amount]",
            ".final-price .price",
            "[data-price-type='finalPrice'] .price",
            ".price"
        ]
        price_text = None
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                price_text = el.get_text()
                print(f"-> Found price using selector '{sel}': {price_text}")
                break

    if not price_text:
        raise Exception("Price not found - HTML structure changed or bot detected")

    clean_price = "".join([c for c in price_text if c.isdigit() or c == '.'])
    price = int(float(clean_price))
    return price

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    r = requests.post(url, data=payload)
    print(f"-> Telegram API Response Status: {r.status_code}")
    # אם יש שגיאה מול טלגרם, השורה הזו תגרום לקוד לקרוס ותציג אותה ב-Logs
    r.raise_for_status()

def main():
    print("=== [STEP 1] Starting Tracker Script ===")
    
    # בדיקת משתני סביבה
    if not BOT_TOKEN:
        print("❌ CRITICAL: BOT_TOKEN is missing or empty!")
    if not CHAT_ID:
        print("❌ CRITICAL: CHAT_ID is missing or empty!")
        
    products = load_products()
    print(f"=== [STEP 2] Loaded {len(products)} products from JSON ===")
    
    state = load_state()
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    for product in products:
        name = product["name"]
        url = product["url"]
        print(f"\n=== [STEP 3] Processing product: {name} ===")

        try:
            price = get_price(url)
            print(f"✅ Success! Current price: {price}")
        except Exception as e:
            print(f"❌ Python Error during fetch: {str(e)}")
            print("Attempting to send error notification to Telegram...")
            try:
                send_telegram(f"❌ Error for {name}: {str(e)}")
            except Exception as tel_err:
                print(f"❌ Failed to send to Telegram as well: {str(tel_err)}")
            continue

        old_price = state.get(name)

        if old_price is None:
            msg = f"🆕 First check\n\n{name}\n💰 Price: ₪{price}\n\n🕒 {now}"
        else:
            diff = price - old_price
            if diff == 0:
                status, arrow = "אין שינוי", "➡️"
            elif diff > 0:
                status, arrow = f"עלה ב-₪{diff}", "⬆️"
            else:
                status, arrow = f"ירד ב-₪{abs(diff)}", "⬇️"

            msg = f"🕒 Urbanica Tracker\n\n{name}\n\n💰 ₪{price} {arrow}\n📊 {status}\n\n🕒 {now}"

        print("Sending update to Telegram...")
        send_telegram(msg)
        state[name] = price

    print("\n=== [STEP 4] Saving state and finishing ===")
    save_state(state)

if __name__ == "__main__":
    main()
