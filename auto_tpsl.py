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

# 実際に注文を出す
AUTO_ORDER = True

# LONG
TP_PERCENT = 1.5
SL_PERCENT = 1.0

# 監視間隔
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
# 全建玉取得
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

    return [
        p
        for p in positions
        if float(p["open_amount"]) > 0
    ]


# ==========================================
# TP / SL注文取得
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
        if order["type"] in (
            "take_profit",
            "stop_loss"
        )
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

        tp = average_price * (
            1 + TP_PERCENT / 100
        )

        sl = average_price * (
            1 - SL_PERCENT / 100
        )

    elif side == "short":

        tp = average_price * (
            1 - TP_PERCENT / 100
        )

        sl = average_price * (
            1 + SL_PERCENT / 100
        )

    else:

        return None, None

    return tp, sl


# ==========================================
# 現在のTP / SLを取得
# ==========================================

def get_position_tpsl(position):

    pair = position["pair"]
    side = position["position_side"]

    orders = get_tpsl_orders(pair)

    tp_orders = []
    sl_orders = []

    for order in orders:

        if order.get("position_side") != side:
            continue

        if order["type"] == "take_profit":
            tp_orders.append(order)

        elif order["type"] == "stop_loss":
            sl_orders.append(order)

    return tp_orders, sl_orders


# ==========================================
# TP / SLキャンセル
# ==========================================

def cancel_order(pair, order_id):

    body = {
        "pair": pair,
        "order_id": int(order_id)
    }

    return private_post(
        "/v1/user/spot/cancel_order",
        body
    )


# ==========================================
# TP注文
# ==========================================

def place_tp(position, tp_price):

    pair = position["pair"]
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
        "trigger_price": str(tp_price)
    }

    return private_post(
        "/v1/user/spot/order",
        body
    )


# ==========================================
# SL注文
# ==========================================

def place_sl(position, sl_price):

    pair = position["pair"]
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
        "trigger_price": str(sl_price)
    }

    return private_post(
        "/v1/user/spot/order",
        body
    )


# ==========================================
# 建玉表示
# ==========================================

def show_position(position, title):

    pair = position["pair"]
    side = position["position_side"]

    amount = position["open_amount"]

    average = float(
        position["average_price"]
    )

    tp, sl = calculate_prices(
        position
    )

    print()
    print("================================")
    print(title)
    print("================================")

    print(f"通貨ペア     : {pair}")
    print(f"ポジション   : {side}")
    print(f"建玉数量     : {amount}")
    print(f"平均取得価格 : {average:.0f}")

    if tp is not None:

        print(f"自動TP価格   : {tp:.3f}")
        print(f"自動SL価格   : {sl:.3f}")


# ==========================================
# 新規建玉
# ==========================================

def handle_new_position(position):

    show_position(
        position,
        "★★ 新規建玉 ★★"
    )

    tp, sl = calculate_prices(
        position
    )

    tp_orders, sl_orders = get_position_tpsl(
        position
    )

    print()
    print(
        f"既存TP : {len(tp_orders)}件"
    )

    print(
        f"既存SL : {len(sl_orders)}件"
    )

    if not AUTO_ORDER:

        print()
        print("【テストモード】")
        print("実際の注文は出していません")
        return

    # 新規建玉なのに既存注文がある場合は触らない
    if tp_orders or sl_orders:

        print()
        print("既存TP/SLがあるため変更しません")
        return

    print()
    print("TP注文を発注します")

    result = place_tp(
        position,
        tp
    )

    print(result)

    print()
    print("SL注文を発注します")

    result = place_sl(
        position,
        sl
    )

    print(result)


# ==========================================
# 追加購入
# ==========================================

def handle_added_position(position):

    show_position(
        position,
        "★★ 追加建玉を検出 ★★"
    )

    tp_orders, sl_orders = get_position_tpsl(
        position
    )

    print()
    print("平均取得価格が変化しました")

    print(
        f"現在のTP : {len(tp_orders)}件"
    )

    print(
        f"現在のSL : {len(sl_orders)}件"
    )

    # ======================================
    # テスト
    # ======================================

    if not AUTO_ORDER:

        print()
        print("【テストモード】")
        print("既存TP/SLをキャンセルして")
        print("新しい平均取得価格から再設定する予定です")

        return

    # ======================================
    # 既存TPをキャンセル
    # ======================================

    for order in tp_orders:

        order_id = order["order_id"]

        print()
        print(
            f"既存TPをキャンセル : {order_id}"
        )

        result = cancel_order(
            position["pair"],
            order_id
        )

        print(result)

    # ======================================
    # 既存SLをキャンセル
    # ======================================

    for order in sl_orders:

        order_id = order["order_id"]

        print()
        print(
            f"既存SLをキャンセル : {order_id}"
        )

        result = cancel_order(
            position["pair"],
            order_id
        )

        print(result)

    # ======================================
    # 新しい平均価格から計算
    # ======================================

    tp, sl = calculate_prices(
        position
    )

    print()
    print("新しいTP/SLを発注します")

    print(f"新TP : {tp:.3f}")
    print(f"新SL : {sl:.3f}")

    # TP
    result = place_tp(
        position,
        tp
    )

    print()
    print("新TP注文結果")
    print(result)

    # SL
    result = place_sl(
        position,
        sl
    )

    print()
    print("新SL注文結果")
    print(result)


# ==========================================
# 起動
# ==========================================

print()
print("================================")
print("       Auto TP / SL")
print("================================")

print(f"TP       : +{TP_PERCENT}%")
print(f"SL       : -{SL_PERCENT}%")
print(f"自動発注 : {AUTO_ORDER}")


# ==========================================
# 起動時の建玉を記録
# ==========================================

initial_positions = get_positions()

previous_positions = {}

for position in initial_positions:

    key = (
        position["pair"],
        position["position_side"]
    )

    previous_positions[key] = {
        "amount": float(
            position["open_amount"]
        ),
        "average": float(
            position["average_price"]
        )
    }

    show_position(
        position,
        "既存建玉"
    )


print()
print("監視中...")
print("新しい建玉・追加購入のみ表示します")
print("Ctrl + C で終了")


# ==========================================
# メインループ
# ==========================================

while True:

    try:

        positions = get_positions()

        current_positions = {}

        for position in positions:

            key = (
                position["pair"],
                position["position_side"]
            )

            amount = float(
                position["open_amount"]
            )

            average = float(
                position["average_price"]
            )

            current_positions[key] = {
                "amount": amount,
                "average": average
            }

            previous = previous_positions.get(
                key
            )

            # ==================================
            # 完全な新規建玉
            # ==================================

            if previous is None:

                handle_new_position(
                    position
                )

            # ==================================
            # 既存建玉の追加
            # ==================================

            else:

                old_amount = previous["amount"]
                old_average = previous["average"]

                amount_increased = (
                    amount > old_amount
                )

                average_changed = (
                    abs(
                        average - old_average
                    ) > 0.00000001
                )

                if (
                    amount_increased
                    and average_changed
                ):

                    handle_added_position(
                        position
                    )

        previous_positions = current_positions

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
