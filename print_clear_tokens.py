from app import create_app
from app.services.database_service import db_service
import os
import json

app = create_app()
with app.app_context():
    print("Clearing tokens...")
    result_access = db_service.save_setting("auth.access_token", "", data_type="string")
    print(f"Cleared access_token: {result_access}")
    result_refresh = db_service.save_setting("auth.refresh_token", "", data_type="string")
    print(f"Cleared refresh_token: {result_refresh}")

    # Also clear access_token and refresh_token in config/auth.json if present
    auth_config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'config', 'auth.json'))
    if os.path.exists(auth_config_path):
        with open(auth_config_path, 'r') as f:
            config = json.load(f)
        changed = False
        if 'access_token' in config:
            config['access_token'] = ''
            changed = True
        if 'refresh_token' in config:
            config['refresh_token'] = ''
            changed = True
        if changed:
            with open(auth_config_path, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"Cleared access_token and refresh_token in {auth_config_path}")
        else:
            print(f"No access_token or refresh_token fields found in {auth_config_path}")
    else:
        print(f"auth.json not found at {auth_config_path}") 