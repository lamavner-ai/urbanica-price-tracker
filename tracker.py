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
    print(f"-> Opening advanced Playwright browser for: {url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="he-IL",
            viewport={"width": 1920, "height": 1080}
        )
        
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # כניסה לאתר
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        print(f"-> Page base loaded. Title: '{page.title()}'")
        
        # המתנה יזומה קצרה שכל ה-JS ירוץ
        page.wait_for_timeout(6000)
        
        # ניסיון חילוץ טקסט ישירות דרך Playwright באמצעות כמה סלקטורים אפשריים
        price_text = None
        selectors = [
            ".price-wrapper [data-price-amount]",
            "[data-price-type='finalPrice'] .price",
            ".product-info-main .price",
            ".price"
        ]
        
        for sel in selectors:
            try:
                # בודק אם האלמנט קיים ונראה לעין
                el = page.locator(sel).first
                if el.is_visible():
                    price_text = el.inner_text()
                    print(f"-> Playwright found price text with selector '{sel}': '{price_text}'")
                    if price_text and any(c.isdigit() for c in price_text):
                        break
            except Exception as e:
                print(f"-> Selector '{sel}' failed or not found: {str(e)}")
                continue

        # אם עדיין לא מצאנו, נדפיס קצת טקסט מהגוף של האתר בשביל להבין מה הוא רואה
        if not price_text:
            try:
                body_text = page.locator("body").inner_text()
                print("-> Snippet of body text seen by browser:")
                print(body_text[:500]) # מדפיס את 500 התווים הראשונים
            except Exception:
                pass
                
        browser.close()

    if not price_text or len(price_text.strip()) == 0:
        raise Exception("Price element missing or empty on render")

    # ניקוי והמרת המחיר למספר
    clean_price = "".join([c for c in price_text if c.isdigit() or c == '.'])
    if not clean_price:
        raise Exception(f"No digits found in price text: '{price_text}'")
        
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
