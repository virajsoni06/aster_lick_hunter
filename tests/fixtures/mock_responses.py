"""
Mock API responses for testing.
Provides realistic mock data for various API endpoints.
"""

from datetime import datetime, timedelta
import random


class MockAPIResponses:
    """Collection of mock API responses."""

    @staticmethod
    def get_account_info():
        """Mock account information response."""
        return {
            "feeTier": 0,
            "canTrade": True,
            "canDeposit": True,
            "canWithdraw": True,
            "updateTime": 0,
            "totalInitialMargin": "2000.00",
            "totalMaintMargin": "1000.00",
            "totalWalletBalance": "10000.00",
            "totalUnrealizedProfit": "100.00",
            "totalMarginBalance": "10100.00",
            "totalPositionInitialMargin": "2000.00",
            "totalOpenOrderInitialMargin": "0.00",
            "totalCrossWalletBalance": "10000.00",
            "totalCrossUnPnl": "100.00",
            "availableBalance": "8000.00",
            "maxWithdrawAmount": "8000.00",
            "assets": [
                {
                    "asset": "USDT",
                    "walletBalance": "10000.00",
                    "unrealizedProfit": "100.00",
                    "marginBalance": "10100.00",
                    "maintMargin": "1000.00",
                    "initialMargin": "2000.00",
                    "positionInitialMargin": "2000.00",
                    "openOrderInitialMargin": "0.00",
                    "maxWithdrawAmount": "8000.00",
                    "crossWalletBalance": "10000.00",
                    "crossUnPnl": "100.00",
                    "availableBalance": "8000.00"
                }
            ],
            "positions": []
        }

    @staticmethod
    def get_position(symbol="BTCUSDT", side="LONG", quantity=0.1, entry_price=50000):
        """Generate mock position data."""
        mark_price = entry_price * random.uniform(0.98, 1.02)
        pnl = (mark_price - entry_price) * quantity if side == "LONG" else (entry_price - mark_price) * quantity

        return {
            "symbol": symbol,
            "initialMargin": str(quantity * entry_price / 10),  # 10x leverage
            "maintMargin": str(quantity * entry_price / 20),
            "unrealizedProfit": str(pnl),
            "positionInitialMargin": str(quantity * entry_price / 10),
            "openOrderInitialMargin": "0",
            "leverage": "10",
            "isolated": True,
            "entryPrice": str(entry_price),
            "maxNotional": "1000000",
            "positionSide": side,
            "positionAmt": str(quantity if side == "LONG" else -quantity),
            "markPrice": str(mark_price),
            "liquidationPrice": str(entry_price * 0.9 if side == "LONG" else entry_price * 1.1),
            "marginType": "isolated",
            "updateTime": int(datetime.now().timestamp() * 1000)
        }

    @staticmethod
    def get_order_response(symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=0.1, price=50000):
        """Generate mock order response."""
        order_id = random.randint(10000000, 99999999)
        return {
            "symbol": symbol,
            "orderId": order_id,
            "clientOrderId": f"test_order_{order_id}",
            "price": str(price),
            "origQty": str(quantity),
            "executedQty": "0",
            "cumQty": "0",
            "cumBase": "0",
            "status": "NEW",
            "timeInForce": "GTC",
            "type": order_type,
            "side": side,
            "stopPrice": "0",
            "icebergQty": "0",
            "time": int(datetime.now().timestamp() * 1000),
            "updateTime": int(datetime.now().timestamp() * 1000),
            "isWorking": True,
            "origType": order_type,
            "positionSide": "LONG" if side == "BUY" else "SHORT",
            "closePosition": False,
            "priceProtect": False,
            "reduceOnly": False
        }

    @staticmethod
    def get_filled_order(order_data):
        """Convert order to filled status."""
        filled_order = order_data.copy()
        filled_order.update({
            "status": "FILLED",
            "executedQty": filled_order["origQty"],
            "cumQty": filled_order["origQty"],
            "avgPrice": filled_order["price"],
            "updateTime": int(datetime.now().timestamp() * 1000)
        })
        return filled_order

    @staticmethod
    def get_kline_data(symbol="BTCUSDT", interval="1m", limit=100):
        """Generate mock kline/candlestick data."""
        klines = []
        base_price = 50000 if symbol == "BTCUSDT" else 3000 if symbol == "ETHUSDT" else 100
        base_time = datetime.now() - timedelta(minutes=limit)

        for i in range(limit):
            timestamp = int((base_time + timedelta(minutes=i)).timestamp() * 1000)
            open_price = base_price * random.uniform(0.995, 1.005)
            close_price = base_price * random.uniform(0.995, 1.005)
            high_price = max(open_price, close_price) * random.uniform(1.0, 1.01)
            low_price = min(open_price, close_price) * random.uniform(0.99, 1.0)
            volume = random.uniform(10, 100)

            klines.append([
                timestamp,                    # Open time
                str(open_price),             # Open
                str(high_price),             # High
                str(low_price),              # Low
                str(close_price),            # Close
                str(volume),                 # Volume
                timestamp + 60000,           # Close time
                str(volume * close_price),   # Quote asset volume
                random.randint(100, 1000),  # Number of trades
                str(volume * 0.5),           # Taker buy base asset volume
                str(volume * 0.5 * close_price),  # Taker buy quote asset volume
                "0"                          # Ignore
            ])

        return klines

    @staticmethod
    def get_trade_history(symbol="BTCUSDT", limit=10):
        """Generate mock trade history."""
        trades = []
        base_time = datetime.now() - timedelta(hours=limit)

        for i in range(limit):
            trade_time = base_time + timedelta(hours=i)
            side = random.choice(["BUY", "SELL"])

            trades.append({
                "id": random.randint(1000000, 9999999),
                "orderId": random.randint(10000000, 99999999),
                "symbol": symbol,
                "price": str(50000 * random.uniform(0.98, 1.02)),
                "qty": str(random.uniform(0.01, 1.0)),
                "commission": str(random.uniform(0.01, 0.1)),
                "commissionAsset": "USDT",
                "time": int(trade_time.timestamp() * 1000),
                "buyer": side == "BUY",
                "maker": random.choice([True, False]),
                "realizedPnl": str(random.uniform(-100, 100)),
                "side": side,
                "positionSide": "LONG" if side == "BUY" else "SHORT"
            })

        return trades

    @staticmethod
    def get_listen_key():
        """Generate mock listen key for user data stream."""
        import hashlib
        import uuid

        random_uuid = str(uuid.uuid4())
        listen_key = hashlib.sha256(random_uuid.encode()).hexdigest()

        return {
            "listenKey": listen_key
        }

    @staticmethod
    def get_server_time():
        """Get mock server time."""
        return {
            "serverTime": int(datetime.now().timestamp() * 1000)
        }

    @staticmethod
    def get_24hr_ticker(symbol="BTCUSDT"):
        """Generate mock 24hr ticker statistics."""
        return {
            "symbol": symbol,
            "priceChange": str(random.uniform(-1000, 1000)),
            "priceChangePercent": str(random.uniform(-5, 5)),
            "weightedAvgPrice": "50000.00",
            "lastPrice": "50100.00",
            "lastQty": "0.100",
            "openPrice": "49500.00",
            "highPrice": "51000.00",
            "lowPrice": "49000.00",
            "volume": "10000.000",
            "quoteVolume": "500000000.00",
            "openTime": int((datetime.now() - timedelta(hours=24)).timestamp() * 1000),
            "closeTime": int(datetime.now().timestamp() * 1000),
            "firstId": 1000000,
            "lastId": 2000000,
            "count": 1000000
        }

    @staticmethod
    def get_funding_rate(symbol="BTCUSDT"):
        """Generate mock funding rate data."""
        return {
            "symbol": symbol,
            "fundingRate": str(random.uniform(-0.001, 0.001)),
            "fundingTime": int((datetime.now() + timedelta(hours=random.choice([0, 8, 16]))).timestamp() * 1000)
        }

    @staticmethod
    def get_open_interest(symbol="BTCUSDT"):
        """Generate mock open interest data."""
        return {
            "symbol": symbol,
            "openInterest": str(random.uniform(10000, 100000)),
            "time": int(datetime.now().timestamp() * 1000)
        }

    @staticmethod
    def get_order_book_ticker(symbol="BTCUSDT"):
        """Generate mock order book ticker."""
        return {
            "symbol": symbol,
            "bidPrice": "50000.00",
            "bidQty": "2.500",
            "askPrice": "50001.00",
            "askQty": "2.500",
            "time": int(datetime.now().timestamp() * 1000)
        }

    @staticmethod
    def generate_websocket_message(message_type="trade"):
        """Generate mock WebSocket messages."""
        if message_type == "trade":
            return {
                "e": "trade",
                "E": int(datetime.now().timestamp() * 1000),
                "s": "BTCUSDT",
                "t": random.randint(1000000, 9999999),
                "p": str(50000 * random.uniform(0.999, 1.001)),
                "q": str(random.uniform(0.001, 1.0)),
                "b": random.randint(100000, 999999),
                "a": random.randint(100000, 999999),
                "T": int(datetime.now().timestamp() * 1000),
                "m": random.choice([True, False])
            }
        elif message_type == "orderUpdate":
            return {
                "e": "ORDER_TRADE_UPDATE",
                "E": int(datetime.now().timestamp() * 1000),
                "T": int(datetime.now().timestamp() * 1000),
                "o": {
                    "s": "BTCUSDT",
                    "c": f"test_order_{random.randint(1000, 9999)}",
                    "S": random.choice(["BUY", "SELL"]),
                    "o": "LIMIT",
                    "f": "GTC",
                    "q": str(random.uniform(0.01, 1.0)),
                    "p": str(50000 * random.uniform(0.98, 1.02)),
                    "ap": "0",
                    "sp": "0",
                    "x": "NEW",
                    "X": "NEW",
                    "i": random.randint(10000000, 99999999),
                    "l": "0",
                    "z": "0",
                    "L": "0",
                    "T": int(datetime.now().timestamp() * 1000),
                    "t": 0,
                    "b": "0",
                    "a": "0",
                    "m": False,
                    "R": False,
                    "wt": "CONTRACT_PRICE",
                    "ot": "LIMIT",
                    "ps": random.choice(["LONG", "SHORT"]),
                    "cp": False,
                    "rp": "0",
                    "pP": False,
                    "si": 0,
                    "ss": 0
                }
            }
        elif message_type == "accountUpdate":
            return {
                "e": "ACCOUNT_UPDATE",
                "E": int(datetime.now().timestamp() * 1000),
                "T": int(datetime.now().timestamp() * 1000),
                "a": {
                    "B": [
                        {
                            "a": "USDT",
                            "wb": "10000.00",
                            "cw": "10000.00",
                            "bc": "0"
                        }
                    ],
                    "P": [
                        {
                            "s": "BTCUSDT",
                            "pa": str(random.uniform(0.01, 1.0)),
                            "ep": str(50000 * random.uniform(0.98, 1.02)),
                            "cr": str(random.uniform(-100, 100)),
                            "up": str(random.uniform(-100, 100)),
                            "mt": "isolated",
                            "iw": "0",
                            "ps": random.choice(["LONG", "SHORT"])
                        }
                    ]
                }
            }
        else:
            return None