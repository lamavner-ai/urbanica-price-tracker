import os
import json
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

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
    print(f"-> Opening Playwright browser for: {url}")
    with sync_playwright() as p:
        # הפעלת דפדפן Chromium
        browser = p.chromium.launch(headless=True)
        # התחזות מלאה לדפדפן רגיל כולל שפה ומערכת הפעלה
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="he-IL"
        )
        page = context.new_page()
        
        # כניסה לאתר והמתנה לטעינה מלאה
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # שליפת תוכן ה-HTML
        html_content = page.content()
        browser.close()

    # שימוש בטקסט שחזר כדי לחלץ את המחיר מתגי המטא
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    
    price_meta = soup.find("meta", property="product:price:amount") or soup.find("meta", itemprop="price")
    
    if price_meta and price_meta.get("content"):
        price_text = price_meta["content"]
        print(f"-> Found price in meta tags: {price_text}")
    else:
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
        raise Exception("Price not found - HTML structure changed or bot still detected")

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
    if r.status_code != 200:
        print(f"-> Telegram Response Content: {r.text}")
    r.raise_for_status()

def main():
    print("=== [STEP 1] Starting Tracker Script ===")
    
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
        try:
            send_telegram(msg)
            state[name] = price
        except Exception as tel_err:
            print(f"❌ Failed to send success message to Telegram: {str(tel_err)}")

    print("\n=== [STEP 4] Saving state and finishing ===")
    save_state(state)

if __name__ == "__main__":
    main()
