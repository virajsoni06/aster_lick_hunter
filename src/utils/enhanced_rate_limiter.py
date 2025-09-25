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

        # ===== MODES =====
        self.burst_mode = False
        self.burst_mode_until = None
        self.liquidation_mode = False
        self.liquidation_mode_until = None

        # ===== NOW SET LIMITS =====
        self.update_limits()

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

    def _get_usage_percentage_unsafe(self) -> float:
        """
        Internal method to get usage percentage without acquiring lock.
        Must be called while holding the lock.
        """
        if self.weight_window:
            current_usage = sum(w for _, w in self.weight_window)
            return min(100.0, (current_usage / self.request_limit) * 100)
        return 0.0

    def get_usage_percentage(self) -> float:
        """Get current usage percentage (0-100)."""
        with self.lock:
            return self._get_usage_percentage_unsafe()

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
                        logger.warning(f"⚠️ CRITICAL: API weight usage at {usage_pct:.1f}%")
                    elif usage_pct > 80:
                        logger.info(f"🟠 HIGH: API weight usage at {usage_pct:.1f}%")

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
            # Use the unsafe version since we're already holding the lock
            current_usage_pct = self._get_usage_percentage_unsafe()
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


# Global instance for backwards compatibility
# Note: Enable monitoring manually if needed via rate_limiter.add_monitor_callback()
rate_limiter = EnhancedRateLimiter(
    buffer_pct=0.1,
    reserve_pct=0.2,
    enable_monitoring=False  # Disabled by default to avoid threading issues in tests/Flask
)
