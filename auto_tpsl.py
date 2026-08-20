import os
import time
import hmac
import hashlib
import json
import requests
from pathlib import Path
from dotenv import load_dotenv


# ==========================================
# 設定
# ==========================================

# False = テストモード（注文しない）
# True  = 実際にTP/SL注文を出す
AUTO_ORDER = False

# TP / SL
TP_PERCENT = 1.5
SL_PERCENT = 1.0

# 監視間隔（秒）
CHECK_INTERVAL = 2


# ==========================================
# .env
# ==========================================

env_file = Path(__file__).parent / ".env"
load_dotenv(env_file)

API_KEY = os.getenv("BITBANK_API_KEY")
API_SECRET = os.getenv("BITBANK_API_SECRET")

if not API_KEY or not API_SECRET:
    print("APIキーまたはシークレットキーを取得できません")
    exit()


# ==========================================
# bitbank API
# ==========================================

BASE_URL = "https://api.bitbank.cc"


# ==========================================
# 認証付きGET
# ==========================================

def private_get(endpoint, params=None):

    nonce = str(int(time.time() * 1000))

    query = ""

    if params:
        query = "?" + "&".join(
            f"{key}={value}"
            for key, value in params.items()
        )

    message = nonce + endpoint + query

    signature = hmac.new(
        API_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-NONCE": nonce,
        "ACCESS-SIGNATURE": signature
    }

    response = requests.get(
        BASE_URL + endpoint + query,
        headers=headers
    )

    return response.json()


# ==========================================
# 認証付きPOST
# ==========================================

def private_post(endpoint, body):

    nonce = str(int(time.time() * 1000))

    body_json = json.dumps(
        body,
        separators=(",", ":")
    )

    message = nonce + body_json

    signature = hmac.new(
        API_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-NONCE": nonce,
        "ACCESS-SIGNATURE": signature,
        "Content-Type": "application/json"
    }

    response = requests.post(
        BASE_URL + endpoint,
        headers=headers,
        data=body_json
    )

    return response.json()


# ==========================================
# 全信用建玉を取得
# ==========================================

def get_positions():

    data = private_get(
        "/v1/user/margin/positions"
    )

    if data.get("success") != 1:

        print("建玉取得エラー")
        print(data)

        return []

    positions = data["data"]["positions"]

    active_positions = []

    for position in positions:

        amount = float(
            position["open_amount"]
        )

        if amount > 0:

            active_positions.append(position)

    return active_positions


# ==========================================
# TP / SL注文を取得
# ==========================================

def get_tpsl_orders(pair):

    data = private_get(
        "/v1/user/spot/active_orders",
        {
            "pair": pair
        }
    )

    if data.get("success") != 1:

        return []

    orders = data["data"]["orders"]

    return [
        order
        for order in orders
        if order["type"] in [
            "take_profit",
            "stop_loss"
        ]
    ]


# ==========================================
# TP / SL価格計算
# ==========================================

def calculate_prices(position):

    average_price = float(
        position["average_price"]
    )

    side = position["position_side"]

    if side == "long":

        tp_price = average_price * (
            1 + TP_PERCENT / 100
        )

        sl_price = average_price * (
            1 - SL_PERCENT / 100
        )

    elif side == "short":

        tp_price = average_price * (
            1 - TP_PERCENT / 100
        )

        sl_price = average_price * (
            1 + SL_PERCENT / 100
        )

    else:

        return None, None

    return tp_price, sl_price


# ==========================================
# TP / SL存在確認
# ==========================================

def check_tpsl(position):

    pair = position["pair"]
    side = position["position_side"]

    orders = get_tpsl_orders(pair)

    tp_exists = False
    sl_exists = False

    for order in orders:

        if order.get("position_side") != side:
            continue

        if order["type"] == "take_profit":
            tp_exists = True

        elif order["type"] == "stop_loss":
            sl_exists = True

    return tp_exists, sl_exists


# ==========================================
# 建玉情報表示
# ==========================================

def show_position(position, title):

    pair = position["pair"]
    side = position["position_side"]
    amount = position["open_amount"]
    average_price = position["average_price"]

    tp_price, sl_price = calculate_prices(
        position
    )

    print()
    print("================================")
    print(title)
    print("================================")

    print(f"通貨ペア     : {pair}")
    print(f"ポジション   : {side}")
    print(f"建玉数量     : {amount}")
    print(f"平均取得価格 : {average_price}")

    if tp_price is not None:

        print(f"TP価格       : {tp_price:.0f}")
        print(f"SL価格       : {sl_price:.0f}")


# ==========================================
# 建玉処理
# ==========================================

def process_position(position):

    pair = position["pair"]

    show_position(
        position,
        "★★ 新規建玉を検出 ★★"
    )

    tp_price, sl_price = calculate_prices(
        position
    )

    tp_exists, sl_exists = check_tpsl(
        position
    )

    print()
    print(
        f"TP注文 : {'あり' if tp_exists else 'なし'}"
    )

    print(
        f"SL注文 : {'あり' if sl_exists else 'なし'}"
    )

    # ======================================
    # テストモード
    # ======================================

    if not AUTO_ORDER:

        print()
        print("【テストモード】")
        print("実際の注文は出していません")

        if not tp_exists:
            print(
                f"TP発注予定 : {tp_price:.0f}円"
            )

        if not sl_exists:
            print(
                f"SL発注予定 : {sl_price:.0f}円"
            )

        return

    # ======================================
    # 実際の注文
    # ======================================

    if not tp_exists:

        side = position["position_side"]

        close_side = (
            "sell"
            if side == "long"
            else "buy"
        )

        body = {
            "pair": pair,
            "side": close_side,
            "position_side": side,
            "type": "take_profit",
            "trigger_price": str(
                int(tp_price)
            )
        }

        result = private_post(
            "/v1/user/spot/order",
            body
        )

        print()
        print("TP注文結果")
        print(result)

    if not sl_exists:

        side = position["position_side"]

        close_side = (
            "sell"
            if side == "long"
            else "buy"
        )

        body = {
            "pair": pair,
            "side": close_side,
            "position_side": side,
            "type": "stop_loss",
            "trigger_price": str(
                int(sl_price)
            )
        }

        result = private_post(
            "/v1/user/spot/order",
            body
        )

        print()
        print("SL注文結果")
        print(result)


# ==========================================
# 起動
# ==========================================

print()
print("================================")
print("       Auto TP / SL")
print("================================")

print(f"TP       : {TP_PERCENT}%")
print(f"SL       : {SL_PERCENT}%")
print(f"自動発注 : {AUTO_ORDER}")


# ==========================================
# 起動時の既存建玉
# ==========================================

initial_positions = get_positions()

previous_positions = {}

for position in initial_positions:

    key = (
        position["pair"],
        position["position_side"]
    )

    amount = float(
        position["open_amount"]
    )

    previous_positions[key] = amount

    # 既存建玉だけ表示
    show_position(
        position,
        "既存建玉"
    )


# ==========================================
# 監視開始
# ==========================================

print()
print("監視中...")
print("新しい建玉ができた場合のみ表示します")
print("Ctrl + C で終了")


# ==========================================
# メインループ
# ==========================================

while True:

    try:

        current_positions = get_positions()

        current_map = {}

        for position in current_positions:

            key = (
                position["pair"],
                position["position_side"]
            )

            current_amount = float(
                position["open_amount"]
            )

            current_map[key] = current_amount

            previous_amount = previous_positions.get(
                key,
                0
            )

            # ==================================
            # 新規建玉・建玉増加
            # ==================================

            if current_amount > previous_amount:

                process_position(
                    position
                )

        previous_positions = current_map

        time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:

        print()
        print("監視を終了しました")
        break

    except Exception as e:

        print()
        print("エラーが発生しました")
        print(e)

        time.sleep(CHECK_INTERVAL)