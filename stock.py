import json
import random
import os
import copy

STOCK_FILE = "stocks.json"
USER_FILE = "users.json"

# 초기 주식 데이터
DEFAULT_STOCKS = {
    "Apple": 150,
    "Tesla": 700,
    "Amazon": 3300,
    "Google": 2800
}

# 초기 사용자 데이터
DEFAULT_USER = {
    "balance": 10000,
    "stocks": {}
}

stock_changes = {}

# JSON 파일 저장/불러오기
def load_data(filename, default_data):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    else:
        return copy.deepcopy(default_data)

def save_data(filename, data):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

# 주식 데이터 초기화
stocks = load_data(STOCK_FILE, DEFAULT_STOCKS)
users = load_data(USER_FILE, {})

def update_stock_prices():
    global stock_changes
    stock_changes = {}

    for name, price in stocks.items():
        percent_change = random.uniform(-20, 20)
        change_amount = round(price * (percent_change / 100), 2)
        new_price = max(1, round(price + change_amount, 2))
        stocks[name] = new_price
        stock_changes[name] = (change_amount, percent_change)

    save_data(STOCK_FILE, stocks)
    return stock_changes

# 사용자 계정 생성 및 조회
def get_user(user_id):
    if user_id not in users:
        users[user_id] = copy.deepcopy(DEFAULT_USER)
        save_data(USER_FILE, users)
    return users[user_id]

# 주식 구매 함수 (평균 구매가 계산 포함)
def buy_stock(user_id, stock_name, amount):
    user = get_user(user_id)

    if stock_name not in stocks:
        return False, "❌ 해당 주식은 존재하지 않습니다."

    stock_price = stocks[stock_name]

    if isinstance(amount, str) and amount.lower() == "all":
        amount = user["balance"] // stock_price
        if amount == 0:
            return False, "💰 잔액이 부족하여 구매할 수 없습니다."

    try:
        amount = int(amount)
    except:
        return False, "❌ 구매 수량은 숫자여야 합니다."

    total_price = stock_price * amount
    if user["balance"] < total_price:
        return False, "💰 잔액이 부족합니다."

    current_quantity, current_avg_price = user["stocks"].get(stock_name, [0, 0])
    new_quantity = current_quantity + amount

    if new_quantity == 0:
        new_avg_price = 0
    else:
        new_avg_price = ((current_quantity * current_avg_price) + (amount * stock_price)) / new_quantity

    user["balance"] = round(user["balance"] - total_price, 2)
    user["stocks"][stock_name] = [new_quantity, new_avg_price]

    save_data(USER_FILE, users)
    return True, user["balance"]

# 주식 판매 함수 ("all" 처리, 타입 체크 포함)
def sell_stock(user_id, stock_name, amount):
    user = get_user(user_id)

    if stock_name not in user["stocks"]:
        return f"❌ {stock_name} 주식을 보유하고 있지 않습니다."

    if isinstance(amount, str) and amount.lower() == "all":
        amount = user["stocks"][stock_name][0]
    else:
        try:
            amount = int(amount)
        except:
            return "❌ 판매 수량은 숫자여야 합니다."

    quantity, avg_price = user["stocks"][stock_name]

    if quantity < amount:
        return f"❌ {stock_name} 주식이 부족합니다. 현재 보유량: {quantity}주"

    total_price = stocks[stock_name] * amount
    user["balance"] = round(user["balance"] + total_price, 2)
    new_quantity = quantity - amount

    if new_quantity == 0:
        del user["stocks"][stock_name]
    else:
        user["stocks"][stock_name] = [new_quantity, avg_price]

    save_data(USER_FILE, users)
    return f"✅ {stock_name} {amount}주를 판매했습니다. 현재 잔액: ${user['balance']:.2f}"

# 🔧 수정된 함수: 사용자가 보유한 특정 주식 수량 조회
def get_user_stock_amount(user_id, stock_name):
    """사용자가 보유한 특정 주식의 수량을 반환"""
    user = get_user(user_id)  # 올바른 함수 호출 (user_id 매개변수 전달)
    user_stocks = user.get("stocks", {})
    stock_data = user_stocks.get(stock_name, [0, 0])  # 기본값: [수량, 평균가격]
    
    # 리스트 형태로 저장되어 있으면 첫 번째 값(수량)을 반환
    if isinstance(stock_data, list):
        return int(stock_data[0]) if len(stock_data) > 0 else 0
    else:
        # 예전 형식으로 저장된 경우 (단순 숫자)
        return int(stock_data) if stock_data else 0

# 🆕 추가된 함수: 모든 사용자 데이터 로드 (랭킹 기능용)
def load_users():
    """모든 사용자 데이터를 반환 (랭킹 기능에서 사용)"""
    return users

# 사용자 주식 보유 정보 조회
def get_portfolio(user_id):
    user = get_user(user_id)

    header = "📌 종목     | 📦 보유량 | 💵 구매가   | 📈 현재가   | 📊 수익률   \n"
    header += "─" * 63 + "\n"

    table_rows = []
    total_investment = 0  # 총 투자금액
    total_current_value = 0  # 현재 총 가치
    
    for stock, (quantity, avg_price) in user["stocks"].items():
        current_price = stocks.get(stock, 0)
        investment_value = quantity * avg_price  # 투자금액
        current_value = quantity * current_price  # 현재 가치
        
        total_investment += investment_value
        total_current_value += current_value
        
        if avg_price > 0:
            profit_percent = ((current_price - avg_price) / avg_price) * 100
            profit_str = f"▲ {profit_percent:.2f}%" if profit_percent >= 0 else f"▼ {abs(profit_percent):.2f}%"
        else:
            profit_str = "N/A"

        row = f"{stock:<11} | {quantity:>7}주 | ${avg_price:>8.2f} | ${current_price:>8.2f} | {profit_str:>8}"
        table_rows.append(row)

    if not table_rows:
        return f"\n💰 현금 잔액: ${user['balance']:.2f}\n📭 보유 주식 없음"

    # 총 수익률 계산
    total_profit_percent = 0
    if total_investment > 0:
        total_profit_percent = ((total_current_value - total_investment) / total_investment) * 100

    total_assets = user['balance'] + total_current_value
    
    portfolio_table = "```\n" + header + "\n".join(table_rows) + "\n" + "─" * 63 + "\n```"
    
    summary = f"""
💰 현금 잔액: ${user['balance']:,.2f}
📈 주식 가치: ${total_current_value:,.2f}
💎 총 자산: ${total_assets:,.2f}
📊 총 수익률: {'▲' if total_profit_percent >= 0 else '▼'} {abs(total_profit_percent):.2f}%"""

    return f"{summary}\n{portfolio_table}"

# 파일 실행 시 주식 가격 갱신
if __name__ == "__main__":
    update_stock_prices()