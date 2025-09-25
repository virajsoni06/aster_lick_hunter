"""
Event Bus - Asynchronous event-driven communication system for services.
Enables loose coupling between components through publish-subscribe pattern.
"""

import asyncio
import time
import logging
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)

class EventType(Enum):
    """Standard event types used in the system."""
    # Order events
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_EXPIRED = "order_expired"
    ORDER_REJECTED = "order_rejected"

    # Position events
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_UPDATED = "position_updated"
    POSITION_LIQUIDATED = "position_liquidated"

    # Tranche events
    TRANCHE_CREATED = "tranche_created"
    TRANCHE_UPDATED = "tranche_updated"
    TRANCHE_MERGED = "tranche_merged"

    # TP/SL events
    TP_PLACED = "tp_placed"
    TP_TRIGGERED = "tp_triggered"
    SL_PLACED = "sl_placed"
    SL_TRIGGERED = "sl_triggered"
    PROTECTION_MISSING = "protection_missing"
    PROTECTION_RECOVERED = "protection_recovered"

    # System events
    SERVICE_STARTED = "service_started"
    SERVICE_STOPPED = "service_stopped"
    SERVICE_ERROR = "service_error"
    CLEANUP_CYCLE = "cleanup_cycle"
    RECONCILIATION = "reconciliation"

    # Market events
    LIQUIDATION_DETECTED = "liquidation_detected"
    THRESHOLD_MET = "threshold_met"
    PRICE_SPIKE = "price_spike"

@dataclass
class Event:
    """Represents an event in the system."""
    type: EventType
    source: str  # Service that generated the event
    data: Dict[str, Any]
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

class EventBus:
    """
    Asynchronous event bus for inter-service communication.
    Implements publisher-subscriber pattern with async handlers.
    """

    def __init__(self):
        """Initialize the event bus."""
        # Subscribers: event_type -> list of (handler, filter)
        self.subscribers: Dict[EventType, List[tuple]] = defaultdict(list)

        # Event history for debugging
        self.event_history: List[Event] = []
        self.max_history_size = 1000

        # Statistics
        self.stats = {
            'events_published': 0,
            'events_delivered': 0,
            'events_failed': 0,
            'subscribers_count': 0
        }

        # Running state
        self.running = True

        # Event queue for async processing
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.processor_task: Optional[asyncio.Task] = None

        logger.info("EventBus initialized")

    def subscribe(self, event_type: EventType, handler: Callable,
                 filter_func: Optional[Callable] = None) -> bool:
        """
        Subscribe to an event type.

        Args:
            event_type: The type of event to subscribe to
            handler: Async function to call when event occurs
            filter_func: Optional filter function to check if handler should be called

        Returns:
            True if subscription successful
        """
        try:
            if not asyncio.iscoroutinefunction(handler):
                logger.error(f"Handler for {event_type} must be an async function")
                return False

            self.subscribers[event_type].append((handler, filter_func))
            self.stats['subscribers_count'] += 1

            logger.debug(f"Subscribed handler to {event_type.value}")
            return True

        except Exception as e:
            logger.error(f"Error subscribing to {event_type}: {e}")
            return False

    def unsubscribe(self, event_type: EventType, handler: Callable) -> bool:
        """
        Unsubscribe from an event type.

        Args:
            event_type: The type of event to unsubscribe from
            handler: The handler function to remove

        Returns:
            True if unsubscription successful
        """
        try:
            handlers = self.subscribers[event_type]
            original_count = len(handlers)

            # Remove all subscriptions for this handler
            self.subscribers[event_type] = [
                (h, f) for h, f in handlers if h != handler
            ]

            removed = original_count - len(self.subscribers[event_type])
            if removed > 0:
                self.stats['subscribers_count'] -= removed
                logger.debug(f"Unsubscribed {removed} handler(s) from {event_type.value}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error unsubscribing from {event_type}: {e}")
            return False

    async def publish(self, event: Event):
        """
        Publish an event asynchronously.

        Args:
            event: The event to publish
        """
        if not self.running:
            logger.warning("EventBus not running, dropping event")
            return

        try:
            # Add to queue for processing
            await self.event_queue.put(event)
            self.stats['events_published'] += 1

            # Add to history
            self.event_history.append(event)
            if len(self.event_history) > self.max_history_size:
                self.event_history = self.event_history[-self.max_history_size:]

            logger.debug(f"Published {event.type.value} from {event.source}")

        except Exception as e:
            logger.error(f"Error publishing event: {e}")
            self.stats['events_failed'] += 1

    def publish_sync(self, event: Event):
        """
        Publish an event synchronously (creates task if in async context).

        Args:
            event: The event to publish
        """
        try:
            # Try to get the running loop
            loop = asyncio.get_running_loop()
            # We're in an async context, create a task
            asyncio.create_task(self.publish(event))
        except RuntimeError:
            # No running loop, need to handle differently
            logger.warning(f"Cannot publish event {event.type.value} - no async context")

    async def _process_event(self, event: Event):
        """
        Process a single event by calling all subscribers.

        Args:
            event: The event to process
        """
        handlers = self.subscribers.get(event.type, [])

        if not handlers:
            logger.debug(f"No handlers for {event.type.value}")
            return

        # Call all handlers concurrently
        tasks = []
        for handler, filter_func in handlers:
            # Check filter if provided
            if filter_func and not filter_func(event):
                continue

            # Create task for handler
            task = asyncio.create_task(self._call_handler(handler, event))
            tasks.append(task)

        # Wait for all handlers to complete
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successes and failures
            for result in results:
                if isinstance(result, Exception):
                    self.stats['events_failed'] += 1
                else:
                    self.stats['events_delivered'] += 1

    async def _call_handler(self, handler: Callable, event: Event):
        """
        Call a single event handler with error handling.

        Args:
            handler: The handler function to call
            event: The event to pass to the handler
        """
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Error in event handler for {event.type.value}: {e}")
            raise

    async def process_events(self):
        """Main event processing loop."""
        logger.info("Starting event processing loop")

        while self.running:
            try:
                # Wait for event with timeout to allow checking running state
                event = await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=1.0
                )

                # Process the event
                await self._process_event(event)

            except asyncio.TimeoutError:
                continue  # Check running state and continue
            except Exception as e:
                logger.error(f"Error in event processing loop: {e}")
                self.stats['events_failed'] += 1

        logger.info("Event processing loop stopped")

    def start(self):
        """Start the event processing loop."""
        if self.processor_task is None:
            try:
                loop = asyncio.get_running_loop()
                self.processor_task = loop.create_task(self.process_events())
                logger.info("EventBus processing started")
            except RuntimeError:
                logger.error("No async context to start event processing")

    def stop(self):
        """Stop the event processing loop."""
        self.running = False
        if self.processor_task:
            self.processor_task.cancel()
            self.processor_task = None
        logger.info("EventBus stopped")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get event bus statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            **self.stats,
            'queue_size': self.event_queue.qsize() if self.event_queue else 0,
            'history_size': len(self.event_history),
            'subscriber_counts': {
                event_type.value: len(handlers)
                for event_type, handlers in self.subscribers.items()
            }
        }

    def get_recent_events(self, event_type: Optional[EventType] = None,
                         source: Optional[str] = None,
                         limit: int = 100) -> List[Event]:
        """
        Get recent events from history.

        Args:
            event_type: Optional filter by event type
            source: Optional filter by source
            limit: Maximum number of events to return

        Returns:
            List of recent events matching filters
        """
        events = self.event_history

        if event_type:
            events = [e for e in events if e.type == event_type]

        if source:
            events = [e for e in events if e.source == source]

        return events[-limit:]

# Global event bus instance
_event_bus: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    """
    Get the global EventBus instance.

    Returns:
        The global EventBus instance
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus

def reset_event_bus():
    """Reset the global EventBus instance (mainly for testing)."""
    global _event_bus
    if _event_bus:
        _event_bus.stop()
    _event_bus = None

# Helper functions for common event patterns

async def emit_order_event(event_type: EventType, order_data: Dict, source: str):
    """
    Emit an order-related event.

    Args:
        event_type: Type of order event
        order_data: Order information
        source: Source service name
    """
    event = Event(
        type=event_type,
        source=source,
        data=order_data
    )
    await get_event_bus().publish(event)

async def emit_position_event(event_type: EventType, position_data: Dict, source: str):
    """
    Emit a position-related event.

    Args:
        event_type: Type of position event
        position_data: Position information
        source: Source service name
    """
    event = Event(
        type=event_type,
        source=source,
        data=position_data
    )
    await get_event_bus().publish(event)

async def emit_system_event(event_type: EventType, data: Dict, source: str):
    """
    Emit a system-related event.

    Args:
        event_type: Type of system event
        data: Event data
        source: Source service name
    """
    event = Event(
        type=event_type,
        source=source,
        data=data
    )
    await get_event_bus().publish(event)