"""
Setup and environment configuration routes.
"""

import os
from flask import Blueprint, jsonify, request, render_template
from src.api.config import API_KEY, API_SECRET, parent_dir
from src.api.services.settings_service import save_settings

setup_bp = Blueprint('setup', __name__)

@setup_bp.route('/')
def index():
    """Serve the main dashboard page."""
    # Check if .env exists and is configured
    env_path = os.path.join(parent_dir, '.env')
    if not os.path.exists(env_path) or not API_KEY or not API_SECRET:
        return render_template('setup.html')
    return render_template('index.html')

@setup_bp.route('/setup')
def setup():
    """Serve the setup page."""
    return render_template('setup.html')

@setup_bp.route('/api/check-env')
def check_env():
    """Check if .env file exists and is configured."""
    env_path = os.path.join(parent_dir, '.env')
    exists = os.path.exists(env_path)
    configured = bool(API_KEY and API_SECRET)

    response_data = {
        'exists': exists,
        'configured': configured
    }

    # If configured, provide masked previews
    if configured:
        # Show first 6 and last 4 characters of API key
        if API_KEY and len(API_KEY) > 10:
            response_data['apiKeyPreview'] = f"{API_KEY[:6]}{'*' * (len(API_KEY) - 10)}{API_KEY[-4:]}"
        else:
            response_data['apiKeyPreview'] = '*' * 20

        # API Secret is always fully masked for security
        if API_SECRET:
            response_data['apiSecretPreview'] = '*' * min(len(API_SECRET), 40)
        else:
            response_data['apiSecretPreview'] = '*' * 20

    return jsonify(response_data)

@setup_bp.route('/api/test-connection', methods=['POST'])
def test_connection():
    """Test API connection with provided credentials."""
    import hmac
    import hashlib
    import time as time_module
    from urllib.parse import urlencode
    import requests
    from src.api.config import BASE_URL

    data = request.json
    use_existing = data.get('useExisting', False)

    if use_existing:
        # Test with existing credentials from environment
        test_key = data.get('apiKey') or API_KEY
        test_secret = data.get('apiSecret') or API_SECRET
    else:
        test_key = data.get('apiKey')
        test_secret = data.get('apiSecret')

    if not test_key or not test_secret:
        return jsonify({'success': False, 'error': 'Missing credentials'})

    try:
        # Test the credentials by making a simple authenticated request
        timestamp = int(time_module.time() * 1000)
        params = {'timestamp': timestamp}
        query_string = urlencode(params)
        signature = hmac.new(
            test_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        headers = {'X-MBX-APIKEY': test_key}
        params['signature'] = signature

        response = requests.get(
            f'{BASE_URL}/fapi/v2/account',
            headers=headers,
            params=params
        )

        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': f'Invalid credentials or API error: {response.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@setup_bp.route('/api/save-env', methods=['POST'])
def save_env():
    """Save API credentials to .env file."""
    global API_KEY, API_SECRET

    data = request.json
    api_key = data.get('apiKey')
    api_secret = data.get('apiSecret')
    keep_existing = data.get('keepExisting', False)

    # If keeping existing values, use current ones for missing fields
    if keep_existing:
        api_key = api_key or API_KEY
        api_secret = api_secret or API_SECRET

    if not api_key or not api_secret:
        return jsonify({'success': False, 'error': 'Missing credentials'})

    try:
        env_path = os.path.join(parent_dir, '.env')
        content = f"""# API Authentication - Simple API key (generate via Aster DEX dashboard)
API_KEY={api_key}
API_SECRET={api_secret}

"""
        with open(env_path, 'w') as f:
            f.write(content)

        # Reload the environment variables for the current process
        API_KEY = api_key
        API_SECRET = api_secret

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
