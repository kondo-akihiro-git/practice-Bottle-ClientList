import json
import os
from oauth2client.service_account import ServiceAccountCredentials

def get_credentials():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # 環境変数に基づいて設定を分ける
    environment = os.getenv('ENVIRONMENT', 'local')  # 'ENVIRONMENT' 環境変数が設定されていない場合は 'local' とみなす

    if environment == 'production':
        # 本番用
        credentials_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(credentials_json), scope)
    else:
        # ローカル用
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)


    return creds
