"""
Service Coordinator - Orchestrates startup sequence and manages service dependencies.
Ensures services are initialized in the correct order with shared state.
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
from src.utils.auth import make_authenticated_request
from src.utils.config import config
from src.utils.state_manager import get_state_manager
from src.utils.utils import log

logger = log

class ServiceStatus(Enum):
    """Service status enumeration."""
    NOT_STARTED = "not_started"
    INITIALIZING = "initializing"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"

@dataclass
class ServiceInfo:
    """Information about a service."""
    name: str
    status: ServiceStatus
    dependencies: List[str]
    start_time: Optional[float] = None
    error: Optional[str] = None
    instance: Optional[Any] = None

class ServiceCoordinator:
    """
    Coordinates the startup and shutdown of services in the trading bot.
    Ensures proper initialization order and shared state management.
    """

    def __init__(self):
        """Initialize the service coordinator."""
        self.services: Dict[str, ServiceInfo] = {}
        self.shared_state: Dict[str, Any] = {}
        self.startup_complete = False
        self.state_manager = get_state_manager()

        # Health check results
        self.health_checks: Dict[str, Dict] = {}

        logger.info("ServiceCoordinator initialized")

    def register_service(self, name: str, dependencies: List[str] = None):
        """
        Register a service with its dependencies.

        Args:
            name: Service name
            dependencies: List of service names this service depends on
        """
        self.services[name] = ServiceInfo(
            name=name,
            status=ServiceStatus.NOT_STARTED,
            dependencies=dependencies or []
        )
        logger.debug(f"Registered service '{name}' with dependencies: {dependencies}")

    async def fetch_exchange_state(self) -> Dict[str, Any]:
        """
        Fetch all exchange state data once at startup.
        This prevents multiple services from making the same API calls.

        Returns:
            Dictionary containing exchange state data
        """
        logger.info("Fetching initial exchange state...")
        state = {}

        try:
            # Fetch account info
            logger.debug("Fetching account info...")
            response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v2/account")
            if response.status_code == 200:
                state['account'] = response.json()
                logger.debug(f"Account balance: {state['account'].get('totalWalletBalance', 0)} USDT")
            else:
                logger.warning(f"Failed to fetch account info: {response.status_code}")
                state['account'] = None

            # Fetch positions
            logger.debug("Fetching positions...")
            response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v2/positionRisk")
            if response.status_code == 200:
                positions = response.json()
                state['positions'] = positions

                # Process positions for state manager
                for pos in positions:
                    amt = float(pos.get('positionAmt', 0))
                    if amt != 0:
                        symbol = pos['symbol']
                        side = 'LONG' if amt > 0 else 'SHORT'
                        entry_price = float(pos.get('entryPrice', 0))
                        mark_price = float(pos.get('markPrice', 0))

                        # Update state manager
                        self.state_manager.update_position(
                            symbol, side, abs(amt), entry_price, mark_price
                        )

                active_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
                logger.debug(f"Found {len(active_positions)} active positions")
            else:
                logger.warning(f"Failed to fetch positions: {response.status_code}")
                state['positions'] = []

            # Fetch open orders
            logger.debug("Fetching open orders...")
            response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/openOrders")
            if response.status_code == 200:
                orders = response.json()
                state['open_orders'] = orders

                # Track orders in state manager
                for order in orders:
                    order_id = str(order['orderId'])
                    symbol = order['symbol']
                    order_type = order.get('type', 'UNKNOWN')
                    status = order.get('status', 'NEW')

                    self.state_manager.track_order(order_id, symbol, order_type, status)

                logger.debug(f"Found {len(orders)} open orders")
            else:
                logger.warning(f"Failed to fetch open orders: {response.status_code}")
                state['open_orders'] = []

            # Fetch exchange info for symbols we're trading
            if config.SYMBOL_SETTINGS:
                logger.debug("Fetching exchange info for configured symbols...")
                response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/exchangeInfo")
                if response.status_code == 200:
                    exchange_info = response.json()
                    symbols_info = {}

                    for sym_info in exchange_info.get('symbols', []):
                        if sym_info['symbol'] in config.SYMBOL_SETTINGS:
                            symbols_info[sym_info['symbol']] = sym_info

                    state['symbols_info'] = symbols_info
                    logger.debug(f"Fetched info for {len(symbols_info)} symbols")
                else:
                    logger.warning(f"Failed to fetch exchange info: {response.status_code}")
                    state['symbols_info'] = {}

            # Store in shared state
            self.shared_state['exchange_state'] = state
            logger.info(f"Exchange state fetched successfully: "
                       f"{len(state.get('positions', []))} positions, "
                       f"{len(state.get('open_orders', []))} orders")

            return state

        except Exception as e:
            logger.error(f"Error fetching exchange state: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    async def run_health_checks(self) -> Dict[str, Dict]:
        """
        Run health checks before starting services.

        Returns:
            Dictionary of health check results
        """
        logger.info("Running startup health checks...")
        checks = {}

        # Check database connection
        try:
            from src.database.db import get_db_conn
            conn = get_db_conn()
            conn.execute("SELECT 1")
            conn.close()
            checks['database'] = {'status': 'healthy', 'message': 'Database accessible'}
            logger.success("Database health check: OK")
        except Exception as e:
            checks['database'] = {'status': 'unhealthy', 'error': str(e)}
            logger.error(f"Database health check failed: {e}")

        # Check API connectivity
        try:
            response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/ping")
            if response.status_code == 200:
                checks['api_connection'] = {'status': 'healthy', 'message': 'API reachable'}
                logger.success("API connectivity check: OK")
            else:
                checks['api_connection'] = {'status': 'unhealthy', 'error': f"Status {response.status_code}"}
                logger.error(f"API connectivity check failed: {response.status_code}")
        except Exception as e:
            checks['api_connection'] = {'status': 'unhealthy', 'error': str(e)}
            logger.error(f"API connectivity check failed: {e}")

        # Check position mode settings
        try:
            response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/positionSide/dual")
            if response.status_code == 200:
                dual_side = response.json().get('dualSidePosition', False)
                expected = config.GLOBAL_SETTINGS.get('hedge_mode', False)

                if dual_side == expected:
                    checks['position_mode'] = {
                        'status': 'healthy',
                        'message': f"Position mode correct (hedge_mode={expected})"
                    }
                    logger.success(f"Position mode check: OK (hedge_mode={expected})")
                else:
                    checks['position_mode'] = {
                        'status': 'warning',
                        'message': f"Position mode mismatch: exchange={dual_side}, config={expected}"
                    }
                    logger.warning(f"Position mode mismatch: exchange={dual_side}, config={expected}")
            else:
                checks['position_mode'] = {'status': 'unhealthy', 'error': f"Status {response.status_code}"}
        except Exception as e:
            checks['position_mode'] = {'status': 'unhealthy', 'error': str(e)}
            logger.error(f"Position mode check failed: {e}")

        # Check for orphaned orders
        open_orders = self.shared_state.get('exchange_state', {}).get('open_orders', [])
        positions = self.shared_state.get('exchange_state', {}).get('positions', [])

        active_symbols = set()
        for pos in positions:
            if float(pos.get('positionAmt', 0)) != 0:
                active_symbols.add(pos['symbol'])

        orphaned_orders = []
        for order in open_orders:
            if order['symbol'] not in active_symbols:
                if order.get('type') in ['STOP_MARKET', 'TAKE_PROFIT_MARKET', 'LIMIT']:
                    if order.get('reduceOnly', False):
                        orphaned_orders.append(order)

        if orphaned_orders:
            checks['orphaned_orders'] = {
                'status': 'warning',
                'message': f"Found {len(orphaned_orders)} orphaned orders",
                'orders': [{'symbol': o['symbol'], 'type': o['type'], 'id': o['orderId']}
                          for o in orphaned_orders[:5]]  # Show first 5
            }
            logger.warning(f"Found {len(orphaned_orders)} orphaned orders that may need cleanup")
        else:
            checks['orphaned_orders'] = {'status': 'healthy', 'message': 'No orphaned orders found'}
            logger.success("Orphaned orders check: OK")

        self.health_checks = checks

        # Log summary
        healthy = sum(1 for c in checks.values() if c['status'] == 'healthy')
        warnings = sum(1 for c in checks.values() if c['status'] == 'warning')
        unhealthy = sum(1 for c in checks.values() if c['status'] == 'unhealthy')

        logger.info(f"Health check summary: {healthy} healthy, {warnings} warnings, {unhealthy} unhealthy")

        return checks

    async def initialize_service(self, service_name: str, init_func: Callable, *args, **kwargs) -> bool:
        """
        Initialize a single service.

        Args:
            service_name: Name of the service
            init_func: Initialization function to call
            *args, **kwargs: Arguments to pass to init function

        Returns:
            True if initialization successful
        """
        service = self.services.get(service_name)
        if not service:
            logger.error(f"Service '{service_name}' not registered")
            return False

        # Check dependencies
        for dep in service.dependencies:
            dep_service = self.services.get(dep)
            if not dep_service or dep_service.status != ServiceStatus.RUNNING:
                logger.error(f"Dependency '{dep}' not running for service '{service_name}'")
                service.status = ServiceStatus.FAILED
                service.error = f"Dependency '{dep}' not available"
                return False

        try:
            service.status = ServiceStatus.INITIALIZING
            service.start_time = time.time()
            logger.info(f"Initializing service '{service_name}'...")

            # Pass shared state to initialization if requested
            if 'shared_state' in kwargs:
                kwargs['shared_state'] = self.shared_state

            # Call initialization function
            result = await init_func(*args, **kwargs)

            service.instance = result
            service.status = ServiceStatus.RUNNING

            init_time = time.time() - service.start_time
            logger.success(f"Service '{service_name}' initialized successfully ({init_time:.2f}s)")

            return True

        except Exception as e:
            service.status = ServiceStatus.FAILED
            service.error = str(e)
            logger.error(f"Failed to initialize service '{service_name}': {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def start_services(self, service_initializers: Dict[str, Callable]) -> bool:
        """
        Start all services in dependency order.

        Args:
            service_initializers: Dictionary mapping service names to initialization functions

        Returns:
            True if all services started successfully
        """
        logger.info("Starting services...")

        # First fetch exchange state
        await self.fetch_exchange_state()

        # Run health checks
        await self.run_health_checks()

        # Check for critical failures in health checks
        critical_failures = [
            name for name, check in self.health_checks.items()
            if check['status'] == 'unhealthy' and name in ['database', 'api_connection']
        ]

        if critical_failures:
            logger.error(f"Critical health check failures: {critical_failures}")
            logger.error("Cannot start services due to critical failures")
            return False

        # Initialize services in dependency order
        initialized = set()
        max_iterations = len(self.services) * 2  # Prevent infinite loop
        iteration = 0

        while len(initialized) < len(self.services) and iteration < max_iterations:
            iteration += 1
            progress = False

            for service_name, service in self.services.items():
                if service_name in initialized:
                    continue

                # Check if all dependencies are initialized
                deps_ready = all(dep in initialized for dep in service.dependencies)

                if deps_ready:
                    init_func = service_initializers.get(service_name)
                    if init_func:
                        success = await self.initialize_service(
                            service_name,
                            init_func,
                            shared_state=self.shared_state
                        )

                        if success:
                            initialized.add(service_name)
                            progress = True
                        else:
                            logger.error(f"Failed to initialize '{service_name}', stopping startup")
                            return False
                    else:
                        logger.warning(f"No initializer for service '{service_name}', marking as running")
                        service.status = ServiceStatus.RUNNING
                        initialized.add(service_name)
                        progress = True

            if not progress:
                # No progress made, likely circular dependency
                pending = [s for s in self.services if s not in initialized]
                logger.error(f"Circular dependency detected or missing initializers. Pending: {pending}")
                return False

        self.startup_complete = True

        # Log startup summary
        running = sum(1 for s in self.services.values() if s.status == ServiceStatus.RUNNING)
        failed = sum(1 for s in self.services.values() if s.status == ServiceStatus.FAILED)

        logger.info(f"Service startup complete: {running} running, {failed} failed")

        # Log state manager statistics
        self.state_manager.log_stats()

        return failed == 0

    async def stop_services(self):
        """Stop all services in reverse dependency order."""
        logger.info("Stopping services...")

        # Build reverse dependency order
        stopped = set()
        max_iterations = len(self.services) * 2
        iteration = 0

        while len(stopped) < len(self.services) and iteration < max_iterations:
            iteration += 1

            for service_name, service in reversed(list(self.services.items())):
                if service_name in stopped:
                    continue

                # Check if any service depends on this one
                dependents = [
                    s for s, info in self.services.items()
                    if service_name in info.dependencies and s not in stopped
                ]

                if not dependents:
                    # Safe to stop this service
                    if service.instance and hasattr(service.instance, 'stop'):
                        try:
                            logger.info(f"Stopping service '{service_name}'...")
                            if asyncio.iscoroutinefunction(service.instance.stop):
                                await service.instance.stop()
                            else:
                                service.instance.stop()
                            logger.debug(f"Service '{service_name}' stopped")
                        except Exception as e:
                            logger.error(f"Error stopping service '{service_name}': {e}")

                    service.status = ServiceStatus.STOPPED
                    stopped.add(service_name)

        logger.info(f"All services stopped ({len(stopped)}/{len(self.services)})")

    def get_service_status(self) -> Dict[str, Dict]:
        """
        Get the status of all services.

        Returns:
            Dictionary of service statuses
        """
        return {
            name: {
                'status': info.status.value,
                'dependencies': info.dependencies,
                'error': info.error,
                'uptime': time.time() - info.start_time if info.start_time else 0
            }
            for name, info in self.services.items()
        }

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get overall health status.

        Returns:
            Health status summary
        """
        service_status = self.get_service_status()

        return {
            'startup_complete': self.startup_complete,
            'services': service_status,
            'health_checks': self.health_checks,
            'state_manager_stats': self.state_manager.get_stats() if self.state_manager else {},
            'timestamp': time.time()
        }