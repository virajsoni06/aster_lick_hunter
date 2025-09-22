# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Aster Liquidation Hunter Bot - A cryptocurrency trading bot that monitors liquidation events on Aster DEX and executes counter-trades based on volume thresholds. Includes a web-based dashboard for monitoring and configuration.

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run bot only
python main.py

# Run both bot and dashboard
python launcher.py

# Run dashboard only
python src/api/api_server.py
```

Dashboard available at: http://localhost:5000

## Configuration

The bot is configured through two main files:
- `.env`: Contains API credentials (API_KEY, API_SECRET)
- `settings.json`: Contains trading parameters:
  - Global settings: volume_window_sec, simulate_only, db_path, multi_assets_mode, hedge_mode, order_ttl_seconds, max_open_orders_per_symbol, max_total_exposure_usdt, rate_limit_buffer_pct, time_in_force
  - Per-symbol settings: volume_threshold, leverage, margin_type, trade_side, trade_value_usdt, price_offset_pct, max_position_usdt, take_profit/stop_loss settings, working_type, price_protect

## Architecture

### Core Components

1. **WebSocket Streaming (`src/core/streamer.py`)**
   - Connects to `wss://fstream.asterdex.com/stream`
   - Subscribes to `!forceOrder@arr` liquidation stream
   - Processes incoming liquidation events and stores them in database
   - Triggers trade evaluation for each liquidation

2. **Trading Logic (`src/core/trader.py`)**
   - Evaluates liquidations against volume thresholds (USDT or token volume)
   - Places counter-trades when thresholds are met with orderbook-based pricing
   - Supports hedge mode with separate LONG/SHORT positions
   - Automatically places Take Profit and Stop Loss orders after entry fills
   - Calculates position sizes from trade_value_usdt * leverage
   - Caches exchange info and symbol specifications for precision handling

3. **Database Layer (`src/database/db.py`)**
   - SQLite database with tables: `liquidations`, `trades`, `order_relationships`, `order_status`, `positions`
   - Tracks all liquidation events with USDT value calculations
   - Records trade attempts with order type and parent order tracking
   - Provides volume aggregation queries for threshold checking
   - Indexed tables for efficient queries

4. **Order Management (`src/core/order_cleanup.py`)**
   - Background service that monitors and cancels stale limit orders
   - Cancels related TP/SL orders when main orders are canceled
   - Configurable cleanup interval and stale order timeout

5. **User Data Stream (`src/core/user_stream.py`)**
   - Monitors real-time position updates via WebSocket
   - Handles order fills and position changes
   - Integrates with order cleanup for automated management

6. **Authentication (`src/utils/auth.py`)**
   - HMAC SHA256 signature-based authentication
   - All API requests go through `make_authenticated_request()`
   - Handles GET, POST, and DELETE requests with proper signing

7. **PNL Tracker (`src/api/pnl_tracker.py`)**
   - Tracks realized and unrealized P&L for positions
   - Calculates trade performance metrics
   - Integrates with dashboard for real-time P&L display

### Data Flow

1. WebSocket receives liquidation event → `streamer.process_liquidation()`
2. Liquidation stored in database → `db.insert_liquidation()`
3. Trade evaluation triggered → `trader.evaluate_trade()`
4. Volume check performed → `db.get_usdt_volume_in_window()` or `db.get_volume_in_window()`
5. If threshold met, calculate position size from trade_value_usdt * leverage
6. Place limit order with orderbook pricing → `trader.place_order()`
7. Monitor for fill, then place TP/SL orders → `trader.place_tp_sl_orders()`
8. Trade and relationships recorded in database

## Key API Endpoints

- Base URL: `https://fapi.asterdex.com`
- WebSocket: `wss://fstream.asterdex.com/stream`
- Exchange Info: `GET /fapi/v1/exchangeInfo`
- Order Book: `GET /fapi/v1/depth`
- Position Mode: `GET/POST /fapi/v1/positionSide/dual`
- Multi-Assets Mode: `GET/POST /fapi/v1/multiAssetsMargin`
- Margin Type: `POST /fapi/v1/marginType`
- Leverage: `POST /fapi/v1/leverage`
- Place Order: `POST /fapi/v1/order`
- Batch Orders: `POST /fapi/v1/batchOrders`
- Cancel Order: `DELETE /fapi/v1/order`
- Listen Key: `POST/PUT/DELETE /fapi/v1/listenKey`

## Database Schema

The bot uses SQLite with indexed tables for performance:
- `liquidations`: Tracks all liquidation events with USDT value
- `trades`: Records all trading attempts with order type, parent tracking, and PNL data
- `order_relationships`: Maps main orders to their TP/SL orders
- `order_status`: Tracks order lifecycle from placement to fill/cancel
- `positions`: Current position tracking with entry prices and quantities
- All tables indexed for efficient queries

## Simulation Mode

When `simulate_only: true` in settings.json:
- Orders are logged but not sent to the exchange
- Trades are recorded with status 'SIMULATED'
- Useful for testing strategies without risking capital

## Web Dashboard

### Frontend Components

1. **Dashboard API (`src/api/api_server.py`)**
   - Flask server running on port 5000
   - RESTful API endpoints for positions, trades, liquidations, and statistics
   - Server-sent events (SSE) for real-time updates
   - Configuration management endpoints for adding/removing symbols
   - Database monitoring thread for live updates

2. **Dashboard UI (`templates/index.html`)**
   - Real-time monitoring of positions and P&L
   - Live liquidation and trade feed
   - Symbol configuration management
   - Performance statistics and charts
   - Account balance and margin information

3. **Frontend JavaScript (`static/js/dashboard.js`)**
   - Real-time data updates via SSE
   - Interactive charts for volume and performance tracking
   - Symbol management interface
   - Configuration editor with live validation

4. **Launcher (`launcher.py`)**
   - Orchestrates both bot and dashboard processes
   - Handles graceful shutdown of all services
   - Streams output from both processes with labels

### Dashboard API Endpoints

- `GET /`: Main dashboard page
- `GET /api/positions`: Current exchange positions
- `GET /api/account`: Account balance information
- `GET /api/liquidations`: Recent liquidation events
- `GET /api/trades`: Trade history with filtering and PNL data
- `GET /api/trades/<order_id>`: Detailed trade view with order relationships
- `GET /api/stats`: Aggregated statistics
- `GET /api/config`: Get current configuration
- `POST /api/config`: Update configuration
- `POST /api/config/symbol`: Update symbol configuration
- `GET /api/exchange/symbols`: Get available trading symbols
- `POST /api/config/symbol/add`: Add new symbol configuration
- `POST /api/config/symbol/remove`: Remove symbol configuration
- `GET /api/stream`: SSE endpoint for real-time updates
- `GET /api/health`: Health check endpoint