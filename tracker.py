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
    # 1. ניסיון פנייה ישירה ל-API הפנימי של אורבניקה (הכי יציב ומהיר)
    try:
        print("-> Attempting to fetch price via internal Magento API...")
        # אורבניקה בנויה על מג'נטו. ננסה לחלץ את ה-URL Key מהכתובת
        url_clean = url.split('?')[0].rstrip('/')
        product_key = url_clean.split('/')[-1].replace('.html', '')
        
        # כתובת ה-API הטיפוסית לקבלת מידע על מוצר במערכות אלו
        api_url = f"https://www.urbanica-wh.com/rest/V1/products-renderinfo?searchCriteria[filterGroups][0][filters][0][field]=url_key&searchCriteria[filterGroups][0][filters][0][value]={product_key}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        
        res = requests.get(api_url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            # ניקוי וסריקה של ה-JSON למציאת שדות מחיר
            if "items" in data and len(data["items"]) > 0:
                price_info = data["items"][0].get("price_info", {})
                final_price = price_info.get("final_price") or price_info.get("regular_price")
                if final_price is not None:
                    print(f"-> Success via API! Found price: {final_price}")
                    return int(float(final_price))
    except Exception as api_err:
        print(f"-> Internal API attempt skipped or failed: {str(api_err)}")

    # 2. גיבוי - במידה וה-API נכשל, ננסה את ה-Playwright המתוחכם
    print(f"-> Falling back to advanced Playwright browser for: {url}")
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
        
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(6000)
        
        price_text = None
        selectors = [
            ".price-wrapper [data-price-amount]",
            "[data-price-type='finalPrice'] .price",
            ".product-info-main .price",
            ".price"
        ]
        
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    price_text = el.inner_text()
                    if price_text and any(c.isdigit() for c in price_text):
                        break
            except Exception:
                continue
                
        browser.close()

    if not price_text:
        raise Exception("Price not found - Cloudflare wall blocking the server")

    clean_price = "".join([c for c in price_text if c.isdigit() or c == '.'])
    return int(float(clean_price))
    
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
