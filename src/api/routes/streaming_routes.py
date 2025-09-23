"""
Streaming routes (Server-Sent Events).
"""

from flask import Blueprint, Response, stream_with_context
import time
import json
from src.api.services.event_service import event_queue, event_lock

streaming_bp = Blueprint('streaming', __name__)

@streaming_bp.route('/api/stream')
def stream_events():
    """Server-sent events endpoint for real-time updates."""
    def generate():
        # Send immediate connected event
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': int(time.time() * 1000)})}\n\n"

        last_check = time.time()

        while True:
            # Send heartbeat every 30 seconds
            if time.time() - last_check > 30:
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': int(time.time() * 1000)})}\n\n"
                last_check = time.time()

            # Send queued events
            with event_lock:
                while event_queue:
                    event = event_queue.popleft()
                    yield f"data: {json.dumps(event)}\n\n"

            time.sleep(1)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )
