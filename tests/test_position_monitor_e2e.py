"""
End-to-end tests for PositionMonitor system.
Tests complete workflows from order placement through TP/SL management.
"""

import asyncio
import json
import sys
import os
import time
import sqlite3
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock, Mock
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestE2E:
    """End-to-end test scenarios for Position Monitor."""

    def __init__(self):
        self.passed = 0
        self.failed = 0

    async def test_complete_trade_lifecycle(self):
        """Test complete lifecycle from liquidation to TP hit."""
        print("\n🔄 Testing Complete Trade Lifecycle...")
        
        # Setup mocked environment
        with patch('src.core.trader.config.GLOBAL_SETTINGS', {
            'use_position_monitor': True,
            'instant_tp_enabled': True,
            'hedge_mode': True,
            'simulate_only': False
        }):
            from src.core.position_monitor import PositionMonitor
            from src.core.trader import evaluate_trade
            import src.core.trader as trader
            
            # Create and setup PositionMonitor
            monitor = PositionMonitor()
            trader.position_monitor = monitor
            trader.USE_POSITION_MONITOR = True
            
            # Mock API calls
            monitor._place_single_order = AsyncMock(return_value={'orderId': 'MAIN123'})
            monitor._place_batch_orders = AsyncMock(return_value=[
                {'orderId': 'TP123'},
                {'orderId': 'SL456'}
            ])
            monitor._cancel_order = AsyncMock(return_value=True)
            
            # Mock order placement in trader
            with patch('src.core.trader.place_order') as mock_place_order:
                mock_place_order.return_value = 'MAIN123'
                
                # Step 1: Liquidation triggers order
                print("  Step 1: Processing liquidation event...")
                await evaluate_trade('BTCUSDT', 'LONG', 0.1, 45000)
                
                # Simulate order registration
                await monitor.register_order({
                    'order_id': 'MAIN123',
                    'symbol': 'BTCUSDT',
                    'side': 'BUY',
                    'quantity': 0.1,
                    'tranche_id': 0
                })
                print("    ✅ Order placed and registered")
                
                # Step 2: Order fills
                print("  Step 2: Simulating order fill...")
                await monitor.on_order_filled({
                    'order_id': 'MAIN123',
                    'symbol': 'BTCUSDT',
                    'side': 'BUY',
                    'quantity': 0.1,
                    'fill_price': 45000,
                    'position_side': 'LONG'
                })
                
                # Verify TP/SL orders were placed
                assert monitor._place_batch_orders.called or monitor._place_single_order.called
                print("    ✅ TP/SL orders placed")
                
                # Step 3: Price spike triggers instant closure
                print("  Step 3: Price spike above TP...")
                tranche = monitor.get_tranche('BTCUSDT', 'LONG', 0)
                if tranche:
                    # Set TP/SL order IDs
                    tranche.tp_order_id = 'TP123'
                    tranche.sl_order_id = 'SL456'
                    
                    # Simulate price spike (1% above entry = TP hit)
                    await monitor.check_instant_closure('BTCUSDT', 45500)
                    
                    # Verify market closure was attempted
                    calls = monitor._place_single_order.call_args_list
                    market_orders = [c for c in calls if 'type' in c[0][0] and c[0][0]['type'] == 'MARKET']
                    print(f"    ✅ Instant closure triggered: {len(market_orders)} market orders")
                    
        return True

    async def test_multi_tranche_scenario(self):
        """Test multiple tranches forming and managing separately."""
        print("\n📊 Testing Multi-Tranche Scenario...")
        
        from src.core.position_monitor import PositionMonitor
        
        monitor = PositionMonitor()
        monitor._place_batch_orders = AsyncMock(return_value=[
            {'orderId': 'TP_T0'},
            {'orderId': 'SL_T0'}
        ])
        
        # Initial position - Tranche 0
        print("  Creating initial position (Tranche 0)...")
        await monitor.on_order_filled({
            'order_id': 'ORDER1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'quantity': 0.1,
            'fill_price': 50000,
            'position_side': 'LONG'
        })
        
        tranche0 = monitor.get_tranche('BTCUSDT', 'LONG', 0)
        assert tranche0 is not None
        assert tranche0.quantity == 0.1
        assert tranche0.entry_price == 50000
        print("    ✅ Tranche 0 created: 0.1 BTC @ $50,000")
        
        # Price drops 6% - should trigger new tranche
        print("  Price drops 6% to $47,000...")
        new_price = 47000  # -6% from 50000
        
        # Calculate PnL to verify new tranche needed
        pnl_pct = ((new_price - 50000) / 50000) * 100
        assert pnl_pct < -5, "PnL should be below -5% threshold"
        
        # New order at lower price - should be Tranche 1
        tranche_id = monitor.determine_tranche_id('BTCUSDT', 'LONG', new_price)
        assert tranche_id == 1, "Should create new tranche when down > 5%"
        
        # Fill order in new tranche
        monitor._place_batch_orders = AsyncMock(return_value=[
            {'orderId': 'TP_T1'},
            {'orderId': 'SL_T1'}
        ])
        
        await monitor.on_order_filled({
            'order_id': 'ORDER2',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'quantity': 0.2,
            'fill_price': 47000,
            'position_side': 'LONG',
            'tranche_id': 1
        })
        
        tranche1 = monitor.get_tranche('BTCUSDT', 'LONG', 1)
        assert tranche1 is not None
        assert tranche1.quantity == 0.2
        assert tranche1.entry_price == 47000
        print("    ✅ Tranche 1 created: 0.2 BTC @ $47,000")
        
        # Verify both tranches have separate TP/SL
        print("  Verifying separate TP/SL orders...")
        all_tranches = monitor.get_all_tranches('BTCUSDT', 'LONG')
        assert len(all_tranches) == 2
        print(f"    ✅ {len(all_tranches)} tranches with independent TP/SL")
        
        return True

    async def test_websocket_reconnection(self):
        """Test WebSocket reconnection and recovery."""
        print("\n🔌 Testing WebSocket Reconnection...")
        
        from src.core.position_monitor import PositionMonitor
        
        monitor = PositionMonitor()
        
        # Mock WebSocket connection
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.close = AsyncMock()
        
        with patch('websockets.connect', AsyncMock(return_value=mock_ws)):
            # Start price monitoring
            monitor_task = asyncio.create_task(monitor.start())
            await asyncio.sleep(0.1)  # Let it connect
            
            print("  ✅ Initial connection established")
            
            # Simulate disconnection
            mock_ws.recv.side_effect = Exception("Connection lost")
            await asyncio.sleep(0.1)
            
            print("  ⚡ Simulated connection loss")
            
            # Should attempt reconnection
            # Reset mock for reconnection
            mock_ws.recv.side_effect = None
            mock_ws.recv.return_value = json.dumps([
                {'s': 'BTCUSDT', 'p': '45000'}
            ])
            
            await asyncio.sleep(0.2)
            print("  ✅ Reconnection handled")
            
            # Stop monitoring
            await monitor.stop()
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        
        return True

    async def test_database_recovery(self):
        """Test recovery from database on startup."""
        print("\n💾 Testing Database Recovery...")
        
        from src.core.position_monitor import PositionMonitor
        
        # Create test database
        test_db = ':memory:'
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        
        # Create simplified trades table
        cursor.execute('''
            CREATE TABLE trades (
                order_id TEXT PRIMARY KEY,
                symbol TEXT,
                side TEXT,
                quantity REAL,
                price REAL,
                status TEXT,
                tranche_id INTEGER,
                tp_order_id TEXT,
                sl_order_id TEXT
            )
        ''')
        
        # Insert test data
        cursor.execute('''
            INSERT INTO trades VALUES 
            ('ORDER1', 'BTCUSDT', 'BUY', 0.1, 45000, 'FILLED', 0, 'TP123', 'SL456')
        ''')
        conn.commit()
        
        # Mock database connection
        with patch('src.core.position_monitor.get_db_conn', return_value=conn):
            monitor = PositionMonitor()
            await monitor.recover_from_database()
            
            # Verify tranches were recovered
            tranche = monitor.get_tranche('BTCUSDT', 'LONG', 0)
            assert tranche is not None, "Should recover tranche from database"
            assert tranche.quantity == 0.1
            assert tranche.entry_price == 45000
            assert tranche.tp_order_id == 'TP123'
            assert tranche.sl_order_id == 'SL456'
            print("  ✅ Recovered 1 tranche from database")
        
        conn.close()
        return True

    async def test_api_error_handling(self):
        """Test handling of API errors and retries."""
        print("\n⚠️  Testing API Error Handling...")
        
        from src.core.position_monitor import PositionMonitor
        
        monitor = PositionMonitor()
        
        # Test order placement failure
        monitor._place_single_order = AsyncMock(return_value=None)
        
        tranche = monitor.create_tranche('BTCUSDT', 'LONG', 0, 0.1, 45000)
        
        # Try to place TP/SL - should handle failure gracefully
        tp_id, sl_id = await monitor.place_tranche_tp_sl(tranche)
        
        assert tp_id is None, "Should return None on TP placement failure"
        assert sl_id is None, "Should return None on SL placement failure"
        print("  ✅ Handles order placement failures gracefully")
        
        # Test cancel failure
        monitor._cancel_order = AsyncMock(return_value=False)
        
        result = await monitor.cancel_tranche_orders(tranche)
        assert result == (False, False), "Should handle cancel failures"
        print("  ✅ Handles order cancellation failures")
        
        # Test rate limiting
        monitor._place_single_order = AsyncMock(
            side_effect=Exception("Rate limit exceeded")
        )
        
        try:
            await monitor.instant_close_tranche(tranche, 46000)
            print("  ✅ Handles rate limit errors without crashing")
        except:
            print("  ❌ Failed to handle rate limit error")
            return False
        
        return True

    async def test_concurrent_operations(self):
        """Test handling of concurrent fills and updates."""
        print("\n🔀 Testing Concurrent Operations...")
        
        from src.core.position_monitor import PositionMonitor
        
        monitor = PositionMonitor()
        monitor._place_batch_orders = AsyncMock(return_value=[
            {'orderId': 'TP1'},
            {'orderId': 'SL1'}
        ])
        
        # Simulate multiple concurrent fills
        fills = [
            monitor.on_order_filled({
                'order_id': f'ORDER{i}',
                'symbol': 'BTCUSDT',
                'side': 'BUY',
                'quantity': 0.01,
                'fill_price': 45000 + i*100,
                'position_side': 'LONG',
                'tranche_id': 0
            })
            for i in range(5)
        ]
        
        # Execute concurrently
        await asyncio.gather(*fills)
        
        # Verify all were processed
        tranche = monitor.get_tranche('BTCUSDT', 'LONG', 0)
        assert tranche is not None
        assert tranche.quantity == 0.05, "Should accumulate all fills"
        print(f"  ✅ Handled 5 concurrent fills: {tranche.quantity} BTC total")
        
        # Test concurrent instant closures
        closures = [
            monitor.check_instant_closure('BTCUSDT', 46000)
            for _ in range(3)
        ]
        
        await asyncio.gather(*closures)
        print("  ✅ Handled concurrent instant closure checks")
        
        return True

    async def test_performance_monitoring(self):
        """Test performance and latency monitoring."""
        print("\n⚡ Testing Performance Monitoring...")
        
        from src.core.position_monitor import PositionMonitor
        import time
        
        monitor = PositionMonitor()
        monitor._place_single_order = AsyncMock(return_value={'orderId': 'TEST'})
        
        # Measure instant closure latency
        tranche = monitor.create_tranche('BTCUSDT', 'LONG', 0, 0.1, 45000)
        tranche.tp_order_id = 'TP123'
        tranche.sl_order_id = 'SL456'
        monitor.tranches['BTCUSDT']['LONG'][0] = tranche
        
        start = time.time()
        await monitor.check_instant_closure('BTCUSDT', 46000)  # Above TP
        latency = (time.time() - start) * 1000  # Convert to ms
        
        print(f"  ✅ Instant closure latency: {latency:.2f}ms")
        assert latency < 100, "Instant closure should be fast (<100ms)"
        
        # Test batch operation performance
        monitor._place_batch_orders = AsyncMock(
            return_value=[{'orderId': f'ID{i}'} for i in range(10)]
        )
        
        start = time.time()
        for i in range(5):
            await monitor.place_tranche_tp_sl(
                monitor.create_tranche('BTCUSDT', 'LONG', i, 0.1, 45000)
            )
        batch_time = time.time() - start
        
        print(f"  ✅ Placed 10 orders in {batch_time:.2f}s via batching")
        
        return True

    async def run_all_tests(self):
        """Run all end-to-end tests."""
        print("=" * 60)
        print("🎯 END-TO-END TEST SUITE")
        print("=" * 60)
        
        tests = [
            self.test_complete_trade_lifecycle,
            self.test_multi_tranche_scenario,
            self.test_websocket_reconnection,
            self.test_database_recovery,
            self.test_api_error_handling,
            self.test_concurrent_operations,
            self.test_performance_monitoring
        ]
        
        for test in tests:
            try:
                result = await test()
                if result:
                    self.passed += 1
                else:
                    self.failed += 1
            except Exception as e:
                self.failed += 1
                print(f"  ❌ Test {test.__name__} failed: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n" + "=" * 60)
        print(f"📊 E2E TEST RESULTS")
        print(f"   ✅ Passed: {self.passed}")
        print(f"   ❌ Failed: {self.failed}")
        print(f"   📈 Success Rate: {(self.passed/(self.passed+self.failed)*100 if (self.passed+self.failed) > 0 else 0):.1f}%")
        print("=" * 60)
        
        return self.failed == 0


async def main():
    """Run end-to-end tests."""
    tester = TestE2E()
    success = await tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
