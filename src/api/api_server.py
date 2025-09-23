"""
Flask API server for Aster Liquidation Hunter Bot dashboard.

This is the main entry point that now imports from the refactored modular structure.
"""

# Import and run the refactored application
from src.api.app import create_app

# Create the Flask app instance
app = create_app()

if __name__ == '__main__':
    # Disable Flask/Werkzeug access logs
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Only show errors, not access logs

    print("Starting API server on http://localhost:5000")
    app.run(debug=False, port=5000, threaded=True)
