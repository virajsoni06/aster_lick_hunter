"""
Unit tests for the Rate Limiter utility.
Tests token bucket algorithm, endpoint weights, and rate limit handling.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import concurrent.futures

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.utils.rate_limiter import RateLimiter
from src.utils.endpoint_weights import ENDPOINT_WEIGHTS


class TestRateLimiter:
    """Test suite for RateLimiter functionality."""

    @pytest.fixture
    def rate_limiter(self):
        """Create a rate limiter instance for testing."""
        limiter = RateLimiter(
            weight_limit=1200,
            time_window=60,
            buffer_percent=10
        )
        return limiter

    @pytest.mark.unit
    def test_initialization(self, rate_limiter):
        """Test rate limiter initialization."""
        assert rate_limiter.weight_limit == 1200
        assert rate_limiter.time_window == 60
        assert rate_limiter.effective_limit == 1080  # 1200 * 0.9
        assert rate_limiter.tokens == 1080
        assert rate_limiter.max_tokens == 1080

    @pytest.mark.unit
    def test_token_consumption(self, rate_limiter):
        """Test token consumption for requests."""
        # Consume tokens for order placement
        success = rate_limiter.acquire('/fapi/v1/order', method='POST')
        assert success == True
        assert rate_limiter.tokens == 1076  # 1080 - 4 (order weight)

        # Consume tokens for orderbook
        success = rate_limiter.acquire('/fapi/v1/depth')
        assert success == True
        assert rate_limiter.tokens == 1071  # 1076 - 5 (depth weight)

    @pytest.mark.unit
    def test_token_refill(self, rate_limiter):
        """Test token refill over time."""
        # Consume some tokens
        rate_limiter.tokens = 500

        # Mock time passing
        with patch('time.time') as mock_time:
            # Initial time
            mock_time.return_value = 1000.0
            rate_limiter.last_refill = 1000.0

            # 30 seconds later
            mock_time.return_value = 1030.0
            rate_limiter._refill_tokens()

            # Should refill: (30/60) * 1080 = 540 tokens
            assert rate_limiter.tokens == 1040  # 500 + 540

            # Another 30 seconds (would exceed max)
            mock_time.return_value = 1060.0
            rate_limiter._refill_tokens()

            # Should cap at max_tokens
            assert rate_limiter.tokens == 1080

    @pytest.mark.unit
    def test_rate_limit_rejection(self, rate_limiter):
        """Test request rejection when rate limited."""
        # Consume all tokens
        rate_limiter.tokens = 2

        # Try expensive operation
        success = rate_limiter.acquire('/fapi/v1/exchangeInfo')  # Weight: 10

        assert success == False  # Should be rejected
        assert rate_limiter.tokens == 2  # Tokens unchanged

    @pytest.mark.unit
    def test_endpoint_weight_lookup(self, rate_limiter):
        """Test endpoint weight resolution."""
        # Test exact match
        weight = rate_limiter.get_endpoint_weight('/fapi/v1/order', 'POST')
        assert weight == 4

        # Test pattern match
        weight = rate_limiter.get_endpoint_weight('/fapi/v1/order/12345', 'DELETE')
        assert weight == 1

        # Test default weight
        weight = rate_limiter.get_endpoint_weight('/unknown/endpoint')
        assert weight == 1

    @pytest.mark.unit
    def test_wait_for_tokens(self, rate_limiter):
        """Test waiting for token availability."""
        rate_limiter.tokens = 0
        rate_limiter.refill_rate = 18  # tokens per second

        with patch('time.sleep') as mock_sleep:
            with patch('time.time', return_value=1000.0):
                # Request needs 4 tokens
                rate_limiter.wait_for_tokens(4)

                # Should sleep for: 4 tokens / 18 tokens per sec ≈ 0.22 sec
                mock_sleep.assert_called()
                sleep_time = mock_sleep.call_args[0][0]
                assert 0.2 <= sleep_time <= 0.3

    @pytest.mark.unit
    def test_concurrent_requests(self, rate_limiter):
        """Test thread safety with concurrent requests."""
        results = []
        rate_limiter.tokens = 100

        def make_request():
            return rate_limiter.acquire('/fapi/v1/order', 'GET')  # Weight: 2

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(50)]
            results = [f.result() for f in futures]

        # Should have some successful and some failed
        successes = sum(1 for r in results if r)
        failures = sum(1 for r in results if not r)

        assert successes > 0
        assert failures > 0
        assert successes + failures == 50
        # Maximum successes: 100 tokens / 2 weight = 50 requests
        assert successes <= 50

    @pytest.mark.unit
    def test_reset_tokens(self, rate_limiter):
        """Test manual token reset."""
        rate_limiter.tokens = 100

        rate_limiter.reset()

        assert rate_limiter.tokens == rate_limiter.max_tokens

    @pytest.mark.unit
    def test_get_wait_time(self, rate_limiter):
        """Test calculation of wait time for tokens."""
        rate_limiter.tokens = 10
        rate_limiter.refill_rate = 18

        # Need 20 tokens, have 10, need 10 more
        wait_time = rate_limiter.get_wait_time(20)

        # 10 tokens / 18 tokens per sec ≈ 0.56 sec
        assert 0.5 <= wait_time <= 0.6

    @pytest.mark.unit
    def test_buffer_percentage(self):
        """Test buffer percentage configuration."""
        # Create limiter with 20% buffer
        limiter = RateLimiter(weight_limit=1000, buffer_percent=20)

        assert limiter.weight_limit == 1000
        assert limiter.effective_limit == 800  # 1000 * 0.8

    @pytest.mark.unit
    def test_dynamic_endpoint_weights(self):
        """Test dynamic endpoint weight calculation."""
        limiter = RateLimiter()

        # Test batch orders weight calculation
        weight = limiter.get_endpoint_weight('/fapi/v1/batchOrders', 'POST', batch_size=5)
        assert weight == 25  # 5 * 5

        # Test with parameters
        weight = limiter.get_endpoint_weight('/fapi/v1/klines', params={'limit': 1000})
        assert weight == 10  # Higher weight for large limit


class TestRateLimiterIntegration:
    """Integration tests for rate limiter with real timing."""

    @pytest.mark.unit
    def test_token_refill_real_time(self):
        """Test token refill with real time passing."""
        limiter = RateLimiter(weight_limit=120, time_window=1)  # Fast for testing
        limiter.tokens = 0

        # Wait for refill
        time.sleep(0.5)
        limiter._refill_tokens()

        # Should have refilled approximately half
        assert 50 <= limiter.tokens <= 70

        # Wait for full refill
        time.sleep(0.6)
        limiter._refill_tokens()

        # Should be at max
        assert limiter.tokens == 108  # 120 * 0.9

    @pytest.mark.unit
    def test_burst_protection(self):
        """Test protection against burst requests."""
        limiter = RateLimiter(weight_limit=100, burst_size=20)

        # Make burst of requests
        successes = 0
        for _ in range(30):
            if limiter.acquire('/fapi/v1/order', 'GET'):  # Weight: 2
                successes += 1

        # Should limit burst
        assert successes <= 10  # 20 burst tokens / 2 weight

    @pytest.mark.unit
    def test_per_ip_tracking(self):
        """Test per-IP rate limit tracking."""
        limiter = RateLimiter()

        # Track different IPs
        limiter.track_ip_request('192.168.1.1', 10)
        limiter.track_ip_request('192.168.1.1', 20)
        limiter.track_ip_request('192.168.1.2', 15)

        assert limiter.get_ip_usage('192.168.1.1') == 30
        assert limiter.get_ip_usage('192.168.1.2') == 15


class TestEndpointWeights:
    """Test endpoint weight configurations."""

    @pytest.mark.unit
    def test_all_endpoints_covered(self):
        """Test that all major endpoints have weights defined."""
        critical_endpoints = [
            '/fapi/v1/order',
            '/fapi/v1/depth',
            '/fapi/v1/exchangeInfo',
            '/fapi/v1/klines',
            '/fapi/v1/account',
            '/fapi/v1/positionRisk'
        ]

        for endpoint in critical_endpoints:
            # Remove any parameters
            base_endpoint = endpoint.split('?')[0]
            # Check if endpoint or pattern exists
            found = False
            for pattern in ENDPOINT_WEIGHTS.keys():
                if base_endpoint in pattern or pattern in base_endpoint:
                    found = True
                    break
            assert found, f"No weight defined for {endpoint}"

    @pytest.mark.unit
    def test_weight_values_reasonable(self):
        """Test that weight values are within reasonable range."""
        for endpoint, weight in ENDPOINT_WEIGHTS.items():
            if isinstance(weight, dict):
                for method_weight in weight.values():
                    assert 1 <= method_weight <= 50, f"Unreasonable weight for {endpoint}"
            else:
                assert 1 <= weight <= 50, f"Unreasonable weight for {endpoint}"


class TestRateLimiterErrorHandling:
    """Test error handling in rate limiter."""

    @pytest.mark.unit
    def test_negative_weight_handling(self):
        """Test handling of negative weight values."""
        limiter = RateLimiter()

        # Should treat negative as minimum weight
        success = limiter.acquire('/test', weight=-5)

        assert limiter.tokens < limiter.max_tokens  # Some tokens consumed

    @pytest.mark.unit
    def test_overflow_protection(self):
        """Test protection against token overflow."""
        limiter = RateLimiter()
        limiter.tokens = limiter.max_tokens

        # Try to add more tokens
        with patch('time.time') as mock_time:
            mock_time.return_value = 10000.0
            limiter.last_refill = 0  # Very old

            limiter._refill_tokens()

            # Should not exceed max
            assert limiter.tokens == limiter.max_tokens

    @pytest.mark.unit
    def test_thread_safety_stress(self):
        """Stress test thread safety."""
        limiter = RateLimiter(weight_limit=10000)
        errors = []

        def stress_test():
            try:
                for _ in range(100):
                    limiter.acquire('/fapi/v1/order', 'POST')
                    limiter._refill_tokens()
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=stress_test)
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        # Should complete without errors
        assert len(errors) == 0
        # Tokens should be valid
        assert 0 <= limiter.tokens <= limiter.max_tokens