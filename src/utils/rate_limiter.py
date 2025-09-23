"""
Rate limiter for Aster API requests and order placement.
Tracks both REQUEST_WEIGHT and ORDER rate limits.
"""

import time
import logging
from typing import Dict, Optional, Tuple
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Manages API rate limits for Aster exchange.

    Limits from documentation:
    - REQUEST_WEIGHT: 2400 per minute
    - ORDERS: 1200 per minute
    """

    def __init__(self, buffer_pct: float = 0.1, reserve_pct: float = 0.2):
        """
        Initialize rate limiter.

        Args:
            buffer_pct: Safety buffer percentage (0.1 = 10% buffer)
            reserve_pct: Reserved capacity for critical requests (0.2 = 20% reserved)
        """
        # Store initial settings
        self.initial_buffer_pct = buffer_pct
        self.initial_reserve_pct = reserve_pct

        # Apply safety buffer to limits
        self.request_limit = int(2400 * (1 - buffer_pct))
        self.order_limit = int(1200 * (1 - buffer_pct))

        # Burst mode settings
        self.burst_mode = False
        self.burst_mode_until = None
        self.burst_buffer_pct = 0.05  # Only 5% buffer in burst mode
        self.burst_reserve_pct = 0.1  # Only 10% reserve in burst mode

        # Reserve capacity for critical requests
        self.reserve_pct = reserve_pct
        self.reserved_request_capacity = int(self.request_limit * reserve_pct)
        self.reserved_order_capacity = int(self.order_limit * reserve_pct)
        self.normal_request_limit = self.request_limit - self.reserved_request_capacity
        self.normal_order_limit = self.order_limit - self.reserved_order_capacity

        # Sliding window tracking
        self.request_times = deque()
        self.order_times = deque()

        # Thread safety
        self.lock = Lock()

        # Track current usage from headers (None initially, set after first parse)
        self.current_request_weight = None
        self.current_order_count = None

        # Rate limit violation tracking
        self.last_429_time = None
        self.consecutive_429s = 0
        self.is_banned = False
        self.ban_until = None

        # Queue management for deferred requests
        self.request_queue = deque()
        self.order_queue = deque()
        self.max_queue_size = 100

        # High traffic detection
        self.recent_request_times = deque(maxlen=100)
        self.high_traffic_threshold = 50  # requests per 10 seconds

        logger.info(f"Rate limiter initialized with limits: requests={self.request_limit}/min (normal={self.normal_request_limit}, reserved={self.reserved_request_capacity}), orders={self.order_limit}/min")

    def parse_headers(self, headers: Dict[str, str]) -> None:
        """
        Parse rate limit headers from API response.

        Headers format:
        - X-MBX-USED-WEIGHT-1M: current request weight used
        - X-MBX-ORDER-COUNT-1M: current order count
        """
        try:
            # Parse request weight
            for key, value in headers.items():
                if 'X-MBX-USED-WEIGHT' in key.upper():
                    self.current_request_weight = int(value)
                    logger.debug(f"Current request weight: {self.current_request_weight}/{self.request_limit}")

                elif 'X-MBX-ORDER-COUNT' in key.upper():
                    self.current_order_count = int(value)
                    logger.debug(f"Current order count: {self.current_order_count}/{self.order_limit}")

        except (ValueError, KeyError) as e:
            logger.warning(f"Failed to parse rate limit headers: {e}")

    def handle_http_response(self, status_code: int) -> None:
        """
        Handle HTTP response codes for rate limiting.

        Args:
            status_code: HTTP status code from response
        """
        if status_code == 429:
            # Rate limit exceeded
            self.consecutive_429s += 1
            self.last_429_time = time.time()

            # Calculate backoff time
            backoff_seconds = min(60, 2 ** self.consecutive_429s)
            logger.warning(f"Rate limit exceeded (429). Backing off for {backoff_seconds}s")

            time.sleep(backoff_seconds)

        elif status_code == 418:
            # IP banned
            self.is_banned = True
            # Default ban duration: start with 2 minutes
            ban_duration = 120
            self.ban_until = time.time() + ban_duration

            logger.error(f"IP banned (418). Ban expires at {time.ctime(self.ban_until)}")

        elif status_code < 400:
            # Successful request, reset consecutive 429 counter
            self.consecutive_429s = 0

    def can_make_request(self, weight: int = 1, priority: str = 'normal') -> Tuple[bool, Optional[float]]:
        """
        Check if a request can be made based on current limits.

        Args:
            weight: Weight of the request (default 1)
            priority: 'critical' or 'normal' - critical bypasses reserved limits

        Returns:
            Tuple of (can_make_request, wait_time_seconds)
        """
        with self.lock:
            # Check if banned
            if self.is_banned:
                if self.ban_until and time.time() < self.ban_until:
                    wait_time = self.ban_until - time.time()
                    return False, wait_time
                else:
                    # Ban expired
                    self.is_banned = False
                    self.ban_until = None

            # If we have header-based usage, use it first for more accuracy
            if self.current_request_weight is not None:
                effective_limit = self.request_limit if priority == 'critical' else self.normal_request_limit
                if self.current_request_weight + weight > effective_limit:
                    # Conservatively wait 1 second since we don't have exact time
                    logger.debug(f"Header-based usage {self.current_request_weight} + {weight} would exceed {effective_limit}")
                    return False, 1.0
                else:
                    logger.debug(f"Header shows {self.current_request_weight}, allowing request with weight {weight}")
                    return True, None

            # Fall back to local sliding window tracking
            # Clean old entries from sliding window
            current_time = time.time()
            minute_ago = current_time - 60

            # Clean request times
            while self.request_times and self.request_times[0] < minute_ago:
                self.request_times.popleft()

            # Effective limit based on priority
            effective_limit = self.request_limit if priority == 'critical' else self.normal_request_limit

            # Check if we can make the request
            if len(self.request_times) + weight > effective_limit:
                # Calculate wait time
                if self.request_times:
                    wait_time = 60 - (current_time - self.request_times[0])
                    return False, wait_time
                return False, 0

            return True, None

    def can_place_order(self, priority: str = 'normal') -> Tuple[bool, Optional[float]]:
        """
        Check if an order can be placed based on order rate limits.

        Args:
            priority: 'critical' or 'normal' - critical bypasses reserved limits

        Returns:
            Tuple of (can_place_order, wait_time_seconds)
        """
        with self.lock:
            # Check if banned
            if self.is_banned:
                if self.ban_until and time.time() < self.ban_until:
                    wait_time = self.ban_until - time.time()
                    return False, wait_time
                else:
                    # Ban expired
                    self.is_banned = False
                    self.ban_until = None

            # If we have header-based usage, use it first for more accuracy
            if self.current_order_count is not None:
                effective_limit = self.order_limit if priority == 'critical' else self.normal_order_limit
                if self.current_order_count >= effective_limit:
                    logger.debug(f"Header-based order count {self.current_order_count} >= {effective_limit}")
                    return False, 1.0
                else:
                    logger.debug(f"Header shows {self.current_order_count} orders, allowing")
                    return True, None

            # Fall back to local sliding window tracking
            # Clean old entries from sliding window
            current_time = time.time()
            minute_ago = current_time - 60

            # Clean order times
            while self.order_times and self.order_times[0] < minute_ago:
                self.order_times.popleft()

            # Effective limit based on priority
            effective_limit = self.order_limit if priority == 'critical' else self.normal_order_limit

            # Check if we can place the order
            if len(self.order_times) >= effective_limit:
                # Calculate wait time
                if self.order_times:
                    wait_time = 60 - (current_time - self.order_times[0])
                    return False, wait_time
                return False, 0

            return True, None

    def record_request(self, weight: int = 1) -> None:
        """
        Record that a request was made.

        Args:
            weight: Weight of the request
        """
        with self.lock:
            current_time = time.time()
            for _ in range(weight):
                self.request_times.append(current_time)

            # Check for high traffic
            self.detect_high_traffic()

    def record_order(self) -> None:
        """
        Record that an order was placed.
        """
        with self.lock:
            self.order_times.append(time.time())

    def wait_if_needed(self, is_order: bool = False, priority: str = 'normal') -> None:
        """
        Wait if rate limits require it.

        Args:
            is_order: True if placing an order, False for regular request
            priority: 'critical' or 'normal' for effective limits
        """
        if is_order:
            can_proceed, wait_time = self.can_place_order(priority)
        else:
            can_proceed, wait_time = self.can_make_request(priority=priority)

        if not can_proceed and wait_time:
            logger.info(f"Rate limit reached (priority:{priority}). Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)

    def detect_high_traffic(self) -> bool:
        """
        Detect if we're in a high traffic situation.

        Returns:
            True if traffic is high, False otherwise
        """
        current_time = time.time()
        self.recent_request_times.append(current_time)

        # Count requests in last 10 seconds
        ten_seconds_ago = current_time - 10
        recent_count = sum(1 for t in self.recent_request_times if t > ten_seconds_ago)

        is_high = recent_count >= self.high_traffic_threshold

        # Auto-enable burst mode if traffic is high and not already enabled
        if is_high and not self.burst_mode:
            logger.info(f"High traffic detected: {recent_count} requests in 10s")
            self.enable_burst_mode(duration_seconds=60)

        return is_high

    def enable_burst_mode(self, duration_seconds: int = 60) -> None:
        """
        Enable burst mode for handling high liquidation traffic.

        Args:
            duration_seconds: Duration to maintain burst mode
        """
        with self.lock:
            self.burst_mode = True
            self.burst_mode_until = time.time() + duration_seconds

            # Increase limits for burst mode
            self.request_limit = int(2400 * (1 - self.burst_buffer_pct))
            self.order_limit = int(1200 * (1 - self.burst_buffer_pct))

            # Reduce reserved capacity during burst
            self.reserved_request_capacity = int(self.request_limit * self.burst_reserve_pct)
            self.reserved_order_capacity = int(self.order_limit * self.burst_reserve_pct)
            self.normal_request_limit = self.request_limit - self.reserved_request_capacity
            self.normal_order_limit = self.order_limit - self.reserved_order_capacity

            logger.info(f"BURST MODE ENABLED for {duration_seconds}s. Limits: requests={self.request_limit}, orders={self.order_limit}")

    def disable_burst_mode(self) -> None:
        """
        Disable burst mode and restore normal limits.
        """
        with self.lock:
            self.burst_mode = False
            self.burst_mode_until = None

            # Restore normal limits
            self.request_limit = int(2400 * (1 - self.initial_buffer_pct))
            self.order_limit = int(1200 * (1 - self.initial_buffer_pct))

            # Restore normal reserved capacity
            self.reserved_request_capacity = int(self.request_limit * self.initial_reserve_pct)
            self.reserved_order_capacity = int(self.order_limit * self.initial_reserve_pct)
            self.normal_request_limit = self.request_limit - self.reserved_request_capacity
            self.normal_order_limit = self.order_limit - self.reserved_order_capacity

            logger.info("BURST MODE DISABLED. Restored normal rate limits.")

    def check_burst_mode(self) -> None:
        """
        Check if burst mode should be disabled.
        """
        if self.burst_mode and self.burst_mode_until:
            if time.time() > self.burst_mode_until:
                self.disable_burst_mode()

    def queue_request(self, request_info: Dict, is_order: bool = False, priority: str = 'normal') -> bool:
        """
        Queue a request for later processing.

        Args:
            request_info: Information about the request
            is_order: Whether this is an order request
            priority: Request priority level

        Returns:
            True if queued successfully, False if queue is full
        """
        with self.lock:
            queue = self.order_queue if is_order else self.request_queue

            if len(queue) >= self.max_queue_size:
                logger.warning(f"{'Order' if is_order else 'Request'} queue full ({self.max_queue_size} items)")
                return False

            # Add with priority sorting
            queue_item = {
                'info': request_info,
                'timestamp': time.time(),
                'priority': priority,
                'is_order': is_order
            }

            # Insert based on priority
            if priority == 'critical':
                queue.appendleft(queue_item)
            else:
                queue.append(queue_item)

            logger.debug(f"Queued {'order' if is_order else 'request'} with priority '{priority}'. Queue size: {len(queue)}")
            return True

    def get_queued_request(self, is_order: bool = False) -> Optional[Dict]:
        """
        Get next queued request if rate limits allow.

        Args:
            is_order: Whether to get from order queue

        Returns:
            Request info if available and rate limits allow
        """
        with self.lock:
            self.check_burst_mode()

            queue = self.order_queue if is_order else self.request_queue

            if not queue:
                return None

            # Check if we can process the request
            next_item = queue[0]
            priority = next_item.get('priority', 'normal')

            if is_order:
                can_proceed, _ = self.can_place_order(priority=priority)
            else:
                can_proceed, _ = self.can_make_request(weight=1, priority=priority)

            if can_proceed:
                return queue.popleft()

            return None

    def process_queue(self) -> int:
        """
        Process queued requests that can be sent now.

        Returns:
            Number of requests processed
        """
        processed = 0

        # Process order queue
        while True:
            item = self.get_queued_request(is_order=True)
            if not item:
                break
            processed += 1
            logger.debug(f"Processing queued order: {item['info'].get('symbol', 'unknown')}")

        # Process request queue
        while True:
            item = self.get_queued_request(is_order=False)
            if not item:
                break
            processed += 1
            logger.debug("Processing queued request")

        return processed

    def get_usage_stats(self) -> Dict[str, any]:
        """
        Get current usage statistics.

        Returns:
            Dictionary with usage stats
        """
        with self.lock:
            current_time = time.time()
            minute_ago = current_time - 60

            # Count recent requests
            recent_requests = sum(1 for t in self.request_times if t >= minute_ago)
            recent_orders = sum(1 for t in self.order_times if t >= minute_ago)

            return {
                'request_count': recent_requests,
                'request_limit': self.request_limit,
                'request_usage_pct': (recent_requests / self.request_limit * 100) if self.request_limit > 0 else 0,
                'order_count': recent_orders,
                'order_limit': self.order_limit,
                'order_usage_pct': (recent_orders / self.order_limit * 100) if self.order_limit > 0 else 0,
                'is_banned': self.is_banned,
                'ban_until': self.ban_until,
                'consecutive_429s': self.consecutive_429s,
                'burst_mode': self.burst_mode,
                'burst_mode_until': self.burst_mode_until,
                'request_queue_size': len(self.request_queue),
                'order_queue_size': len(self.order_queue)
            }
