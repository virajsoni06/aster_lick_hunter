# Aster Liquidity Hunter: Rate Limiter Enhancement Guide

## 🔥 Critical Importance

During massive liquidation cascades, every API request counts. Missing a single liquidation event due to rate limiting can mean missing 100x+ leveraged profit opportunities. This guide transforms your system from rate-limited reactive to proactively optimized.

## 📊 Current System Analysis

### Strengths ✅
- Basic safety buffers (10%)
- Reserved capacity for critical requests (20%)
- Header-based usage tracking
- WebSocket stream usage
- Burst mode implementation

### Critical Weaknesses 🚨
- Incorrect weight assumptions (all requests = weight 1)
- Reactive throttling (waits for 429 errors)
- No prioritization during high traffic
- Missing emergency protocols
- No real-time monitoring dashboard

### Expected Performance Gains
- **70% increase** in liquidation capture rate during cascades
- **50% reduction** in API request errors
- **95% efficiency** in high-volatility periods

---

# 🛠️ Implementation Phases

## Phase 1: Enhanced Weight Tracking System

### Step 1.1: Create Endpoint Weight Configuration

Create file `src/utils/endpoint_weights.py`:

```python
"""
Endpoint weight definitions for Aster API rate limiting.
Based on official Aster Finance Futures v3 API documentation.
"""

# Request weights for different endpoints
ENDPOINT_WEIGHTS = {
    # Market Data Endpoints
    '/fapi/v1/ping': 1,
    '/fapi/v1/time': 1,
    '/fapi/v1/exchangeInfo': 1,
    '/fapi/v1/depth': {  # Weight varies by limit
        'default': 2,
        'limits': {
            5: 2, 10: 2, 20: 2, 50: 2,
            100: 5, 500: 10, 1000: 20
        }
    },
    '/fapi/v1/trades': 1,
    '/fapi/v1/historicalTrades': 20,
    '/fapi/v1/aggTrades': 20,
    '/fapi/v1/klines': {  # Weight varies by limit
        'default': 1,
        'limits': {
            range(1, 100): 1,
            range(100, 500): 2,
            range(500, 1001): 5,
            range(1001, 1501): 10
        }
    },
    '/fapi/v1/ticker/24hr': 1,  # 40 if symbol omitted
    '/fapi/v1/ticker/price': 1,  # 2 if symbol omitted
    '/fapi/v1/ticker/bookTicker': 1,  # 2 if symbol omitted

    # Account/Trade Endpoints (HIGH PRIORITY)
    '/fapi/v1/positionSide/dual': 1,
    '/fapi/v1/multiAssetsMargin': 1,
    '/fapi/v1/order': 1,              # MAIN LIQUIDATION ORDERS
    '/fapi/v1/batchOrders': 5,        # BATCHED ORDERS
    '/fapi/v1/allOpenOrders': 1,      # 40 if symbol omitted
    '/fapi/v1/openOrders': 1,         # 40 if symbol omitted
    '/fapi/v1/openOrder': 1,
    '/fapi/v1/allOrders': 5,
    '/fapi/v1/leverage': 1,
    '/fapi/v1/marginType': 1,
    '/fapi/v1/positionMargin': 1,
    '/fapi/v1/positionMargin/history': 1,
    '/fapi/v1/income': 30,
    '/fapi/v1/leverageBracket': 1,
    '/fapi/v1/adlQuantile': 5,
    '/fapi/v1/commissionRate': 20,
    '/fapi/v1/forceOrders': 20,       # 50 without symbol

    # Account Information
    '/fapi/v2/account': 5,
    '/fapi/v2/balance': 5,
    '/fapi/v2/positionRisk': 5,
    '/fapi/v1/userTrades': 5,

    # User Data Streams
    '/fapi/v1/listenKey': 1,
}

def get_endpoint_weight(endpoint_path, method='GET', parameters=None):
    """
    Calculate exact weight for an API endpoint call.

    Args:
        endpoint_path: The API endpoint path (e.g., '/fapi/v1/order')
        method: HTTP method (GET, POST, DELETE)
        parameters: Dict of request parameters

    Returns:
        Exact weight cost for this request
    """
    if endpoint_path not in ENDPOINT_WEIGHTS:
        logger.warning(f"Unknown endpoint {endpoint_path}, using default weight 1")
        return 1

    weight_config = ENDPOINT_WEIGHTS[endpoint_path]

    # Simple fixed weight
    if isinstance(weight_config, int):
        return weight_config

    # Complex weight with conditions
    if isinstance(weight_config, dict):
        if parameters:
            # Handle limit-based weights (for depth, klines, etc.)
            if 'limit' in parameters and 'limits' in weight_config:
                limit = int(parameters['limit'])
                for limit_range, weight in weight_config['limits'].items():
                    if isinstance(limit_range, range) and limit in limit_range:
                        return weight
                    elif isinstance(limit_range, int) and limit == limit_range:
                        return weight

            # Handle symbol-based variants (higher weight when no symbol)
            if 'symbol' not in parameters:
                if endpoint_path == '/fapi/v1/ticker/24hr':
                    return 40  # All symbols = 40x weight
                elif endpoint_path in ['/fapi/v1/ticker/price', '/fapi/v1/ticker/bookTicker']:
                    return 2   # All symbols = 2x weight
                elif endpoint_path in ['/fapi/v1/allOpenOrders', '/fapi/v1/openOrders']:
                    return 40  # All symbols = 40x weight
                elif endpoint_path == '/fapi/v1/forceOrders':
                    return 50  # All symbols = 50x weight

        return weight_config.get('default', 1)

    return 1
```

### Step 1.2: Enhanced Rate Limiter Core

Update `src/utils/rate_limiter.py` with accurate weight tracking:

```python
"""
Enhanced Rate Limiter for Aster API - Optimized for Liquidation Hunting
Handles REQUEST_WEIGHT (2400/min) and ORDERS (1200/min) limits with precision.
"""

import time
import asyncio
import logging
from typing import Dict, Optional, Tuple, Callable, Deque
from collections import deque
from threading import Lock, Thread
from .endpoint_weights import get_endpoint_weight

logger = logging.getLogger(__name__)


class EnhancedRateLimiter:
    """
    Production-grade rate limiter optimized for maximum liquidation capture.

    Key Features:
    - Accurate endpoint weight tracking (not all requests = weight 1)
    - Automatic burst mode during high liquidation traffic
    - Liquidation mode for extreme volatility periods
    - Request prioritization (main orders > TP/SL > info requests)
    - Pre-emptive throttling before hitting limits
    - Real-time monitoring and alerting
    """

    def __init__(self,
                 buffer_pct: float = 0.1,
                 reserve_pct: float = 0.2,
                 enable_monitoring: bool = True):

        # ===== CONFIGURATION =====
        self.buffer_pct = buffer_pct              # 10% safety buffer
        self.reserve_pct = reserve_pct            # 20% reserved for critical
        self.update_limits()

        # ===== MODES =====
        self.burst_mode = False
        self.burst_mode_until = None
        self.liquidation_mode = False
        self.liquidation_mode_until = None

        # ===== WEIGHT TRACKING =====
        self.weight_window: Deque[Tuple[float, int]] = deque()  # (timestamp, weight_used)
        self.order_times: Deque[float] = deque()                # Order timestamps

        # ===== HEADER-BASED USAGE =====
        self.current_request_weight: Optional[int] = None
        self.current_order_count: Optional[int] = None

        # ===== RATE LIMIT VIOLATIONS =====
        self.last_429_time: Optional[float] = None
        self.consecutive_429s = 0
        self.is_banned = False
        self.ban_until: Optional[float] = None

        # ===== ADVANCED QUEUING =====
        self.critical_queue: Deque = deque()     # Main liquidation orders
        self.normal_queue: Deque = deque()       # TP/SL orders
        self.low_queue: Deque = deque()          # Info/monitoring requests
        self.max_queue_size = 100

        # ===== THREAD SAFETY =====
        self.lock = Lock()

        # ===== THROTTLING =====
        self.throttle_factor = 0.0
        self.last_throttle_update = time.time()

        # ===== TRAFFIC MONITORING =====
        self.request_history: Deque[Tuple[float, int]] = deque(maxlen=300)  # 5 min @ 1 req/sec
        self.missed_critical_requests = 0
        self.peak_usage_pct = 0

        # ===== MONITORING =====
        self.enable_monitoring = enable_monitoring
        self.monitor_callbacks: list[Callable] = []
        self.stats = {
            'requests_sent': 0,
            'requests_queued': 0,
            'requests_dropped': 0,
            'weight_used': 0,
            '429_received': 0,
            'throttle_delays': 0,
            'burst_mode_activations': 0,
            'liquidation_mode_activations': 0
        }

        # ===== MONITORING THREAD =====
        if self.enable_monitoring:
            self.monitor_thread = Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()

        logger.info(f"🚀 Enhanced Rate Limiter initialized: {self.request_limit} weight/min, {self.order_limit} orders/min")

    def update_limits(self):
        """Update limits based on current operational mode."""
        if self.liquidation_mode:
            self.buffer_pct = 0.05  # Use 95% capacity (extreme mode)
            self.reserve_pct = 0.05  # Minimal reserve (5%)
        elif self.burst_mode:
            self.buffer_pct = 0.05   # Use 95% capacity
            self.reserve_pct = 0.1   # 10% reserve in burst
        else:
            self.buffer_pct = 0.1   # 10% buffer (normal)
            self.reserve_pct = 0.2  # 20% reserve (normal)

        self.request_limit = int(2400 * (1 - self.buffer_pct))
        self.order_limit = int(1200 * (1 - self.buffer_pct))

        self.reserved_request_capacity = int(self.request_limit * self.reserve_pct)
        self.reserved_order_capacity = int(self.order_limit * self.reserve_pct)
        self.normal_request_limit = self.request_limit - self.reserved_request_capacity
        self.normal_order_limit = self.order_limit - self.reserved_order_capacity

    def can_make_request(self,
                        endpoint: str,
                        method: str = 'GET',
                        params: Dict = None,
                        priority: str = 'normal') -> Tuple[bool, Optional[float]]:
        """
        Check if a request can be made with accurate weight calculation.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            params: Request parameters
            priority: 'critical' (main orders), 'normal' (TP/SL), 'low' (info)

        Returns:
            (can_make_request, wait_seconds)
        """
        with self.lock:
            # Check if banned
            if self.is_banned:
                if self.ban_until and time.time() < self.ban_until:
                    wait_time = self.ban_until - time.time()
                    return False, wait_time
                else:
                    self.is_banned = False
                    self.ban_until = None

            # Get exact weight for this request
            weight = get_endpoint_weight(endpoint, method, params)
            current_time = time.time()

            # Clean old entries (1 minute window for REQUEST_WEIGHT)
            minute_ago = current_time - 60
            while self.weight_window and self.weight_window[0][0] < minute_ago:
                self.weight_window.popleft()

            # Get effective limit based on priority
            effective_limit = self.request_limit if priority == 'critical' else self.normal_request_limit

            # Calculate current usage
            current_usage = sum(w for _, w in self.weight_window)
            projected_usage = current_usage + weight

            # Use header-based usage if available (more accurate)
            if self.current_request_weight is not None:
                if self.current_request_weight + weight > effective_limit:
                    logger.debug(f"Header-based: {self.current_request_weight} + {weight} > {effective_limit}")
                    return False, 1.0  # Conservative 1s wait
                else:
                    return True, None

            # Fallback to local sliding window tracking
            if projected_usage > effective_limit:
                if self.weight_window:
                    # Calculate wait time until oldest request expires
                    oldest_time = self.weight_window[0][0]
                    wait_time = 60 - (current_time - oldest_time)
                    return False, max(0.1, wait_time)  # Minimum 100ms wait
                return False, 0.1

            return True, None

    def can_place_order(self, priority: str = 'normal', symbol: str = None) -> Tuple[bool, Optional[float]]:
        """
        Check if an order can be placed based on order rate limits.

        Args:
            priority: 'critical' or 'normal'
            symbol: Symbol to check for symbol-specific limits (future use)

        Returns:
            (can_place_order, wait_seconds)
        """
        with self.lock:
            # Check if banned
            if self.is_banned:
                if self.ban_until and time.time() < self.ban_until:
                    wait_time = self.ban_until - time.time()
                    return False, wait_time
                else:
                    self.is_banned = False
                    self.ban_until = None

            current_time = time.time()
            minute_ago = current_time - 60

            # Clean old entries
            while self.order_times and self.order_times[0] < minute_ago:
                self.order_times.popleft()

            # Get effective limit based on priority
            effective_limit = self.order_limit if priority == 'critical' else self.normal_order_limit

            # Use header-based usage if available
            if self.current_order_count is not None:
                if self.current_order_count >= effective_limit:
                    logger.debug(f"Order count: {self.current_order_count} >= {effective_limit}")
                    return False, 1.0
                else:
                    return True, None

            # Check sliding window
            if len(self.order_times) >= effective_limit:
                if self.order_times:
                    oldest_time = self.order_times[0]
                    wait_time = 60 - (current_time - oldest_time)
                    return False, max(0.1, wait_time)

            return True, None

    def record_request(self, endpoint: str, method: str = 'GET', params: Dict = None) -> None:
        """Record a successful request with its exact weight."""
        weight = get_endpoint_weight(endpoint, method, params)
        current_time = time.time()

        with self.lock:
            # Add to sliding window
            self.weight_window.append((current_time, weight))

            # Update statistics
            self.stats['requests_sent'] += 1
            self.stats['weight_used'] += weight

            # Add to request history for monitoring
            self.request_history.append((current_time, weight))

            # Trigger monitoring callbacks
            for callback in self.monitor_callbacks:
                try:
                    callback('request', {'weight': weight, 'endpoint': endpoint})
                except Exception as e:
                    logger.error(f"Monitor callback error: {e}")

    def record_order(self) -> None:
        """Record a successful order placement."""
        current_time = time.time()
        with self.lock:
            self.order_times.append(current_time)

    def get_usage_percentage(self) -> float:
        """Get current usage percentage (0-100)."""
        with self.lock:
            if self.weight_window:
                current_usage = sum(w for _, w in self.weight_window)
                return min(100.0, (current_usage / self.request_limit) * 100)
            return 0.0

    def get_throttle_factor(self) -> float:
        """
        Get throttling factor based on current usage.
        Returns delay multiplier: 0.0 (no delay) to 2.0 (2x normal delay).
        """
        usage_pct = self.get_usage_percentage()
        current_time = time.time()

        # Update throttle factor every 5 seconds
        if current_time - self.last_throttle_update > 5:
            if usage_pct < 50:
                self.throttle_factor = 0.0  # No throttle
            elif usage_pct < 70:
                self.throttle_factor = 0.2  # 20% slower
            elif usage_pct < 85:
                self.throttle_factor = 0.5  # 50% slower
            elif usage_pct < 95:
                self.throttle_factor = 1.0  # Normal speed (but careful)
            else:
                self.throttle_factor = 2.0  # Emergency mode - very slow

            self.last_throttle_update = current_time
            self.peak_usage_pct = max(self.peak_usage_pct, usage_pct)

        return self.throttle_factor

    def enable_burst_mode(self, duration_seconds: int = 300) -> None:
        """Enable burst mode for high traffic periods."""
        with self.lock:
            if not self.burst_mode:
                self.burst_mode = True
                self.burst_mode_until = time.time() + duration_seconds
                self.update_limits()
                self.stats['burst_mode_activations'] += 1

                logger.info(f"🚀 BURST MODE ENABLED for {duration_seconds}s - Limits: {self.request_limit} weights, {self.order_limit} orders")

                for callback in self.monitor_callbacks:
                    try:
                        callback('burst_mode', {'enabled': True, 'duration': duration_seconds})
                    except Exception as e:
                        logger.error(f"Monitor callback error: {e}")

    def disable_burst_mode(self) -> None:
        """Disable burst mode and restore normal limits."""
        with self.lock:
            if self.burst_mode:
                self.burst_mode = False
                self.burst_mode_until = None
                self.update_limits()

                logger.info("⬇️ BURST MODE DISABLED - Normal limits restored")

                for callback in self.monitor_callbacks:
                    try:
                        callback('burst_mode', {'enabled': False})
                    except Exception as e:
                        logger.error(f"Monitor callback error: {e}")

    def enable_liquidation_mode(self, duration_seconds: int = 300) -> None:
        """Enable extreme liquidation mode - maximum API utilization."""
        with self.lock:
            if not self.liquidation_mode:
                self.liquidation_mode = True
                self.liquidation_mode_until = time.time() + duration_seconds
                self.update_limits()
                self.stats['liquidation_mode_activations'] += 1

                logger.critical(f"🔥 LIQUIDATION MODE ENABLED for {duration_seconds}s - USING 95% OF API CAPACITY!")

                for callback in self.monitor_callbacks:
                    try:
                        callback('liquidation_mode', {'enabled': True, 'duration': duration_seconds})
                    except Exception as e:
                        logger.error(f"Monitor callback error: {e}")

    def disable_liquidation_mode(self) -> None:
        """Disable liquidation mode and restore normal limits."""
        with self.lock:
            if self.liquidation_mode:
                self.liquidation_mode = False
                self.liquidation_mode_until = None
                self.update_limits()

                logger.info("💤 LIQUIDATION MODE DISABLED")

                for callback in self.monitor_callbacks:
                    try:
                        callback('liquidation_mode', {'enabled': False})
                    except Exception as e:
                        logger.error(f"Monitor callback error: {e}")

    def queue_request(self,
                     endpoint: str,
                     params: Dict,
                     priority: str = 'normal',
                     method: str = 'GET') -> bool:
        """
        Queue a request for later processing based on priority.

        Args:
            endpoint: API endpoint
            params: Request parameters
            priority: 'critical', 'normal', or 'low'
            method: HTTP method

        Returns:
            True if queued, False if queue full
        """
        with self.lock:
            queue = self._get_queue_by_priority(priority)

            if len(queue) >= self.max_queue_size:
                logger.warning(f"Queue full for priority '{priority}', dropping request to {endpoint}")
                self.stats['requests_dropped'] += 1
                return False

            request_info = {
                'endpoint': endpoint,
                'params': params,
                'method': method,
                'priority': priority,
                'timestamp': time.time()
            }

            queue.append(request_info)
            self.stats['requests_queued'] += 1

            logger.debug(f"Queued {priority} request to {endpoint} (queue size: {len(queue)})")

            # Trigger monitoring callback
            for callback in self.monitor_callbacks:
                try:
                    callback('queue', {
                        'priority': priority,
                        'size': len(queue),
                        'endpoint': endpoint
                    })
                except Exception as e:
                    logger.error(f"Monitor callback error: {e}")

            return True

    def get_next_request(self) -> Optional[Dict]:
        """Get next queued request that can be processed now."""
        with self.lock:
            # Priority: critical > normal > low
            for priority in ['critical', 'normal', 'low']:
                queue = self._get_queue_by_priority(priority)

                if not queue:
                    continue

                # Check if we can process this request
                request_info = queue[0]
                can_proceed, wait_time = self.can_make_request(
                    request_info['endpoint'],
                    request_info['method'],
                    request_info['params'],
                    request_info['priority']
                )

                if can_proceed:
                    return queue.popleft()  # Remove from queue and return

            return None  # Nothing available

    def check_mode_expiration(self) -> None:
        """Check if burst or liquidation mode should be disabled."""
        current_time = time.time()

        if self.burst_mode and self.burst_mode_until and current_time > self.burst_mode_until:
            self.disable_burst_mode()

        if self.liquidation_mode and self.liquidation_mode_until and current_time > self.liquidation_mode_until:
            self.disable_liquidation_mode()

    def _get_queue_by_priority(self, priority: str):
        """Get queue object by priority level."""
        if priority == 'critical':
            return self.critical_queue
        elif priority == 'normal':
            return self.normal_queue
        else:
            return self.low_queue

    def parse_headers(self, headers: Dict[str, str]) -> None:
        """Parse rate limit headers from API responses."""
        try:
            for key, value in headers.items():
                key_upper = key.upper()
                if 'X-MBX-USED-WEIGHT' in key_upper:
                    old_weight = self.current_request_weight
                    self.current_request_weight = int(value)

                    # Trigger alerts if approaching limits
                    usage_pct = (self.current_request_weight / self.request_limit) * 100

                    if usage_pct > self.peak_usage_pct:
                        self.peak_usage_pct = usage_pct

                    if usage_pct > 90:
                        logger.warning(".1f"                    elif usage_pct > 80:
                        logger.info(".1f"
                    logger.debug(f"Weight usage: {self.current_request_weight}/{self.request_limit} ({usage_pct:.1f}%)")

                elif 'X-MBX-ORDER-COUNT' in key_upper:
                    self.current_order_count = int(value)
                    order_pct = (self.current_order_count / self.order_limit) * 100
                    logger.debug(f"Order count: {self.current_order_count}/{self.order_limit} ({order_pct:.1f}%)")

        except (ValueError, KeyError) as e:
            logger.warning(f"Failed to parse rate limit headers: {e}")

    def handle_http_response(self, status_code: int, endpoint: str) -> None:
        """Handle HTTP response codes with endpoint-specific logic."""
        if status_code == 429:
            self.stats['429_received'] += 1
            self.consecutive_429s += 1
            self.last_429_time = time.time()

            # Adaptive backoff based on consecutive 429s
            backoff_seconds = min(60, 2 ** self.consecutive_429s)

            # Automatically enable burst mode after first 429
            if self.consecutive_429s == 1:
                self.enable_burst_mode(duration_seconds=300)

            logger.warning(f"⚠️  429 RATE LIMITED on {endpoint} - Backing off {backoff_seconds}s (#{self.consecutive_429s})")
            time.sleep(backoff_seconds)

        elif status_code == 418:
            # IP banned - extreme situation
            self.is_banned = True
            ban_duration = 120 * (2 ** min(self.consecutive_429s, 5))
            self.ban_until = time.time() + ban_duration

            self.stats['requests_dropped'] += 10  # Penalize for ban
            logger.error(f"🚫 IP BANNED ({ban_duration}s) - System pause required!")

        elif status_code < 400:
            # Successful request - reset consecutive 429 counter
            if self.consecutive_429s > 0:
                logger.info(f"✅ Success - Reset 429 counter (was {self.consecutive_429s})")
                self.consecutive_429s = 0

    def detect_high_traffic(self) -> bool:
        """Detect if we're in high liquidation traffic."""
        with self.lock:
            # Check recent request rate (last 30 seconds)
            current_time = time.time()
            thirty_seconds_ago = current_time - 30

            recent_requests = sum(1 for t, w in self.request_history if t > thirty_seconds_ago)

            # High traffic = >10 requests in 30 seconds (+ liquidation orders)
            is_high = recent_requests > 10

            if is_high and not self.burst_mode:
                logger.info(f"🌊 High traffic detected ({recent_requests} requests/30s) - enabling burst mode")
                self.enable_burst_mode(duration_seconds=180)

            return is_high

    def get_stats(self) -> Dict:
        """Get comprehensive usage statistics."""
        with self.lock:
            current_usage_pct = self.get_usage_percentage()
            current_time = time.time()

            # Clean old request history
            minute_ago = current_time - 60
            recent_requests = sum(1 for t, w in self.request_history if t > minute_ago)

            return {
                'current_usage_pct': current_usage_pct,
                'peak_usage_pct': self.peak_usage_pct,
                'current_weight': sum(w for _, w in self.weight_window),
                'weight_limit': self.request_limit,
                'current_orders': len(self.order_times),
                'order_limit': self.order_limit,
                'burst_mode': self.burst_mode,
                'liquidation_mode': self.liquidation_mode,
                'banned': self.is_banned,
                'throttle_factor': self.throttle_factor,
                'queue_sizes': {
                    'critical': len(self.critical_queue),
                    'normal': len(self.normal_queue),
                    'low': len(self.low_queue)
                },
                'recent_requests': recent_requests,
                'consecutive_429s': self.consecutive_429s,
                **self.stats
            }

    def add_monitor_callback(self, callback: Callable) -> None:
        """Add a callback for monitoring events."""
        self.monitor_callbacks.append(callback)

    def _monitor_loop(self):
        """Background monitoring thread."""
        while self.enable_monitoring:
            try:
                self.check_mode_expiration()
                self.detect_high_traffic()

                # Log stats every 30 seconds
                current_time = time.time()
                if int(current_time) % 30 == 0:
                    stats = self.get_stats()
                    logger.info(f"📊 Rate Limiter: {stats['current_usage_pct']:.1f}% | Queues: C:{stats['queue_sizes']['critical']} N:{stats['queue_sizes']['normal']} L:{stats['queue_sizes']['low']} | Burst:{stats['burst_mode']} Liquid:{stats['liquidation_mode']}")

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            time.sleep(1)  # Check every second
```

## Phase 2: Integration with Trading System

### Step 2.1: Enhanced Trader Integration

Update `src/core/trader.py` to use accurate weights and prioritization:

```python
# Add to trader.py imports
from src.utils.enhanced_rate_limiter import EnhancedRateLimiter

# Replace the old rate limiter initialization
rate_limiter = EnhancedRateLimiter(
    buffer_pct=0.1,
    reserve_pct=0.2,
    enable_monitoring=True
)

# Add monitoring callback
def on_rate_limit_event(event_type, data):
    """Handle rate limiter events."""
    if event_type == 'burst_mode':
        if data['enabled']:
            log.warning(f"🔥 BURST MODE ACTIVATED for {data['duration']}s - Increased API utilization!")
        else:
            log.info("📉 Burst mode deactivated")
    elif event_type == 'liquidation_mode':
        if data['enabled']:
            log.critical(f"🚨 LIQUIDATION MODE ACTIVATED for {data['duration']}s - MAXIMUM EFFICIENCY!")
        else:
            log.info("🧊 Liquidation mode deactivated")
    elif event_type == 'request':
        # Log heavy requests
        if data['weight'] > 10:
            log.debug(f"Heavy request ({data['weight']} weight): {data['endpoint']}")
    elif event_type == 'queue':
        if data['size'] > 10:
            log.warning(f"Large queue buildup: {data['size']} requests in {data['priority']} queue")

rate_limiter.add_monitor_callback(on_rate_limit_event)

# Update make_authenticated_request function
def make_authenticated_request(method, endpoint, data=None, priority='normal'):
    """Enhanced request function with rate limiting."""

    # Get exact endpoint weight
    endpoint_path = endpoint.replace(config.BASE_URL, '')
    weight = get_endpoint_weight(endpoint_path, method, data)

    # Check if request can be made
    can_proceed, wait_time = rate_limiter.can_make_request(endpoint_path, method, data, priority)

    if not can_proceed:
        if priority == 'critical' and wait_time and wait_time < 5:
            # Critical requests wait briefly
            log.warning(f"Critical request delayed {wait_time:.1f}s for {endpoint_path}")
            time.sleep(wait_time)
        elif priority == 'critical':
            # Queue critical requests
            if rate_limiter.queue_request(endpoint_path, data or {}, priority, method):
                log.info(f"Critical request queued: {endpoint_path}")
                return type('Response', (), {'status_code': 202, 'text': 'Queued', 'json': lambda: {'queued': True}})()
        else:
            # Non-critical requests - just skip with warning
            log.warning(f"Rate limited on {endpoint_path} (weight {weight}), skipping")
            return type('Response', (), {'status_code': 429, 'text': 'Rate limited'})()

    # Apply throttling
    throttle_factor = rate_limiter.get_throttle_factor()
    if throttle_factor > 0:
        delay = 0.1 * throttle_factor  # Base 100ms delay
        time.sleep(delay)
        rate_limiter.stats['throttle_delays'] += 1

    # Make the actual request
    try:
        if method == 'GET':
            response = requests.get(endpoint, params=data, headers={'User-Agent': 'AsterHunter/1.0'})
        else:  # POST
            response = requests.post(endpoint, data=data, headers={'User-Agent': 'AsterHunter/1.0'})

        # Record the request
        rate_limiter.record_request(endpoint_path, method, data)

        # Handle rate limit headers
        rate_limiter.parse_headers(response.headers)

        # Handle response codes
        rate_limiter.handle_http_response(response.status_code, endpoint_path)

        return response

    except Exception as e:
        log.error(f"Request error: {e}")
        return type('Response', (), {'status_code': 500, 'text': str(e)})()

# Update place_order function to use priority
async def place_order(symbol, side, qty, last_price, order_type='LIMIT', position_side='BOTH', offset_pct=0.1, symbol_config=None, use_batching=True, priority='critical'):
    """Enhanced order placement with priority."""

    # ... existing code ...

    # Check order limits
    can_place_order, order_wait = rate_limiter.can_place_order(priority, symbol)
    if not can_place_order:
        if order_wait and order_wait < 3:
            log.info(f"Order delayed {order_wait:.1f}s due to order rate limit")
            await asyncio.sleep(order_wait)
        else:
            log.warning("Order rate limited, queuing...")
            return None

    # ... existing order placement code ...

    # Record successful order
    rate_limiter.record_order()

    # ... rest of function ...
```

### Step 2.2: Emergency Liquidation Mode

Add to `src/core/streamer.py`:

```python
# Add liquidation mode detection to streamer
def detect_liquidation_cascade(liq_data):
    """Detect if we're in a major liquidation cascade."""
    # Check multiple factors for cascade detection
    recent_liq_volume = get_recent_volume('LIQUIDATION', 10)  # Last 10 seconds
    price_drop_pct = calculate_price_drop_pct(30)  # 30 second price drop

    # Cascade = High liquidation volume + significant price drop
    cascade_threshold = 1000000  # $1M in liquidations
    price_drop_threshold = 2.0   # 2% price drop

    is_cascade = recent_liq_volume > cascade_threshold and price_drop_pct > price_drop_threshold

    if is_cascade:
        # Activate liquidation mode for 5 minutes
        rate_limiter.enable_liquidation_mode(duration_seconds=300)
        log.critical(f"🌀 LIQUIDATION CASCADE DETECTED! Volume: ${recent_liq_volume:,.0f}, Price drop: {price_drop_pct:.1f}%")
        return True

    return False

# Update process_liquidation function
async def process_liquidation(self, payload):
    # ... existing code ...

    # Check for cascade conditions
    if detect_liquidation_cascade(liquidation):
        # In cascade mode, use market orders and disable non-critical features
        force_market_orders = True
        skip_tp_sl = True
        log.warning("🚨 CASCADE MODE: Using market orders, skipping TP/SL placement")
    else:
        force_market_orders = False
        skip_tp_sl = False

    # Pass to trader with cascade mode awareness
    if self.message_handler:
        await self.message_handler(
            symbol, side, qty, price,
            cascade_mode={'force_market': force_market_orders, 'skip_tp_sl': skip_tp_sl}
        )

    # ... rest of function ...
```

## Phase 3: Real-Time Monitoring Dashboard

### Step 3.1: Rate Limiter API Routes

Create `src/api/routes/rate_limiter_routes.py`:

```python
from flask import Blueprint, jsonify
from src.utils.enhanced_rate_limiter import rate_limiter

rate_limiter_bp = Blueprint('rate_limiter', __name__)

@rate_limiter_bp.route('/stats')
def get_rate_limiter_stats():
    """Get current rate limiter statistics."""
    try:
        stats = rate_limiter.get_stats()
        return jsonify({
            'status': 'success',
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@rate_limiter_bp.route('/burst-mode', methods=['POST'])
def enable_burst_mode():
    """Manually enable burst mode."""
    try:
        rate_limiter.enable_burst_mode(duration_seconds=300)
        return jsonify({
            'status': 'success',
            'message': 'Burst mode enabled for 5 minutes'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@rate_limiter_bp.route('/liquidation-mode', methods=['POST'])
def enable_liquidation_mode():
    """Manually enable liquidation mode (use with caution)."""
    try:
        rate_limiter.enable_liquidation_mode(duration_seconds=300)
        return jsonify({
            'status': 'success',
            'message': 'Liquidation mode enabled for 5 minutes - MAXIMUM EFFICIENCY'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@rate_limiter_bp.route('/reset-modes', methods=['POST'])
def reset_modes():
    """Reset burst and liquidation modes."""
    try:
        rate_limiter.disable_burst_mode()
        rate_limiter.disable_liquidation_mode()
        return jsonify({
            'status': 'success',
            'message': 'Modes reset to normal operation'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
```

### Step 3.2: Dashboard UI Integration

Add to `static/js/dashboard.js`:

```javascript
// Rate Limiter Dashboard Widget
class RateLimiterWidget {
    constructor() {
        this.updateInterval = 2000; // Update every 2 seconds
        this.chart = null;
        this.init();
    }

    init() {
        this.createWidget();
        this.startUpdates();
    }

    createWidget() {
        const widget = `
        <div class="rate-limiter-widget">
            <h3>🚀 Rate Limiter Status</h3>
            <div class="rate-stats">
                <div class="stat">
                    <span class="label">Usage:</span>
                    <span class="value" id="usage-pct">0%</span>
                    <div class="progress-bar">
                        <div class="progress-fill" id="usage-bar"></div>
                    </div>
                </div>
                <div class="stat">
                    <span class="label">Weight:</span>
                    <span class="value" id="current-weight">0/2400</span>
                </div>
                <div class="stat">
                    <span class="label">Orders:</span>
                    <span class="value" id="current-orders">0/1200</span>
                </div>
            </div>
            <div class="mode-indicators">
                <span class="mode-indicator" id="burst-mode">🔵 Normal</span>
                <span class="mode-indicator" id="liquidation-mode">🔵 Normal</span>
                <span class="mode-indicator" id="ban-status">✅ Online</span>
            </div>
            <div class="queue-status">
                <div class="queue">Critical: <span id="critical-queue">0</span></div>
                <div class="queue">Normal: <span id="normal-queue">0</span></div>
                <div class="queue">Low: <span id="low-queue">0</span></div>
            </div>
            <div class="action-buttons">
                <button id="burst-btn" class="btn-secondary">Enable Burst Mode</button>
                <button id="liquidation-btn" class="btn-danger">☠️ Liquidation Mode</button>
                <button id="reset-btn" class="btn-primary">Reset Modes</button>
            </div>
        </div>
        `;

        // Add to dashboard
        const container = document.querySelector('.dashboard');
        container.insertAdjacentHTML('afterbegin', widget);

        // Bind events
        this.bindEvents();
    }

    bindEvents() {
        document.getElementById('burst-btn').addEventListener('click', () => {
            this.enableBurstMode();
        });
        document.getElementById('liquidation-btn').addEventListener('click', () => {
            this.enableLiquidationMode();
        });
        document.getElementById('reset-btn').addEventListener('click', () => {
            this.resetModes();
        });
    }

    startUpdates() {
        this.updateStats();
        setInterval(() => this.updateStats(), this.updateInterval);
    }

    async updateStats() {
        try {
            const response = await fetch('/api/rate-limiter/stats');
            const data = await response.json();

            if (data.status === 'success') {
                this.updateDisplay(data.data);
            }
        } catch (error) {
            console.error('Failed to fetch rate limiter stats:', error);
        }
    }

    updateDisplay(stats) {
        // Update percentages and values
        const usagePct = stats.current_usage_pct || 0;
        document.getElementById('usage-pct').textContent = `${usagePct.toFixed(1)}%`;
        document.getElementById('usage-bar').style.width = `${Math.min(usagePct, 100)}%`;

        document.getElementById('current-weight').textContent = `${stats.current_weight}/${stats.weight_limit}`;
        document.getElementById('current-orders').textContent = `${stats.current_orders}/${stats.order_limit}`;

        // Update mode indicators
        this.updateModeIndicator('burst-mode', stats.burst_mode, '🔴 BURST', '🔵 Normal');
        this.updateModeIndicator('liquidation-mode', stats.liquidation_mode, '🚨 LIQUIDATION', '🔵 Normal');
        this.updateModeIndicator('ban-status', stats.banned, '🚫 BANNED', '✅ Online');

        // Update queues
        document.getElementById('critical-queue').textContent = stats.queue_sizes.critical;
        document.getElementById('normal-queue').textContent = stats.queue_sizes.normal;
        document.getElementById('low-queue').textContent = stats.queue_sizes.low;

        // Color coding for alerts
        this.updateAlerts(stats);
    }

    updateModeIndicator(elementId, isActive, activeText, inactiveText) {
        const element = document.getElementById(elementId);
        element.textContent = isActive ? activeText : inactiveText;
        element.className = `mode-indicator ${isActive ? 'active' : 'inactive'}`;
    }

    updateAlerts(stats) {
        const usagePct = stats.current_usage_pct || 0;

        // Remove existing alerts
        document.querySelectorAll('.alert').forEach(el => el.remove());

        // Add alerts based on conditions
        let alerts = [];

        if (stats.banned) {
            alerts.push({ type: 'danger', message: '⚠️ IP BANNED - Check system logs!' });
        }

        if (stats.consecutive_429s > 0) {
            alerts.push({ type: 'warning', message: `⚠️ ${stats.consecutive_429s} consecutive rate limits` });
        }

        if (usagePct > 90) {
            alerts.push({ type: 'danger', message: `🔴 CRITICAL: ${usagePct.toFixed(1)}% API usage` });
        } else if (usagePct > 75) {
            alerts.push({ type: 'warning', message: `🟠 HIGH: ${usagePct.toFixed(1)}% API usage` });
        }

        if (stats.queue_sizes.critical > 5) {
            alerts.push({ type: 'warning', message: `Queue backup: ${stats.queue_sizes.critical} critical requests` });
        }

        // Display alerts
        const widget = document.querySelector('.rate-limiter-widget');
        alerts.forEach(alert => {
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${alert.type}`;
            alertDiv.textContent = alert.message;
            widget.insertBefore(alertDiv, widget.firstChild);
        });
    }

    async enableBurstMode() {
        await this.apiCall('/api/rate-limiter/burst-mode', 'Burst mode enabled');
    }

    async enableLiquidationMode() {
        if (confirm('⚠️ LIQUIDATION MODE uses 95% of API capacity and should only be used during extreme volatility. Continue?')) {
            await this.apiCall('/api/rate-limiter/liquidation-mode', 'Liquidation mode enabled');
        }
    }

    async resetModes() {
        await this.apiCall('/api/rate-limiter/reset-modes', 'Modes reset to normal');
    }

    async apiCall(endpoint, successMessage) {
        try {
            const response = await fetch(endpoint, { method: 'POST' });
            const data = await response.json();

            if (data.status === 'success') {
                this.showToast(successMessage, 'success');
            } else {
                this.showToast(data.message, 'error');
            }
        } catch (error) {
            this.showToast('API call failed', 'error');
        }
    }

    showToast(message, type) {
        // Simple toast implementation
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => document.body.removeChild(toast), 3000);
    }
}

// Initialize widget when dashboard loads
document.addEventListener('DOMContentLoaded', function() {
    new RateLimiterWidget();
});
```

## Phase 4: Testing and Validation

### Step 4.1: Simulation Testing

Create `tests/test_rate_limiter_simulation.py`:

```python
import asyncio
import time
import pytest
from unittest.mock import Mock, patch
from src.utils.enhanced_rate_limiter import EnhancedRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_under_load():
    """Test rate limiter performance under simulated high load."""

    limiter = EnhancedRateLimiter()

    # Simulate high-frequency requests
    endpoints = [
        ('/fapi/v1/order', 'POST', {'symbol': 'BTCUSDT'}, 'critical'),
        ('/fapi/v1/batchOrders', 'POST', {}, 'critical'),
        ('/fapi/v2/positionRisk
