import asyncio
import json
import websockets
from config import config
from db import insert_liquidation, get_db_conn
from utils import log

class LiquidationStreamer:
    def __init__(self, message_handler):
        self.ws_url = config.WS_URL
        self.stream = config.LIQUIDATION_STREAM
        self.message_handler = message_handler
        self.conn = get_db_conn()

    async def subscribe(self, websocket):
        """Send subscription message to include the stream."""
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [self.stream],
            "id": 1
        }
        await websocket.send(json.dumps(subscribe_msg))
        log.info(f"Subscribed to {self.stream}")

    async def listen(self):
        """Connect to websocket and listen for messages."""
        while True:
            try:
                uri = f"{self.ws_url}?streams={self.stream}"
                async with websockets.connect(uri) as websocket:
                    log.info("Connected to websocket")
                    await self.subscribe(websocket)
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            if 'data' in data:  # Wrapped stream
                                payload = data['data']
                            else:
                                payload = data

                            if payload.get('e') == 'forceOrder':
                                await self.process_liquidation(payload)
                        except json.JSONDecodeError as e:
                            log.error(f"Failed to parse message: {e}")
                        except Exception as e:
                            log.error(f"Error processing message: {e}")
            except websockets.exceptions.ConnectionClosedError:
                log.warning("WebSocket connection closed, reconnecting...")
                await asyncio.sleep(5)  # Reconnect delay
            except Exception as e:
                log.error(f"WebSocket error: {e}, reconnecting...")
                await asyncio.sleep(5)

    async def process_liquidation(self, payload):
        """Process a liquidation event and insert into DB."""
        liquidation = payload['o']  # The order object
        symbol = liquidation['s']
        side = liquidation['S']
        qty = float(liquidation['q'])
        price = float(liquidation['p']) if liquidation['p'] != '0' else 0.0  #Avg price or 0
        usdt_value = qty * price  # Calculate USDT value

        insert_liquidation(self.conn, symbol, side, qty, price)
        log.info(f"Liquidation: {symbol} {side} {qty} @ {price} (${usdt_value:.2f} USDT)")

        # Pass to message handler (e.g., for trading decisions)
        if self.message_handler:
            await self.message_handler(symbol, side, qty, price)
