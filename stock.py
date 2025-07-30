# stock.py
import json
import random
import os
import copy
import sys
from datetime import datetime

# --- 파일 및 기본 데이터 설정 ---
STOCK_FILE = "stocks.json"
USER_FILE = "users.json"
MARKET_EVENT_FILE = "market_event.json"

# --- 현실성 강화를 위한 상수 ---
TRADING_FEE_RATE = 0.002  # 거래 수수료 0.2%

# ⭐ 사용자의 요청에 따라 주식 종목을 8개로 엄선하고 재구성
DEFAULT_STOCKS = {
    "Apple":    {"price": 170.0, "sector": "IT", "volatility": 1.0, "total_shares": 10000, "available_shares": 10000},
    "Google":   {"price": 130.0, "sector": "IT", "volatility": 1.1, "total_shares": 8500, "available_shares": 8500},
    "NVIDIA":   {"price": 450.0, "sector": "IT", "volatility": 2.2, "total_shares": 5000, "available_shares": 5000},
    "Tesla":    {"price": 250.0, "sector": "자동차", "volatility": 1.8, "total_shares": 7000, "available_shares": 7000},
    "Pfizer":   {"price": 35.0,  "sector": "바이오", "volatility": 0.8, "total_shares": 20000, "available_shares": 20000},
    "JPMorgan": {"price": 150.0, "sector": "금융", "volatility": 0.7, "total_shares": 15000, "available_shares": 15000},
    "Coca-Cola":{"price": 60.0,  "sector": "소비재", "volatility": 0.5, "total_shares": 30000, "available_shares": 30000},
    "Samsung":  {"price": 70.0,  "sector": "IT", "volatility": 1.2, "total_shares": 25000, "available_shares": 25000}
}
DEFAULT_USER = {"balance": 50000.0, "stocks": {}, "last_claim_date": None} 
stock_changes = {}

# --- 데이터 로드 및 저장 함수 ---
def load_data(filename, default_data):
    try:
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            with open(filename, "r", encoding="utf-8") as file:
                return json.load(file)
    except (json.JSONDecodeError, IOError) as e:
        print(f"데이터 로드 오류 {filename}: {e}", file=sys.stderr)
    save_data(filename, default_data)
    return copy.deepcopy(default_data)

def save_data(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"데이터 저장 오류 {filename}: {e}", file=sys.stderr)

# --- 데이터 초기화 ---
stocks = load_data(STOCK_FILE, DEFAULT_STOCKS)
users = load_data(USER_FILE, {})

def save_users():
    save_data(USER_FILE, users)

# --- 현실적인 주가 변동 시스템 ---
def update_stock_prices():
    global stock_changes
    stock_changes = {}
    
    market_events = {}
    if random.random() < 0.2:
        sectors = list(set(s['sector'] for s in stocks.values()))
        event_sector = random.choice(sectors)
        event_multiplier = random.uniform(0.85, 1.15)
        market_events = {"sector": event_sector, "multiplier": event_multiplier}
        save_data(MARKET_EVENT_FILE, market_events)
    else:
        market_events = load_data(MARKET_EVENT_FILE, {})

    for name, data in stocks.items():
        volatility = data.get('volatility', 1.0)
        base_change = random.uniform(-2.0 * volatility, 2.0 * volatility)
        
        demand_pressure = 0
        if data['total_shares'] > 0:
            shares_held = data['total_shares'] - data['available_shares']
            demand_pressure = (shares_held / data['total_shares']) * 5.0

        sector_bonus = 0
        if market_events and data['sector'] == market_events.get('sector'):
            sector_bonus = 10 * (market_events.get('multiplier', 1.0) - 1.0)

        total_percent_change = base_change + demand_pressure + sector_bonus
        change_amount = data['price'] * (total_percent_change / 100)
        new_price = max(1.0, round(data['price'] + change_amount, 2))
        
        stocks[name]['price'] = new_price
        stock_changes[name] = (change_amount, total_percent_change)

    save_data(STOCK_FILE, stocks)
    return stock_changes

# --- 유저 관련 함수 (거래 수수료 및 수량 제한 추가) ---
def get_user(user_id):
    if user_id not in users:
        users[user_id] = copy.deepcopy(DEFAULT_USER)
    return users[user_id]

def load_users():
    return users

def claim_daily(user_id, amount):
    user = get_user(user_id)
    today_str = datetime.utcnow().date().strftime("%Y-%m-%d")
    if user.get("last_claim_date") == today_str:
        return False, {"message": "오늘은 이미 출석했습니다."}
    user["balance"] = user.get("balance", 0) + amount
    user["last_claim_date"] = today_str
    save_users()
    return True, {"new_balance": user["balance"]}

def buy_stock(user_id, stock_name, amount):
    user = get_user(user_id)
    if stock_name not in stocks:
        return False, "❌ 해당 주식은 존재하지 않습니다."
    
    stock_data = stocks[stock_name]
    stock_price = stock_data['price']
    
    if isinstance(amount, str) and amount.lower() == "all":
        if stock_price <= 0: return False, "❌ 해당 주식의 가격이 0이라 구매할 수 없습니다."
        max_buyable = int(user["balance"] / (stock_price * (1 + TRADING_FEE_RATE)))
        amount = min(max_buyable, stock_data['available_shares'])
        if amount == 0: return False, "💰 잔액이 부족하여 1주도 구매할 수 없습니다."
    
    if amount > stock_data['available_shares']:
        return False, f"❌ 시장에 나온 주식 물량이 부족합니다. (현재 유통량: {stock_data['available_shares']}주)"

    total_cost = stock_price * amount
    fee = total_cost * TRADING_FEE_RATE
    final_cost = total_cost + fee

    if user["balance"] < final_cost:
        return False, f"💰 잔액이 부족합니다. (수수료 포함: ${final_cost:,.2f})"

    current_quantity, current_avg_price = user["stocks"].get(stock_name, [0, 0])
    new_quantity = current_quantity + amount
    new_avg_price = ((current_quantity * current_avg_price) + (amount * stock_price)) / new_quantity
        
    user["balance"] = round(user["balance"] - final_cost, 2)
    user["stocks"][stock_name] = [new_quantity, round(new_avg_price, 2)]
    
    stocks[stock_name]['available_shares'] -= amount

    save_users()
    save_data(STOCK_FILE, stocks)
    return True, {"amount": amount, "total_cost": total_cost, "fee": fee, "new_balance": user["balance"]}

def sell_stock(user_id, stock_name, amount_to_sell):
    user = get_user(user_id)
    if stock_name not in user.get("stocks", {}):
        return False, f"❌ **{stock_name}** 주식을 보유하고 있지 않습니다."

    current_quantity, avg_price = user["stocks"][stock_name]
    
    if isinstance(amount_to_sell, str) and amount_to_sell.lower() == "all":
        amount_to_sell = current_quantity

    if current_quantity < amount_to_sell:
        return False, f"❌ **{stock_name}** 주식이 부족합니다. (보유량: {current_quantity}주)"
    
    stock_price = stocks[stock_name]['price']
    total_revenue = stock_price * amount_to_sell
    fee = total_revenue * TRADING_FEE_RATE
    final_revenue = total_revenue - fee
    
    user["balance"] = round(user["balance"] + final_revenue, 2)
    new_quantity = current_quantity - amount_to_sell

    if new_quantity == 0:
        del user["stocks"][stock_name]
    else:
        user["stocks"][stock_name][0] = new_quantity
    
    stocks[stock_name]['available_shares'] += amount_to_sell

    save_users()
    save_data(STOCK_FILE, stocks)
    return True, {"amount": amount_to_sell, "total_revenue": total_revenue, "fee": fee, "new_balance": user["balance"]}

def get_portfolio(user_id):
    user = get_user(user_id)
    header = "📌 종목     | 📦 보유량 | 💵 구매가   | 📈 현재가   | 📊 수익률   \n" + "─" * 63
    table_rows, total_investment, total_current_value = [], 0, 0

    for stock, (quantity, avg_price) in user.get("stocks", {}).items():
        current_price = stocks.get(stock, {}).get('price', 0)
        investment = quantity * avg_price
        current_value = quantity * current_price
        total_investment += investment
        total_current_value += current_value
        profit_percent = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0
        profit_str = f"{'▲' if profit_percent >= 0 else '▼'} {profit_percent:+.2f}%"
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
    user = get_user(user_id)
    balance = user.get("balance", 0)
    total_stock_value = sum(data[0] * stocks.get(name, {}).get('price', 0) for name, data in user.get("stocks", {}).items())
    return balance + total_stock_value

# --- [수정] 도박 시스템: 게임 종류별로 함수 분리 ---
def _validate_bet(user_id, bet_amount_str):
    """베팅 금액 유효성 검사 및 확정 내부 함수"""
    user = get_user(user_id)
    balance = user.get("balance", 0)
    
    if bet_amount_str.lower() == 'all':
        bet_amount = balance
    else:
        try:
            bet_amount = int(bet_amount_str)
        except ValueError:
            return False, {'message': "숫자로 된 베팅 금액을 입력해주세요."}

    if bet_amount <= 0:
        return False, {'message': "베팅 금액은 0보다 커야 합니다."}
    if balance < bet_amount:
        return False, {'message': f"잔액이 부족합니다. (현재 잔액: ${balance:,.2f})"}
        
    return True, {'user': user, 'bet_amount': bet_amount}

def process_slot_machine(user_id, bet_amount_str):
    """슬롯머신 게임 로직"""
    is_valid, result = _validate_bet(user_id, bet_amount_str)
    if not is_valid:
        return False, result

    user, bet_amount = result['user'], result['bet_amount']

    reels_config = [
        ('💎', 20, 2),
        ('💰', 10, 5),
        ('7️⃣', 5, 8),
        ('🍒', 2, 12),
        ('💔', 0, 10)
    ]
    symbols = [item[0] for item in reels_config]
    weights = [item[2] for item in reels_config]
    
    reels_result = random.choices(symbols, weights=weights, k=3)
    winnings = 0
    
    if reels_result[0] == reels_result[1] == reels_result[2]:
        symbol = reels_result[0]
        multiplier = next((item[1] for item in reels_config if item[0] == symbol), 0)
        winnings = bet_amount * multiplier
    elif reels_result.count('🍒') == 2:
        winnings = bet_amount 

    user['balance'] += winnings - bet_amount
    save_users()
    return True, {'reels': reels_result, 'winnings': winnings, 'bet_amount': bet_amount, 'new_balance': user['balance']}

def process_dice_roll(user_id, bet_amount_str):
    """주사위 게임 로직"""
    is_valid, result = _validate_bet(user_id, bet_amount_str)
    if not is_valid:
        return False, result

    user, bet_amount = result['user'], result['bet_amount']
    
    dice1 = random.randint(1, 6)
    dice2 = random.randint(1, 6)
    dice_sum = dice1 + dice2
    winnings = 0
    
    if dice1 == dice2:
        winnings = bet_amount * 4
    elif dice_sum == 7:
        winnings = bet_amount * 2
        
    user['balance'] += winnings - bet_amount
    save_users()
    return True, {'dices': [dice1, dice2], 'winnings': winnings, 'bet_amount': bet_amount, 'new_balance': user['balance']}

def process_coin_flip(user_id, bet_amount_str, choice):
    """동전던지기 게임 로직"""
    is_valid, result = _validate_bet(user_id, bet_amount_str)
    if not is_valid:
        return False, result

    user, bet_amount = result['user'], result['bet_amount']

    if choice not in ['앞', '뒤']:
        return False, {'message': "'앞' 또는 '뒤'를 선택해주세요."}

    coin_result = random.choice(['앞', '뒤'])
    winnings = 0

    if choice == coin_result:
        winnings = bet_amount * 2
    
    user['balance'] += winnings - bet_amount
    save_users()
    return True, {'result': coin_result, 'choice': choice, 'winnings': winnings, 'bet_amount': bet_amount, 'new_balance': user['balance']}