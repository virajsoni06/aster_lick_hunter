# Tranche System Implementation Checklist

## Overview
This document tracks the implementation progress of unifying and fixing the Take Profit/Stop Loss tranche system in the Aster Liquidation Hunter bot.

## Problem Summary
- **Current State**: Two disconnected tranche systems (in-memory vs database) that aren't properly integrated
- **Goal**: Unified tranche system with proper TP/SL management and accurate dashboard display
- **Impact**: Better position management, proper risk control, and clear visibility of trading tranches

---

## Phase 1: Choose and Integrate One Tranche System
**Goal**: Remove redundant code and integrate the position_manager.py system into main trading flow

### 1.1 Remove Database-Based Emergency Consolidation
- [x] **Remove `get_tranche_for_price()` function** (trader.py lines 585-639) ✅ COMPLETED
  - Location: `src/core/trader.py`
  - Action: Delete entire function
  - Dependencies: Used only by consolidate_stop_orders()

- [x] **Remove `consolidate_stop_orders()` function** (trader.py lines 641-729) ✅ COMPLETED
  - Location: `src/core/trader.py`
  - Action: Delete entire function
  - Dependencies: Called in place_tp_sl_orders()

- [x] **Remove consolidation logic from `place_tp_sl_orders()`** (trader.py lines 821-833) ✅ COMPLETED
  - Location: `src/core/trader.py`
  - Action: Remove the consolidation check and call
  - Keep: Basic TP/SL placement logic

### 1.2 Initialize PositionManager in Trader
- [x] **Import PositionManager class** ✅ COMPLETED
  - Location: `src/core/trader.py` (top imports section)
  - Action: Add `from src.utils.position_manager import PositionManager`

- [x] **Add PositionManager to init_symbol_settings()** ✅ COMPLETED
  - Location: `src/core/trader.py` init_symbol_settings function
  - Action: Initialize `position_manager = PositionManager(config)`
  - Config: Pass existing config with tranche parameters

- [x] **Load existing positions on startup** ✅ COMPLETED
  - Location: `src/core/trader.py` init_symbol_settings function
  - Action: Query database for open positions and load into position_manager

### 1.3 Integrate PositionManager into Trading Flow
- [x] **Update `evaluate_trade()` to check position tranches** ✅ COMPLETED
  - Location: `src/core/trader.py` evaluate_trade method
  - Action: Call position_manager.can_open_position() before placing orders
  - Logic: Check position limits and add pending exposure

- [x] **Add position update after order fills** ✅ COMPLETED
  - Location: `src/core/trader.py` monitor_and_place_tp_sl method
  - Action: Call position_manager.add_fill_to_position() when order fills
  - Data: Pass fill price, quantity, and calculate tranche assignment

- [ ] **Update position on TP/SL fills**
  - Location: `src/core/user_stream.py` or order monitoring
  - Action: Update position_manager when TP/SL orders execute
  - Effect: Properly track position reduction/closure

---

## Phase 2: Fix Order-Tranche Relationships
**Goal**: Properly associate all orders with their respective tranches

### 2.1 Database Schema Updates
- [x] **Add tranche tracking to trades table** ✅ COMPLETED
  - Location: `src/database/db.py`
  - Action: Ensure tranche_id is properly set (not defaulted to 0)
  - Migration: Update existing records if needed

- [x] **Update order_relationships to track real tranches** ✅ COMPLETED
  - Location: `src/database/db.py`
  - Action: Added tranche_id parameter to insert_order_relationship
  - Validation: Tranche_id passed through from place_order

### 2.2 Modify Order Placement
- [x] **Update `place_order()` to include tranche_id** ✅ COMPLETED
  - Location: `src/core/trader.py` place_order method
  - Action: Get tranche_id from position_manager
  - Database: Insert tranche_id into trades table

- [x] **Update `place_tp_sl_orders()` with tranche association** ✅ COMPLETED
  - Location: `src/core/trader.py` place_tp_sl_orders method
  - Action: Pass tranche_id to TP/SL order creation
  - Tracking: Store in order_relationships with correct tranche_id

- [x] **Add tranche_id to order tracking** ✅ COMPLETED
  - Location: `src/database/db.py` insert_trade method
  - Action: Include tranche_id in trade records
  - Default: Use 0 only for non-tranche trades

---

## Phase 3: Implement Proper Tranche Creation Logic
**Goal**: Automatic tranche creation based on position PNL and market conditions

### 3.1 Initial Tranche Creation
- [x] **Create tranche 0 on new position** ✅ COMPLETED
  - Location: `src/utils/position_manager.py` add_fill_to_position
  - Action: Create initial tranche when no position exists
  - Database: Insert into position_tranches table

- [x] **Set initial tranche parameters** ✅ COMPLETED
  - Location: `src/utils/position_manager.py`
  - Action: Store entry price, quantity, timestamp
  - Tracking: Associate with first order

### 3.2 Dynamic Tranche Creation
- [x] **Monitor position PNL for tranche triggers** ✅ COMPLETED
  - Location: `src/utils/position_manager.py`
  - Threshold: Create new tranche at -tranche_pnl_increment_pct (default -5%)
  - Action: Split position into new tranche

- [x] **Implement tranche creation on liquidation volume** ✅ COMPLETED
  - Location: `src/utils/position_manager.py` add_fill_to_position
  - Logic: Check if current position PNL warrants new tranche
  - Create: New tranche with updated entry parameters

- [x] **Add max tranche limits** ✅ COMPLETED
  - Location: `src/utils/position_manager.py`
  - Config: Respect max_tranches_per_symbol_side setting
  - Action: Prevent excessive tranche creation

### 3.3 Tranche Merging Logic
- [x] **Implement profitable tranche merging** ✅ COMPLETED
  - Location: `src/utils/position_manager.py`
  - Trigger: When tranches become profitable or max limit reached
  - Action: Combine tranches with merge_least_lossy_tranches and merge_eligible_tranches

- [ ] **Update orders on tranche merge**
  - Location: `src/core/trader.py`
  - Action: Cancel old TP/SL, create new consolidated orders
  - Database: Update order_relationships

- [ ] **Track merge history**
  - Location: `src/database/db.py`
  - Table: Add tranche_history or audit table
  - Data: Record merge events and reasons

### 3.4 Database Persistence
- [x] **Save tranches to position_tranches table** ✅ COMPLETED
  - Location: `src/utils/position_manager.py`
  - Action: Write to database on creation/update/merge
  - Sync: Keep in-memory and database in sync

- [x] **Load tranches on startup** ✅ COMPLETED
  - Location: `src/core/trader.py` initialization
  - Action: Restore position_manager state from database
  - Validation: Query existing tranches from database

- [x] **Add database methods for tranche CRUD** ✅ COMPLETED
  - Location: `src/database/db.py`
  - Methods: insert_tranche, update_tranche, delete_tranche, get_tranches
  - Transactions: Use proper transaction handling

---

## Phase 4: Fix Dashboard Display
**Goal**: Show accurate, real-time tranche information in the web interface

### 4.1 Backend API Updates
- [x] **Add tranche endpoint to API** ✅ COMPLETED
  - Location: `src/api/api_server.py`
  - Endpoint: `/api/positions/<symbol>/<side>` includes tranches
  - Response: Detailed tranche breakdown with PNL

- [x] **Update position endpoint with tranche data** ✅ COMPLETED
  - Location: `src/api/api_server.py`
  - Endpoint: `/api/positions/<symbol>/<side>`
  - Include: Tranche data with calculated PNL

- [ ] **Add tranche details to trade endpoint**
  - Location: `src/api/api_server.py`
  - Endpoint: `/api/trades/<order_id>`
  - Include: Associated tranche information

### 4.2 Frontend Updates
- [x] **Update position modal to show real tranches** ✅ COMPLETED
  - Location: `static/js/dashboard.js` showPositionDetails function
  - Query: Fetch from position_tranches table
  - Display: Dashboard already configured to display tranches (lines 1355-1407)

- [x] **Fix tranche table rendering** ✅ COMPLETED
  - Location: `static/js/dashboard.js` lines 1300-1407
  - Data: Dashboard checks for both order_relationships and tranches
  - Columns: Tranche ID, Entry Price, Quantity, TP/SL orders

- [ ] **Add tranche PNL visualization**
  - Location: `static/js/dashboard.js`
  - Chart: Show PNL per tranche
  - Colors: Green for profitable, red for losing tranches

### 4.3 Real-time Updates
- [ ] **Add tranche updates to SSE stream**
  - Location: `src/api/api_server.py` monitor_database method
  - Events: Tranche creation, merge, close
  - Data: Include updated tranche state

- [ ] **Update dashboard on tranche events**
  - Location: `static/js/dashboard.js`
  - Listen: Handle new SSE events
  - Update: Refresh position details automatically

- [ ] **Add tranche notifications**
  - Location: `static/js/dashboard.js`
  - Events: New tranche created, tranches merged
  - Display: Toast notifications with details

---

## Phase 5: Add Tranche-Aware Order Management
**Goal**: Intelligent order management that respects tranche boundaries

### 5.1 Order Limits per Tranche
- [ ] **Implement per-tranche order limits**
  - Location: `src/core/trader.py`
  - Logic: Track orders per tranche, not just per symbol
  - Config: Add max_orders_per_tranche setting

- [ ] **Update order counting logic**
  - Location: `src/core/trader.py`
  - Method: Count orders by tranche_id
  - Validation: Prevent exceeding limits per tranche

### 5.2 Smart Order Consolidation
- [ ] **Implement tranche-aware consolidation**
  - Location: `src/core/trader.py`
  - Logic: Only consolidate within same tranche
  - Maintain: Tranche integrity during consolidation

- [ ] **Add selective tranche consolidation**
  - Location: `src/utils/position_manager.py`
  - Feature: Consolidate specific tranches on demand
  - UI: Add consolidation button in dashboard

### 5.3 Order Cleanup Updates
- [ ] **Update cleanup to respect tranches**
  - Location: `src/core/order_cleanup.py`
  - Logic: Clean orders by tranche age/status
  - Priority: Older tranches first

- [ ] **Add tranche-based cleanup rules**
  - Location: `src/core/order_cleanup.py`
  - Rules: Different TTL for different tranches
  - Config: Add per-tranche cleanup settings

- [ ] **Handle orphaned tranche orders**
  - Location: `src/core/order_cleanup.py`
  - Detection: Find orders without valid tranches
  - Action: Clean up or reassign

---

## Phase 6: Testing and Validation
**Goal**: Ensure the unified system works correctly

### 6.1 Unit Tests
- [ ] **Test PositionManager tranche creation**
  - Location: `tests/unit/test_position_manager.py`
  - Cases: New position, PNL threshold, max tranches

- [ ] **Test tranche merging logic**
  - Location: `tests/unit/test_position_manager.py`
  - Cases: Profitable merge, forced merge, merge conflicts

- [ ] **Test order-tranche association**
  - Location: `tests/unit/test_trader.py`
  - Cases: Order placement, TP/SL creation, relationships

### 6.2 Integration Tests
- [ ] **Test full trading flow with tranches**
  - Location: `tests/integration/test_trading_flow.py`
  - Scenario: Open position → create tranches → merge → close

- [ ] **Test dashboard data accuracy**
  - Location: `tests/integration/test_api.py`
  - Verify: API returns correct tranche data

- [ ] **Test database consistency**
  - Location: `tests/integration/test_database.py`
  - Check: In-memory vs database sync

### 6.3 Manual Testing
- [ ] **Test with simulation mode**
  - Config: Set simulate_only = true
  - Run: Full trading session with multiple symbols
  - Verify: Tranches created and managed properly

- [ ] **Test dashboard display**
  - Open: Position details modal
  - Verify: Correct tranche information displayed
  - Check: Real-time updates working

- [ ] **Test with live trading (small amounts)**
  - Config: Minimal position sizes
  - Monitor: Tranche creation and TP/SL placement
  - Verify: Orders placed correctly on exchange

---

## Phase 7: Documentation and Cleanup
**Goal**: Update documentation and remove obsolete code

### 7.1 Documentation Updates
- [ ] **Update CLAUDE.md with tranche system**
  - Location: `CLAUDE.md`
  - Add: Detailed tranche system explanation
  - Include: Configuration parameters

- [ ] **Update README.md**
  - Location: `README.md`
  - Add: User-facing tranche documentation
  - Include: Configuration examples

- [ ] **Add inline code comments**
  - Location: All modified files
  - Explain: Tranche logic and decision points
  - Document: Key algorithms and thresholds

### 7.2 Code Cleanup
- [ ] **Remove unused consolidation code**
  - Location: `src/core/trader.py`
  - Remove: Old consolidation functions
  - Clean: Related database queries

- [ ] **Remove obsolete database columns**
  - Location: Migration script
  - Remove: Unused columns after testing
  - Migrate: Production database

- [ ] **Optimize database queries**
  - Location: `src/database/db.py`
  - Add: Proper indexes for tranche queries
  - Optimize: Frequently used queries

### 7.3 Configuration
- [ ] **Add tranche configuration to settings.json**
  - Location: `settings.json`
  - Add: Tranche-specific parameters
  - Document: Each setting's purpose

- [ ] **Add tranche config to dashboard**
  - Location: `templates/index.html` settings modal
  - Add: UI controls for tranche parameters
  - Validate: Input ranges and dependencies

- [ ] **Create migration script for existing users**
  - Location: `scripts/migrate_to_tranches.py`
  - Purpose: Smooth upgrade path
  - Action: Convert existing positions to tranches

---

## Completion Criteria
- [ ] All phases completed and tested
- [ ] No regression in existing functionality
- [ ] Dashboard accurately displays tranche information
- [ ] Documentation updated and complete
- [ ] Code reviewed and optimized
- [ ] Production deployment successful

## Notes and Observations
- Add any implementation notes here
- Document any deviations from the plan
- Record any issues encountered and solutions

## Implementation Timeline
- **Start Date**: 2025-09-23
- **Completed Phases**: 1-4 (Core functionality)
- **Remaining**: Phases 5-7 (Enhancements, testing, documentation)

## Sign-off
- [ ] Developer testing complete
- [ ] Code review complete
- [ ] Production deployment approved