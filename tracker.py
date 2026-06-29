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
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.get(url, headers=headers, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")

    # ניסיון לאתר מחיר (אורבניקה לרוב משתמשים ב-data attribute או class עם price)
    price_text = None

    selectors = [
        "[data-price]",
        ".price",
        ".product-price",
        ".price-value"
    ]

    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            price_text = el.get_text()
            break

    if not price_text:
        raise Exception("Price not found - HTML structure may have changed")

    # ניקוי למחיר מספרי
    price = int("".join([c for c in price_text if c.isdigit()]))

    return price


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=payload)


def main():
    products = load_products()
    state = load_state()

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    for product in products:
        name = product["name"]
        url = product["url"]

        try:
            price = get_price(url)
        except Exception as e:
            send_telegram(f"❌ Error for {name}: {str(e)}")
            continue

        old_price = state.get(name)

        # הודעה תמידית כל שעה
        if old_price is None:
            msg = f"""🆕 First check

{name}
💰 Price: ₪{price}

🕒 {now}"""
        else:
            diff = price - old_price

            if diff == 0:
                status = "אין שינוי"
                arrow = "➡️"
            elif diff > 0:
                status = f"עלה ב-₪{diff}"
                arrow = "⬆️"
            else:
                status = f"ירד ב-₪{abs(diff)}"
                arrow = "⬇️"

            msg = f"""🕒 Urbanica Tracker

{name}

💰 ₪{price} {arrow}
📊 {status}

🕒 {now}"""

        send_telegram(msg)

        state[name] = price

    save_state(state)


if __name__ == "__main__":
    main()
