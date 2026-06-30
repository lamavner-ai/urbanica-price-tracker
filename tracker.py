def main():
    print("--- Starting Tracker Script ---")
    products = load_products()
    print(f"Loaded {len(products)} products from JSON.")

    state = load_state()
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    for product in products:
        name = product["name"]
        url = product["url"]
        print(f"Checking price for: {name}...")

        try:
            price = get_price(url)
            print(f"Successfully found price: {price}")
        except Exception as e:
            print(f"❌ Python Error for {name}: {str(e)}")
            print("Trying to send error to Telegram...")
            send_telegram(f"❌ Error for {name}: {str(e)}")
            continue
            
        # ... שאר הקוד שלך ...
def get_price(url):
    # כותרות מלאות כדי להיראות כמו דפדפן אמיתי
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    r = requests.get(url, headers=headers, timeout=20)
    
    # אם השרת חוסם אותנו, נדע מיד
    if r.status_code != 200:
        raise Exception(f"Failed to fetch page. Status code: {r.status_code}")
        
    soup = BeautifulSoup(r.text, "html.parser")

    # אורבניקה משתמשת בתגי meta עבור מנועי חיפוש שמכילים את המחיר המדויק
    price_meta = soup.find("meta", property="product:price:amount") or soup.find("meta", itemprop="price")
    
    if price_meta and price_meta.get("content"):
        price_text = price_meta["content"]
    else:
        # גיבוי לסלקטורים הרגילים במבנה של אורבניקה
        selectors = [
            ".price-wrapper [data-price-amount]",
            ".final-price .price",
            "[data-price-type='finalPrice'] .price"
        ]
        price_text = None
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                price_text = el.get_text()
                break

    if not price_text:
        raise Exception("Price not found - HTML structure may have changed or bot detected")

    # ניקוי למחיר מספרי (תומך גם בנקודה עשרונית אם יש)
    clean_price = "".join([c for c in price_text if c.isdigit() or c == '.'])
    price = int(float(clean_price)) # המרה ל-float ואז ל-int כדי להתמודד עם שברים

    return price
