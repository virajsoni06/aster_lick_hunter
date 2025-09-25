"""
Rate limiter monitoring API routes for real-time dashboard.
Provides REST endpoints to monitor and control rate limiter status.
"""

import time
from flask import Blueprint, jsonify, request
from src.utils.enhanced_rate_limiter import rate_limiter
from src.utils.utils import log

rate_limiter_bp = Blueprint('rate_limiter', __name__, url_prefix='/api/rate-limiter')

@rate_limiter_bp.route('/stats', methods=['GET'])
def get_rate_limiter_stats():
    """
    Get comprehensive rate limiter statistics.

    Returns real-time data on:
    - Usage percentages and limits
    - Queue sizes and backlogs
    - Active modes (burst/liquidation)
    - Ban status and alerts
    """
    try:
        stats = rate_limiter.get_stats()

        # Enhanced stats for monitoring
        enhanced_stats = {
            'status': 'success',
            'timestamp': stats.get('timestamp', None),
            'data': stats,
            'health': {
                'status': 'healthy' if stats.get('current_usage_pct', 0) < 90 and not stats.get('banned', False) else 'warning',
                'issues': []
            }
        }

        # Add health check alerts
        if stats.get('banned', False):
            enhanced_stats['health']['status'] = 'critical'
            enhanced_stats['health']['issues'].append('IP banned by exchange')

        if stats.get('current_usage_pct', 0) > 95:
            enhanced_stats['health']['status'] = 'critical'
            enhanced_stats['health']['issues'].append('Critical API usage')

        elif stats.get('current_usage_pct', 0) > 85:
            enhanced_stats['health']['status'] = 'warning'
            enhanced_stats['health']['issues'].append('High API usage')

        if stats.get('consecutive_429s', 0) > 0:
            enhanced_stats['health']['issues'].append(f"{stats['consecutive_429s']} consecutive rate limits")

        if stats['queue_sizes']['critical'] > 10:
            enhanced_stats['health']['issues'].append(f"Large critical queue: {stats['queue_sizes']['critical']} requests")

        return jsonify(enhanced_stats)

    except Exception as e:
        log.error(f"Error getting rate limiter stats: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@rate_limiter_bp.route('/burst-mode', methods=['POST'])
def enable_burst_mode():
    """
    Manually enable burst mode for 5 minutes.
    Use during high trading activity to increase API utilization.
    """
    try:
        duration = int(request.json.get('duration', 300)) if request.json else 300
        rate_limiter.enable_burst_mode(duration_seconds=duration)

        log.info(f"Manually enabled burst mode for {duration}s")
        return jsonify({
            'status': 'success',
            'message': f'Burst mode enabled for {duration} seconds',
            'duration': duration
        })

    except Exception as e:
        log.error(f"Error enabling burst mode: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@rate_limiter_bp.route('/liquidation-mode', methods=['POST'])
def enable_liquidation_mode():
    """
    Manually enable liquidation mode - USE WITH EXTREME CAUTION.

    This uses 95% of API capacity and should only be used during
    massive liquidation cascades where missing events means lost profits.
    """
    try:
        confirm = request.json.get('confirm', False) if request.json else False
        if not confirm:
            return jsonify({
                'status': 'error',
                'message': 'Liquidation mode requires confirmation. Send {"confirm": true}'
            }), 400

        duration = int(request.json.get('duration', 300)) if request.json else 300
        rate_limiter.enable_liquidation_mode(duration_seconds=duration)

        log.critical(f"Manually enabled LIQUIDATION MODE for {duration}s - MAXIMUM CAPACITY")
        return jsonify({
            'status': 'success',
            'message': f'🚨 LIQUIDATION MODE ENABLED for {duration} seconds - USING 95% OF API CAPACITY!',
            'duration': duration,
            'warning': 'Monitor closely - this significantly increases rate limit risk'
        })

    except Exception as e:
        log.error(f"Error enabling liquidation mode: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@rate_limiter_bp.route('/reset-modes', methods=['POST'])
def reset_modes():
    """
    Reset burst and liquidation modes to normal operation.
    Use to regain normal safety buffers.
    """
    try:
        rate_limiter.disable_burst_mode()
        rate_limiter.disable_liquidation_mode()

        log.info("Manually reset rate limiter modes to normal")
        return jsonify({
            'status': 'success',
            'message': 'Rate limiter modes reset to normal operation'
        })

    except Exception as e:
        log.error(f"Error resetting modes: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@rate_limiter_bp.route('/queues', methods=['GET'])
def get_queue_status():
    """
    Get detailed queue status for debugging.
    Shows pending requests by priority level.
    """
    try:
        stats = rate_limiter.get_stats()

        # Get next request info if available
        next_request = rate_limiter.get_next_request()
        if next_request:
            next_request_info = {
                'endpoint': next_request['endpoint'],
                'priority': next_request['priority'],
                'queued_for': time.time() - next_request['timestamp']
            }
        else:
            next_request_info = None

        queue_data = {
            'status': 'success',
            'queues': stats['queue_sizes'],
            'next_request': next_request_info,
            'total_queued': sum(stats['queue_sizes'].values()),
            'oldest_request_age': None
        }

        # Find oldest request age across all queues
        oldest_age = 0
        for queue_name, queue in [('critical', rate_limiter._get_queue_by_priority('critical')),
                                ('normal', rate_limiter._get_queue_by_priority('normal')),
                                ('low', rate_limiter._get_queue_by_priority('low'))]:
            if queue:
                for item in queue:
                    age = time.time() - item['timestamp']
                    oldest_age = max(oldest_age, age)

        if oldest_age > 0:
            queue_data['oldest_request_age'] = oldest_age

        return jsonify(queue_data)

    except Exception as e:
        log.error(f"Error getting queue status: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@rate_limiter_bp.route('/history', methods=['GET'])
def get_request_history():
    """
    Get recent request history for analysis.
    Useful for debugging rate limit patterns.
    """
    try:
        # Get parameters
        limit = min(int(request.args.get('limit', 50)), 100)  # Max 100 records
        hours = float(request.args.get('hours', 1))  # Default 1 hour

        # Get history from rate limiter
        # Note: This is a simplified version - you'd want to store more detailed history
        current_time = time.time()
        cutoff_time = current_time - (hours * 3600)

        recent_requests = [
            (timestamp, weight) for timestamp, weight in rate_limiter.request_history
            if timestamp > cutoff_time
        ]

        # Group by minute for chart data
        import collections
        minute_counts = collections.defaultdict(int)
        minute_weights = collections.defaultdict(int)

        for timestamp, weight in recent_requests:
            minute_key = int(timestamp // 60) * 60
            minute_counts[minute_key] += 1
            minute_weights[minute_key] += weight

        chart_data = [
            {
                'timestamp': minute_key,
                'requests': minute_counts[minute_key],
                'weight': minute_weights[minute_key]
            }
            for minute_key in sorted(minute_counts.keys())
        ]

        return jsonify({
            'status': 'success',
            'period': f'{hours} hours',
            'total_requests': len(recent_requests),
            'chart_data': chart_data
        })

    except Exception as e:
        log.error(f"Error getting request history: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
