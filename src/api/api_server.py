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
    import os
    from dotenv import load_dotenv
    
    # Load .env file for local development (no-op in Railway)
    load_dotenv()
    
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Only show errors, not access logs

    # Use standardized environment variable logic (system env vars take precedence over .env)
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    
    print(f"Starting API server on {host}:{port}")
    app.run(debug=False, host=host, port=port, threaded=True)
