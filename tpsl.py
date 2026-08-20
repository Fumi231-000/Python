import os
import time
import hmac
import hashlib
import requests
from pathlib import Path
from dotenv import load_dotenv


# =========================
# .envを読み込む
# =========================

env_file = Path(__file__).parent / ".env"
load_dotenv(env_file)

API_KEY = os.getenv("BITBANK_API_KEY")
API_SECRET = os.getenv("BITBANK_API_SECRET")

if not API_KEY or not API_SECRET:
    print("APIキーまたはシークレットキーを取得できません")
    exit()


BASE_URL = "https://api.bitbank.cc"


# =========================
# 認証付きGET
# =========================

def private_get(endpoint, params=None):

    nonce = str(int(time.time() * 1000))

    # クエリパラメータを作成
    query = ""

    if params:
        query = "?" + "&".join(
            f"{key}={value}"
            for key, value in params.items()
        )

    # 署名
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


# =========================
# 現在の建玉取得
# =========================

position_data = private_get(
    "/v1/user/margin/positions"
)


# =========================
# 現在の注文取得
# =========================

order_data = private_get(
    "/v1/user/spot/active_orders",
    {
        "pair": "btc_jpy"
    }
)


# =========================
# 建玉表示
# =========================

print()
print("================================")
print("       現在のBTC建玉")
print("================================")

if position_data.get("success") != 1:

    print("建玉取得失敗")
    print(position_data)

else:

    positions = position_data["data"]["positions"]

    active_positions = [
        p for p in positions
        if float(p["open_amount"]) > 0
    ]

    if not active_positions:

        print("現在、BTCの建玉はありません")

    else:

        for p in active_positions:

            print()
            print(f"通貨ペア     : {p['pair']}")
            print(f"ポジション   : {p['position_side']}")
            print(f"建玉数量     : {p['open_amount']}")
            print(f"平均取得価格 : {p['average_price']}")


# =========================
# TP / SL注文表示
# =========================

print()
print("================================")
print("       現在のTP / SL注文")
print("================================")

if order_data.get("success") != 1:

    print("注文取得失敗")
    print(order_data)

else:

    orders = order_data["data"]["orders"]

    # TP / SLだけ抽出
    tpsl_orders = [
        order
        for order in orders
        if order["type"] in ["take_profit", "stop_loss"]
    ]

    if not tpsl_orders:

        print("現在、TP / SL注文はありません")

    else:

        for order in tpsl_orders:

            print()
            print(f"注文ID       : {order['order_id']}")
            print(f"通貨ペア     : {order['pair']}")
            print(f"ポジション   : {order.get('position_side')}")
            print(f"注文種類     : {order['type']}")
            print(f"数量         : {order['start_amount']}")
            print(f"残数量       : {order['remaining_amount']}")
            print(f"トリガー価格 : {order.get('trigger_price')}")
            print(f"状態         : {order['status']}")

print()
print("================================")