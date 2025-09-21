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

    def __init__(self, buffer_pct: float = 0.1):
        """
        Initialize rate limiter.

        Args:
            buffer_pct: Safety buffer percentage (0.1 = 10% buffer)
        """
        # Apply safety buffer to limits
        self.request_limit = int(2400 * (1 - buffer_pct))
        self.order_limit = int(1200 * (1 - buffer_pct))

        # Sliding window tracking
        self.request_times = deque()
        self.order_times = deque()

        # Thread safety
        self.lock = Lock()

        # Track current usage from headers
        self.current_request_weight = 0
        self.current_order_count = 0

        # Rate limit violation tracking
        self.last_429_time = None
        self.consecutive_429s = 0
        self.is_banned = False
        self.ban_until = None

        logger.info(f"Rate limiter initialized with limits: requests={self.request_limit}/min, orders={self.order_limit}/min")

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

    def can_make_request(self, weight: int = 1) -> Tuple[bool, Optional[float]]:
        """
        Check if a request can be made based on current limits.

        Args:
            weight: Weight of the request (default 1)

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

            # Clean old entries from sliding window
            current_time = time.time()
            minute_ago = current_time - 60

            # Clean request times
            while self.request_times and self.request_times[0] < minute_ago:
                self.request_times.popleft()

            # Check if we can make the request
            if len(self.request_times) + weight > self.request_limit:
                # Calculate wait time
                if self.request_times:
                    wait_time = 60 - (current_time - self.request_times[0])
                    return False, wait_time
                return False, 0

            return True, None

    def can_place_order(self) -> Tuple[bool, Optional[float]]:
        """
        Check if an order can be placed based on order rate limits.

        Returns:
            Tuple of (can_place_order, wait_time_seconds)
        """
        with self.lock:
            # Clean old entries from sliding window
            current_time = time.time()
            minute_ago = current_time - 60

            # Clean order times
            while self.order_times and self.order_times[0] < minute_ago:
                self.order_times.popleft()

            # Check if we can place the order
            if len(self.order_times) >= self.order_limit:
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

    def record_order(self) -> None:
        """
        Record that an order was placed.
        """
        with self.lock:
            self.order_times.append(time.time())

    def wait_if_needed(self, is_order: bool = False) -> None:
        """
        Wait if rate limits require it.

        Args:
            is_order: True if placing an order, False for regular request
        """
        if is_order:
            can_proceed, wait_time = self.can_place_order()
        else:
            can_proceed, wait_time = self.can_make_request()

        if not can_proceed and wait_time:
            logger.info(f"Rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)

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
                'consecutive_429s': self.consecutive_429s
            }