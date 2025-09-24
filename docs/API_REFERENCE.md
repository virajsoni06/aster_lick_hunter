# 🔌 API Reference Documentation

## Overview

This document provides comprehensive API documentation for both the Dashboard REST API and the Aster DEX Trading API integration.

## Table of Contents

- [Dashboard API](#dashboard-api)
  - [Authentication](#authentication)
  - [Endpoints](#endpoints)
  - [WebSocket/SSE](#websocketsse)
- [Trading API](#trading-api)
  - [REST Endpoints](#rest-endpoints)
  - [WebSocket Streams](#websocket-streams)
- [Data Models](#data-models)
- [Error Codes](#error-codes)
- [Rate Limits](#rate-limits)

---

## Dashboard API

### Base URL
```
http://localhost:5000/api
```

### Authentication

Currently, the dashboard API doesn't require authentication for local access. For production deployment, implement authentication middleware.

### Endpoints

#### GET /api/health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-09-24T10:30:00Z",
  "services": {
    "bot": "running",
    "websocket": "connected",
    "database": "connected"
  }
}
```

---

#### GET /api/positions
Get current trading positions.

**Query Parameters:**
- `symbol` (optional): Filter by symbol
- `side` (optional): Filter by side (LONG/SHORT)

**Response:**
```json
{
  "positions": [
    {
      "symbol": "BTCUSDT",
      "side": "LONG",
      "quantity": 0.001,
      "entryPrice": 65000,
      "markPrice": 65500,
      "unrealizedPnl": 0.50,
      "margin": 6.5,
      "liquidationPrice": 58500,
      "tp_orders": [
        {
          "orderId": "123456",
          "price": 66300,
          "quantity": 0.001,
          "status": "NEW"
        }
      ],
      "sl_orders": [
        {
          "orderId": "123457",
          "price": 64350,
          "quantity": 0.001,
          "status": "NEW"
        }
      ]
    }
  ],
  "totalUnrealizedPnl": 0.50,
  "totalMargin": 6.5
}
```

---

#### POST /api/positions/close
Close a specific position.

**Request Body:**
```json
{
  "symbol": "BTCUSDT",
  "side": "LONG"
}
```

**Response:**
```json
{
  "success": true,
  "orderId": "789012",
  "message": "Position closure initiated"
}
```

---

#### GET /api/account
Get account information.

**Response:**
```json
{
  "totalBalance": 1000.00,
  "availableBalance": 850.00,
  "totalMargin": 150.00,
  "totalUnrealizedPnl": 25.50,
  "totalRealizedPnl": 100.00,
  "marginRatio": 15.0,
  "positions": 3,
  "openOrders": 6
}
```

---

#### GET /api/trades
Get trade history.

**Query Parameters:**
- `limit` (optional): Number of trades (default: 100)
- `offset` (optional): Pagination offset
- `symbol` (optional): Filter by symbol
- `status` (optional): Filter by status
- `start_date` (optional): Start date (ISO format)
- `end_date` (optional): End date (ISO format)

**Response:**
```json
{
  "trades": [
    {
      "orderId": "123456",
      "symbol": "BTCUSDT",
      "side": "BUY",
      "orderType": "MAIN",
      "quantity": 0.001,
      "price": 65000,
      "status": "FILLED",
      "realizedPnl": 10.50,
      "commission": 0.065,
      "timestamp": "2024-09-24T10:00:00Z",
      "trancheId": 0,
      "relatedOrders": {
        "tp": "123457",
        "sl": "123458"
      }
    }
  ],
  "total": 250,
  "limit": 100,
  "offset": 0
}
```

---

#### GET /api/trades/{order_id}
Get detailed trade information.

**Response:**
```json
{
  "orderId": "123456",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "orderType": "MAIN",
  "quantity": 0.001,
  "price": 65000,
  "executedQty": 0.001,
  "avgPrice": 65000,
  "status": "FILLED",
  "realizedPnl": 10.50,
  "unrealizedPnl": 5.25,
  "commission": 0.065,
  "timestamp": "2024-09-24T10:00:00Z",
  "fillTime": "2024-09-24T10:00:05Z",
  "trancheId": 0,
  "relatedOrders": {
    "takeProfit": {
      "orderId": "123457",
      "price": 66300,
      "quantity": 0.001,
      "status": "NEW"
    },
    "stopLoss": {
      "orderId": "123458",
      "price": 64350,
      "quantity": 0.001,
      "status": "NEW"
    }
  },
  "liquidationTrigger": {
    "volume": 150000,
    "threshold": 100000,
    "side": "LONG"
  }
}
```

---

#### GET /api/liquidations
Get recent liquidation events.

**Query Parameters:**
- `limit` (optional): Number of events (default: 50)
- `symbol` (optional): Filter by symbol
- `min_volume` (optional): Minimum volume filter

**Response:**
```json
{
  "liquidations": [
    {
      "id": 1234,
      "symbol": "BTCUSDT",
      "side": "LONG",
      "price": 65000,
      "quantity": 2.5,
      "usdtValue": 162500,
      "timestamp": "2024-09-24T09:55:00Z",
      "tradePlaced": true
    }
  ],
  "total": 150,
  "volumeLast60s": 450000
}
```

---

#### GET /api/stats
Get aggregated statistics.

**Query Parameters:**
- `period` (optional): Time period (1h, 24h, 7d, 30d)

**Response:**
```json
{
  "period": "24h",
  "totalTrades": 45,
  "successfulTrades": 30,
  "winRate": 66.7,
  "totalVolume": 45000,
  "totalPnl": 125.50,
  "averagePnl": 2.79,
  "bestTrade": {
    "symbol": "BTCUSDT",
    "pnl": 50.00,
    "percentage": 5.0
  },
  "worstTrade": {
    "symbol": "ETHUSDT",
    "pnl": -10.00,
    "percentage": -1.0
  },
  "liquidationsCaptured": 120,
  "liquidationsTotal": 500,
  "captureRate": 24.0
}
```

---

#### GET /api/config
Get current configuration.

**Response:**
```json
{
  "globals": {
    "simulate_only": false,
    "volume_window_sec": 60,
    "max_total_exposure_usdt": 1000,
    "use_position_monitor": true
  },
  "symbols": {
    "BTCUSDT": {
      "volume_threshold_long": 100000,
      "volume_threshold_short": 100000,
      "leverage": 10,
      "trade_value_usdt": 100
    }
  }
}
```

---

#### POST /api/config
Update configuration.

**Request Body:**
```json
{
  "globals": {
    "simulate_only": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Configuration updated",
  "requiresRestart": false
}
```

---

#### POST /api/config/symbol
Update symbol configuration.

**Request Body:**
```json
{
  "symbol": "BTCUSDT",
  "config": {
    "leverage": 20,
    "trade_value_usdt": 200
  }
}
```

---

#### POST /api/config/symbol/add
Add new symbol configuration.

**Request Body:**
```json
{
  "symbol": "ETHUSDT",
  "config": {
    "volume_threshold_long": 50000,
    "volume_threshold_short": 50000,
    "leverage": 10,
    "trade_value_usdt": 100
  }
}
```

---

#### POST /api/config/symbol/remove
Remove symbol configuration.

**Request Body:**
```json
{
  "symbol": "ETHUSDT"
}
```

---

#### GET /api/exchange/symbols
Get available trading symbols.

**Response:**
```json
{
  "symbols": [
    {
      "symbol": "BTCUSDT",
      "baseAsset": "BTC",
      "quoteAsset": "USDT",
      "pricePrecision": 2,
      "quantityPrecision": 3,
      "minNotional": 10,
      "filters": {
        "minQty": 0.001,
        "maxQty": 100,
        "stepSize": 0.001
      }
    }
  ]
}
```

---

#### GET /api/stream
Server-Sent Events stream for real-time updates.

**Event Types:**
- `position_update`: Position changes
- `new_trade`: Trade executed
- `new_liquidation`: Liquidation detected
- `account_update`: Account balance changes
- `config_update`: Configuration changes

**Example:**
```javascript
const eventSource = new EventSource('/api/stream');

eventSource.addEventListener('new_trade', (event) => {
  const trade = JSON.parse(event.data);
  console.log('New trade:', trade);
});

eventSource.addEventListener('position_update', (event) => {
  const position = JSON.parse(event.data);
  console.log('Position updated:', position);
});
```

---

## Trading API

### Base URL
```
https://fapi.asterdex.com
```

### Authentication

All authenticated endpoints require HMAC SHA256 signature.

```python
import hmac
import hashlib
import time

def create_signature(params, secret):
    """Create HMAC SHA256 signature."""
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(
        secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

# Example usage
params = {
    'symbol': 'BTCUSDT',
    'side': 'BUY',
    'quantity': 0.001,
    'timestamp': int(time.time() * 1000)
}
params['signature'] = create_signature(params, API_SECRET)
```

### REST Endpoints

#### GET /fapi/v1/exchangeInfo
Get exchange trading rules and symbol information.

**Response:**
```json
{
  "symbols": [
    {
      "symbol": "BTCUSDT",
      "status": "TRADING",
      "baseAsset": "BTC",
      "quoteAsset": "USDT",
      "pricePrecision": 2,
      "quantityPrecision": 3,
      "filters": [
        {
          "filterType": "PRICE_FILTER",
          "minPrice": "0.01",
          "maxPrice": "1000000"
        }
      ]
    }
  ]
}
```

---

#### GET /fapi/v1/depth
Get order book depth.

**Parameters:**
- `symbol`: Trading symbol
- `limit`: Depth limit (5, 10, 20, 50, 100, 500, 1000)

**Response:**
```json
{
  "lastUpdateId": 1234567,
  "bids": [
    ["65000.00", "1.500"],
    ["64999.00", "2.000"]
  ],
  "asks": [
    ["65001.00", "1.200"],
    ["65002.00", "1.800"]
  ]
}
```

---

#### POST /fapi/v1/order
Place a new order.

**Parameters:**
- `symbol`: Trading symbol
- `side`: BUY or SELL
- `type`: LIMIT, MARKET, STOP, etc.
- `quantity`: Order quantity
- `price`: Order price (for LIMIT orders)
- `timeInForce`: GTC, IOC, FOK
- `positionSide`: LONG, SHORT, or BOTH
- `stopPrice`: Stop price (for STOP orders)

**Response:**
```json
{
  "orderId": 12345678,
  "symbol": "BTCUSDT",
  "status": "NEW",
  "clientOrderId": "x-12345",
  "price": "65000",
  "avgPrice": "0.00000",
  "origQty": "0.001",
  "executedQty": "0",
  "type": "LIMIT",
  "side": "BUY",
  "timeInForce": "GTC"
}
```

---

#### POST /fapi/v1/batchOrders
Place multiple orders.

**Parameters:**
- `batchOrders`: JSON array of order parameters

**Request Body:**
```json
{
  "batchOrders": [
    {
      "symbol": "BTCUSDT",
      "side": "BUY",
      "type": "LIMIT",
      "quantity": "0.001",
      "price": "65000"
    },
    {
      "symbol": "ETHUSDT",
      "side": "SELL",
      "type": "LIMIT",
      "quantity": "0.01",
      "price": "3500"
    }
  ]
}
```

---

#### DELETE /fapi/v1/order
Cancel an order.

**Parameters:**
- `symbol`: Trading symbol
- `orderId`: Order ID to cancel

**Response:**
```json
{
  "orderId": 12345678,
  "symbol": "BTCUSDT",
  "status": "CANCELED",
  "origQty": "0.001",
  "executedQty": "0",
  "price": "65000"
}
```

---

#### GET /fapi/v2/positionRisk
Get current position information.

**Response:**
```json
[
  {
    "symbol": "BTCUSDT",
    "positionAmt": "0.001",
    "entryPrice": "65000",
    "markPrice": "65100",
    "unRealizedProfit": "0.10",
    "liquidationPrice": "58500",
    "leverage": "10",
    "marginType": "cross",
    "positionSide": "LONG"
  }
]
```

---

### WebSocket Streams

#### Liquidation Stream
```
wss://fstream.asterdex.com/stream?streams=!forceOrder@arr
```

**Message Format:**
```json
{
  "e": "forceOrder",
  "E": 1234567890123,
  "o": {
    "s": "BTCUSDT",
    "S": "SELL",
    "o": "LIMIT",
    "f": "IOC",
    "q": "0.001",
    "p": "65000",
    "ap": "65000",
    "X": "FILLED",
    "l": "0.001",
    "z": "0.001",
    "T": 1234567890123
  }
}
```

#### User Data Stream
```
wss://fstream.asterdex.com/ws/<listenKey>
```

**Event Types:**
- `ORDER_TRADE_UPDATE`: Order updates
- `ACCOUNT_UPDATE`: Account balance updates
- `listenKeyExpired`: Listen key expired

---

## Data Models

### Position Model
```typescript
interface Position {
  id: number;
  symbol: string;
  side: 'LONG' | 'SHORT';
  quantity: number;
  entryPrice: number;
  markPrice: number;
  liquidationPrice: number;
  unrealizedPnl: number;
  realizedPnl: number;
  margin: number;
  leverage: number;
  trancheId: number;
  tpOrders: Order[];
  slOrders: Order[];
  createdAt: string;
  updatedAt: string;
}
```

### Order Model
```typescript
interface Order {
  orderId: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  type: 'LIMIT' | 'MARKET' | 'STOP' | 'TAKE_PROFIT';
  orderType: 'MAIN' | 'TP' | 'SL';
  quantity: number;
  price: number;
  executedQty: number;
  avgPrice: number;
  status: 'NEW' | 'FILLED' | 'CANCELED' | 'EXPIRED';
  timeInForce: 'GTC' | 'IOC' | 'FOK';
  positionSide: 'LONG' | 'SHORT' | 'BOTH';
  parentOrderId?: string;
  trancheId: number;
  timestamp: string;
}
```

### Liquidation Model
```typescript
interface Liquidation {
  id: number;
  symbol: string;
  side: 'LONG' | 'SHORT';
  price: number;
  quantity: number;
  usdtValue: number;
  timestamp: string;
  tradePlaced: boolean;
  tradeOrderId?: string;
}
```

---

## Error Codes

### Dashboard API Errors

| Code | Description | Solution |
|------|-------------|----------|
| 400 | Bad Request | Check request parameters |
| 401 | Unauthorized | Check authentication |
| 404 | Not Found | Verify endpoint URL |
| 429 | Rate Limited | Reduce request frequency |
| 500 | Internal Error | Check logs, retry |

### Trading API Errors

| Code | Description | Solution |
|------|-------------|----------|
| -1000 | Unknown error | Contact support |
| -1021 | Invalid timestamp | Sync system time |
| -1022 | Invalid signature | Check API keys |
| -1100 | Invalid parameter | Verify parameters |
| -1121 | Invalid symbol | Check symbol exists |
| -2010 | Insufficient balance | Add funds |
| -2011 | Order rejected | Check order parameters |
| -4000 | Invalid order status | Order already filled/canceled |
| -5000 | Order not found | Verify order ID |

---

## Rate Limits

### Dashboard API
- No rate limits for local access
- Recommended: 10 requests/second for production

### Trading API

#### IP Limits
- 1200 requests per minute
- 100 orders per 10 seconds

#### Order Limits
- 200 open orders per symbol
- 10 orders per second per symbol

#### WebSocket Limits
- 5 connections per IP
- 10 subscriptions per connection

### Rate Limit Headers
```
X-RateLimit-Limit: 1200
X-RateLimit-Remaining: 1150
X-RateLimit-Reset: 1234567890
```

### Handling Rate Limits

```python
import time
from functools import wraps

def rate_limit_handler(func):
    """Decorator to handle rate limits."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = int(e.retry_after) if e.retry_after else 2 ** attempt
                time.sleep(wait_time)
    return wrapper

@rate_limit_handler
def place_order(params):
    # Place order logic
    pass
```

---

## Code Examples

### JavaScript (Dashboard)
```javascript
// Fetch positions
async function getPositions() {
  try {
    const response = await fetch('/api/positions');
    const data = await response.json();
    console.log('Positions:', data.positions);
  } catch (error) {
    console.error('Error fetching positions:', error);
  }
}

// Subscribe to real-time updates
const eventSource = new EventSource('/api/stream');
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  updateUI(data);
};
```

### Python (Bot)
```python
import requests
import time
import hmac
import hashlib

class TradingAPI:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = 'https://fapi.asterdex.com'

    def _create_signature(self, params):
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def place_order(self, symbol, side, quantity, price):
        endpoint = '/fapi/v1/order'
        params = {
            'symbol': symbol,
            'side': side,
            'type': 'LIMIT',
            'quantity': quantity,
            'price': price,
            'timeInForce': 'GTC',
            'timestamp': int(time.time() * 1000)
        }
        params['signature'] = self._create_signature(params)

        headers = {'X-API-KEY': self.api_key}
        response = requests.post(
            f"{self.base_url}{endpoint}",
            params=params,
            headers=headers
        )
        return response.json()
```

---

<p align="center">
  <b>Complete API Documentation for Traders and Developers! 🔌</b>
</p>