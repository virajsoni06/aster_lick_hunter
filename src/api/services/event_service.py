"""
Event service for Server-Sent Events (SSE) functionality.
"""

import time
import threading
from collections import deque

# SSE event queue for real-time updates
event_queue = deque(maxlen=100)
event_lock = threading.Lock()

def add_event(event_type, data):
    """Add event to SSE queue."""
    with event_lock:
        event_queue.append({
            'type': event_type,
            'data': data,
            'timestamp': int(time.time() * 1000)
        })
