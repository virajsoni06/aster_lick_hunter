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

# Initialize or migrate database schema
python scripts/init_database.py
python scripts/migrate_db.py
```

Dashboard available at: http://localhost:5000

## Project Structure

```
aster_lick_hunter/
├── main.py                 # Main bot entry point
├── launcher.py             # Orchestrates bot and dashboard processes
├── settings.json           # Trading configuration
├── .env                    # API credentials (not in repo)
├── requirements.txt        # Python dependencies
├── CLAUDE.md              # Project documentation for Claude Code
├── README.md              # User documentation
│
├── src/                   # Source code directory
│   ├── api/               # Dashboard API and services
│   │   ├── api_server.py  # Flask REST API server
│   │   └── pnl_tracker.py # P&L calculation service
│   │
│   ├── core/              # Core trading bot logic
│   │   ├── streamer.py    # WebSocket liquidation stream
│   │   ├── trader.py      # Trading logic and order management
│   │   ├── order_cleanup.py # Stale order cleanup service
│   │   └── user_stream.py # User data WebSocket stream
│   │
│   ├── database/          # Database layer
│   │   └── db.py          # SQLite database operations
│   │
│   └── utils/             # Utility modules
│       ├── auth.py        # API authentication
│       ├── config.py      # Configuration management
│       ├── colored_logger.py # Colored console logging
│       ├── endpoint_weights.py # API rate limit weights
│       ├── rate_limiter.py # Rate limiting implementation
│       ├── order_manager.py # Order management utilities
│       ├── position_manager.py # Position tracking
│       └── utils.py       # General utilities
│
├── scripts/               # Setup and maintenance scripts
│   ├── init_database.py  # Initialize database schema
│   ├── migrate_db.py     # Database migrations
│   ├── setup_env.py      # Environment setup
│   └── analyze_tranches.py # Tranche analysis tool
│
├── static/                # Frontend assets
│   ├── css/
│   │   └── dashboard.css # Dashboard styles
│   └── js/
│       └── dashboard.js  # Dashboard JavaScript
│
├── templates/             # HTML templates
│   ├── index.html        # Dashboard main page
│   └── setup.html        # Initial setup page
│
├── tests/                 # Test files
│   ├── test_colors.py    # Logger color tests
│   └── test_rate_limiter.py # Rate limiter tests
│
├── backups/              # Backup directory for code versions
├── data/                 # Data storage (if needed)
└── docs/                 # Additional documentation (if needed)
```

## File Placement Guidelines

When creating new files for the project, follow these conventions:

### Source Code (`src/`)
- **API Endpoints & Services** → `src/api/`
  - New REST endpoints, dashboard features
  - Services that support the web interface
  - Example: `src/api/websocket_handler.py`

- **Core Trading Logic** → `src/core/`
  - Trading strategies, order execution
  - Market data processing, signal generation
  - WebSocket stream handlers
  - Example: `src/core/strategy_macd.py`

- **Database Operations** → `src/database/`
  - New database models or schemas
  - Migration scripts for schema changes
  - Database utilities and helpers
  - Example: `src/database/models.py`

- **Utility Functions** → `src/utils/`
  - Shared utilities used across modules
  - Helper functions, formatters, validators
  - External service integrations
  - Example: `src/utils/notifications.py`

### Scripts (`scripts/`)
- One-time setup or migration scripts
- Data analysis or reporting tools
- Maintenance and cleanup utilities
- Example: `scripts/export_trades.py`

### Frontend (`static/` and `templates/`)
- **CSS Files** → `static/css/`
  - Component-specific styles
  - Theme files

- **JavaScript** → `static/js/`
  - Frontend logic and interactions
  - Chart implementations
  - API client code

- **HTML Templates** → `templates/`
  - New dashboard pages
  - Email templates (if needed)

### Configuration Files
- Root directory for `.env`, `settings.json`
- Config templates in `docs/` if providing examples

## Test Organization

### Test Structure
```
tests/
├── unit/                  # Unit tests for individual functions
│   ├── test_trader.py
│   ├── test_auth.py
│   └── test_database.py
│
├── integration/           # Integration tests
│   ├── test_api.py
│   └── test_websocket.py
│
├── fixtures/              # Test data and fixtures
│   ├── sample_liquidations.json
│   └── mock_orderbook.json
│
└── conftest.py           # Pytest configuration and shared fixtures
```

### Test Naming Conventions
- Test files: `test_<module_name>.py`
- Test classes: `Test<ClassName>`
- Test methods: `test_<method_name>_<scenario>`
- Example: `test_place_order_insufficient_balance()`

### Running Tests
```bash
# Run individual test files directly (no pytest required)
python tests/test_trade_logic.py
python tests/test_rate_limiter.py
python tests/test_tranche_system.py
python tests/test_order_cleanup.py

# Test specific functionality
python tests/test_colors.py         # Test colored logging output
python tests/test_collateral.py     # Test collateral calculations
```

### Test Guidelines
- Each source module should have corresponding tests
- Mock external API calls and database operations in unit tests
- Use fixtures for common test data
- Integration tests can use a test database
- Keep tests independent and idempotent
- Use descriptive test names that explain the scenario

## Development Commands

```bash
# Check Python syntax errors
python -m py_compile main.py launcher.py
python -m py_compile src/core/*.py src/api/*.py src/database/*.py src/utils/*.py

# Running with debug output (Windows)
python main.py 2>&1 | python -c "import sys; [print(line, end='') for line in sys.stdin]" > debug.log

# Running with debug output (Unix/Linux)
python main.py 2>&1 | tee debug.log

# Database maintenance
python scripts/analyze_tranches.py       # Analyze tranche performance
python scripts/cleanup_test_tranches.py  # Clean test data from database
```

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

## Important Implementation Details

### Startup Verification
The order cleanup service performs startup verification:
- Verifies exchange connectivity
- Checks position mode and margin settings
- Validates API credentials
- Logs startup status with standardized format

### Tranche System
The bot implements an intelligent position management system through "tranches":
- Each new position starts as tranche 0
- When a position's unrealized PNL drops below -tranche_pnl_increment_pct (default -5%), new liquidations trigger creation of a new tranche
- Profitable tranches are automatically merged to optimize capital efficiency
- Maximum tranches per symbol/side is configurable (max_tranches_per_symbol_side)
- Tranche tracking is handled via the tranche_id field in trades table

### Database Connections
- Uses SQLite with thread-safe connection handling
- Fresh database connections are obtained for each operation via `get_db_conn()`
- All connections are properly closed after use to prevent locking issues
- Database files: `bot.db` (main), backup copies created with data prefix

### Order Precision Handling
- Symbol specifications (minQty, stepSize, pricePrecision) are cached from exchangeInfo endpoint
- Price and quantity calculations use proper rounding based on exchange requirements
- The `round_to_precision()` function in trader.py ensures all values meet exchange specifications
- All orders use the configured `time_in_force` setting (default: GTC)

### Rate Limiting
- Built-in rate limit protection with configurable buffer percentage
- Implements exponential backoff on rate limit errors
- Request tracking to avoid exceeding exchange limits

### Background Services
- Order cleanup service runs in separate thread (order_cleanup.py)
  - Startup verification on initialization
  - Periodic cleanup of stale limit orders (configurable timeout)
  - Automatic cancellation of related TP/SL orders
  - Reduced logging noise for cleaner output
- User data stream maintains WebSocket connection for real-time updates
- Database monitoring thread in API server for live dashboard updates
- All background services handle graceful shutdown via threading events

### Error Handling
- Emergency print function available for debugging critical issues (disabled by default)
- Graceful handling of database lock issues with fresh connections
- Automatic retry logic for transient API failures
- Comprehensive error logging with context information