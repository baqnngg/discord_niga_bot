# stock.py
import json
import random
import os
import copy
from datetime import datetime

# --- 파일 및 기본 데이터 설정 ---
STOCK_FILE = "stocks.json"
USER_FILE = "users.json"

DEFAULT_STOCKS = {"Apple": 150, "Tesla": 700, "Amazon": 3300, "Google": 2800}
DEFAULT_USER = {"balance": 10000, "stocks": {}, "last_claim_date": None}
stock_changes = {}

# --- 데이터 로드 및 저장 함수 ---
def load_data(filename, default_data):
    """지정된 파일에서 JSON 데이터를 로드합니다. 파일이 없으면 기본 데이터를 반환합니다."""
    try:
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            with open(filename, "r", encoding="utf-8") as file:
                return json.load(file)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading {filename}: {e}")
    return copy.deepcopy(default_data)

def save_data(filename, data):
    """주어진 데이터를 JSON 파일에 저장합니다."""
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving {filename}: {e}")

# --- 데이터 초기화 ---
stocks = load_data(STOCK_FILE, DEFAULT_STOCKS)
users = load_data(USER_FILE, {})

def save_users():
    """사용자 데이터 전체를 파일에 저장합니다."""
    save_data(USER_FILE, users)

# --- 주식 관련 함수 ---
def update_stock_prices():
    """모든 주식의 가격을 랜덤하게 변동시킵니다."""
    global stock_changes
    stock_changes = {}
    for name, price in stocks.items():
        percent_change = random.uniform(-5, 5) 
        change_amount = round(price * (percent_change / 100), 2)
        new_price = max(1, round(price + change_amount, 2))
        stocks[name] = new_price
        stock_changes[name] = (change_amount, percent_change)
    save_data(STOCK_FILE, stocks)
    return stock_changes

# --- 유저 관련 함수 ---
def get_user(user_id):
    """특정 사용자의 데이터를 가져옵니다. 신규 사용자일 경우 기본값을 생성합니다."""
    if user_id not in users:
        users[user_id] = copy.deepcopy(DEFAULT_USER)
    return users[user_id]

def load_users():
    """모든 사용자 데이터를 반환합니다."""
    return users

def claim_daily(user_id, amount):
    """사용자의 일일 출석 보상을 처리합니다."""
    user = get_user(user_id)
    today_str = datetime.utcnow().date().strftime("%Y-%m-%d")
    
    if user.get("last_claim_date") == today_str:
        return False, {"message": "오늘은 이미 출석했습니다."}
    
    user["balance"] = user.get("balance", 0) + amount
    user["last_claim_date"] = today_str
    save_users()
    
    return True, {"new_balance": user["balance"]}

def buy_stock(user_id, stock_name, amount):
    """사용자가 주식을 구매하는 로직을 처리합니다."""
    user = get_user(user_id)
    if stock_name not in stocks:
        return False, "❌ 해당 주식은 존재하지 않습니다."
    
    stock_price = stocks[stock_name]
    
    if isinstance(amount, str) and amount.lower() == "all":
        if stock_price <= 0: return False, "❌ 해당 주식의 가격이 0이라 구매할 수 없습니다."
        amount = int(user["balance"] // stock_price)
        if amount == 0:
            return False, "💰 잔액이 부족하여 1주도 구매할 수 없습니다."
    
    total_cost = stock_price * amount
    if user["balance"] < total_cost:
        return False, "💰 잔액이 부족합니다."

    current_quantity, current_avg_price = user["stocks"].get(stock_name, [0, 0])
    new_quantity = current_quantity + amount

    if new_quantity > 0:
        new_avg_price = ((current_quantity * current_avg_price) + (amount * stock_price)) / new_quantity
    else: new_avg_price = 0
        
    user["balance"] = round(user["balance"] - total_cost, 2)
    user["stocks"][stock_name] = [new_quantity, round(new_avg_price, 2)]
    save_users()
    return True, {"amount": amount, "total_cost": total_cost, "new_balance": user["balance"]}

def sell_stock(user_id, stock_name, amount_to_sell):
    """사용자가 주식을 판매하는 로직을 처리합니다."""
    user = get_user(user_id)
    if stock_name not in user.get("stocks", {}):
        return False, f"❌ **{stock_name}** 주식을 보유하고 있지 않습니다."

    current_quantity, avg_price = user["stocks"][stock_name]
    
    if isinstance(amount_to_sell, str) and amount_to_sell.lower() == "all":
        amount_to_sell = current_quantity

    if current_quantity < amount_to_sell:
        return False, f"❌ **{stock_name}** 주식이 부족합니다. (보유량: {current_quantity}주)"

    total_revenue = stocks[stock_name] * amount_to_sell
    user["balance"] = round(user["balance"] + total_revenue, 2)
    new_quantity = current_quantity - amount_to_sell

    if new_quantity == 0:
        del user["stocks"][stock_name]
    else:
        user["stocks"][stock_name] = [new_quantity, avg_price]
    save_users()
    return True, {"amount": amount_to_sell, "total_revenue": total_revenue, "new_balance": user["balance"]}

def get_portfolio(user_id):
    """사용자의 자산 포트폴리오를 텍스트로 생성하여 반환합니다."""
    user = get_user(user_id)
    header = "📌 종목     | 📦 보유량 | 💵 구매가   | 📈 현재가   | 📊 수익률   \n" + "─" * 63
    table_rows, total_investment, total_current_value = [], 0, 0

    for stock, (quantity, avg_price) in user.get("stocks", {}).items():
        current_price = stocks.get(stock, 0)
        investment = quantity * avg_price
        current_value = quantity * current_price
        total_investment += investment
        total_current_value += current_value
        
        profit_percent = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0
        profit_str = f"▲ {profit_percent:+.2f}%" if profit_percent >= 0 else f"▼ {profit_percent:+.2f}%"
        table_rows.append(f"{stock:<11} | {quantity:>7}주 | ${avg_price:>8.2f} | ${current_price:>8.2f} | {profit_str:>9}")

    if not table_rows:
        return f"\n💰 현금 잔액: `${user['balance']:,.2f}`\n📭 보유 주식이 없습니다."

    total_profit_percent = ((total_current_value - total_investment) / total_investment) * 100 if total_investment > 0 else 0
    total_assets = user['balance'] + total_current_value
    
    summary = (f"💰 **현금 잔액**: `${user['balance']:,.2f}`\n"
               f"📈 **주식 가치**: `${total_current_value:,.2f}`\n"
               f"💎 **총 자산**: `${total_assets:,.2f}`\n"
               f"📊 **총 수익률**: `{'▲' if total_profit_percent >= 0 else '▼'} {abs(total_profit_percent):.2f}%`")
    
    return f"{summary}\n\n**보유 목록**\n```\n{header}\n" + "\n".join(table_rows) + "\n" + "─" * 63 + "\n```"

def calculate_total_assets(user_id):
    """지정된 사용자의 총 자산을 계산합니다."""
    user = get_user(user_id)
    balance = user.get("balance", 0)
    
    total_stock_value = 0
    for stock_name, stock_data in user.get("stocks", {}).items():
        quantity = stock_data[0]
        current_price = stocks.get(stock_name, 0)
        total_stock_value += quantity * current_price
        
    return balance + total_stock_value