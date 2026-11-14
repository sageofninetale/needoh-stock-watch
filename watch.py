"""NeeDoh stock watcher.

Checks three Shopify toy shops for NeeDoh products and sends a phone
notification (via ntfy) when a product goes from sold out to in stock.
State is kept in state.json so each product only alerts once per restock.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

SHOPS = [
    {"name": "The Kid Collective", "base": "https://thekidcollective.co.uk",
     "path": "/collections/needoh/products.json", "filter": False},
    {"name": "Bigjigs", "base": "https://www.bigjigstoys.co.uk",
     "path": "/collections/nee-doh/products.json", "filter": False},
    {"name": "My Small World", "base": "https://www.mysmallworld.co.uk",
     "path": "/products.json", "filter": True},
]
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
UA = "Mozilla/5.0 (stock-watch)"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def is_needoh(p):
    text = (p.get("title", "") + " " + p.get("vendor", "")).lower()
    return "needoh" in text.replace(" ", "").replace("-", "")


def shop_products(shop):
    items = {}
    for page in range(1, 60):
        data = fetch(f"{shop['base']}{shop['path']}?limit=250&page={page}")
        products = data.get("products", [])
        if not products:
            break
        for p in products:
            if shop["filter"] and not is_needoh(p):
                continue
            variants = p.get("variants", [])
            in_stock = [v for v in variants if v.get("available")]
            price = (in_stock or variants or [{}])[0].get("price", "")
            items[f"{shop['name']}|{p['id']}"] = {
                "title": p.get("title", ""),
                "available": bool(in_stock),
                "price": price,
                "url": f"{shop['base']}/products/{p.get('handle', '')}",
                "shop": shop["name"],
            }
        time.sleep(0.5)
    return items


def send_email(title, message):
    """Email the alert through an SMTP account (e.g. Gmail with an app password)."""
    import smtplib
    from email.message import EmailMessage
    user, password, to = (os.environ.get(k) for k in ("SMTP_USER", "SMTP_PASS", "ALERT_EMAIL"))
    if not (user and password and to):
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = title, user, to
    msg.set_content(message + "\n\n(Automatic NeeDoh stock alert, checked every 15 minutes.)")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    with smtplib.SMTP(host, 587, timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
    return True


def notify(title, message, click=None):
    sent = False
    try:
        sent = send_email(title, message)
    except Exception as e:
        print(f"Email failed: {e}", file=sys.stderr)
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        headers = {"Title": title, "Tags": "teddy_bear", "Priority": "high"}
        if click:
            headers["Click"] = click
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            urllib.request.urlopen(req, timeout=30).read()
            sent = True
        except Exception as e:
            print(f"Push failed: {e}", file=sys.stderr)
    if not sent:
        print("No alert channel worked, would send:", title, "|", message)


def main():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    previous = state.get("products", {})
    first_run = not previous

    current = {}
    for shop in SHOPS:
        try:
            current.update(shop_products(shop))
        except Exception as e:  # keep last known data for a shop that failed
            print(f"Could not check {shop['name']}: {e}", file=sys.stderr)
            current.update({k: v for k, v in previous.items() if v.get("shop") == shop["name"]})

    restocked = [v for k, v in current.items()
                 if v["available"] and not previous.get(k, {}).get("available")]

    in_stock_now = sum(v["available"] for v in current.values())
    print(f"Checked {len(current)} NeeDoh products, {in_stock_now} in stock, {len(restocked)} newly in stock")

    if first_run:
        notify("NeeDoh alerts are on",
               f"Watching {len(current)} NeeDoh products across 3 shops every 15 minutes. "
               f"{in_stock_now} in stock right now. You'll get a ping with the link when one comes back.")
    elif restocked:
        # one email per check, listing everything that came back, each with its buy link
        lines = [f"{i['title']} - £{i['price']} at {i['shop']}\n{i['url']}" for i in restocked[:15]]
        if len(restocked) > 15:
            lines.append(f"...and {len(restocked) - 15} more.")
        title = (f"NeeDoh back in stock: {restocked[0]['title']}" if len(restocked) == 1
                 else f"{len(restocked)} NeeDoh products back in stock")
        notify(title, "\n\n".join(lines), click=restocked[0]["url"])

    # month stamp keeps the repo active so GitHub never pauses the schedule
    state = {"month": datetime.now(timezone.utc).strftime("%Y-%m"), "products": current}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
