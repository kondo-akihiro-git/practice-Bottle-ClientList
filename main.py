from urllib.parse import urlparse
from bottle import Bottle, request, response, static_file
import requests
import gspread
from bs4 import BeautifulSoup
import json
import re
import os
from credentials import get_credentials
import logging
from functools import lru_cache
from celery import Celery
import warnings
from celery.result import AsyncResult
warnings.filterwarnings("ignore", category=DeprecationWarning)

app = Bottle()

# Google Sheets API認証設定
# scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# # Google Sheets API認証設定
# creds = get_credentials()
# client = gspread.authorize(creds)

# 環境変数に基づいて設定を分ける
environment = os.getenv('ENVIRONMENT', 'local')

redis_url = os.getenv('REDIS_URL')
cel = Celery('tasks', broker=redis_url, backend=redis_url)

# # ロガーの設定
# logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')

# トップページの表示ルート
@app.route('/')
def index():
    return static_file('index.html', root='.')


# APIエンドポイント（フォーム入力押下時/URL押下時）
@app.route('/extract', method='GET')
def extract_info():
    # クエリパラメータからURLを取得
    url = request.query.get('company_url')

    # 入力内容がURLではない場合
    if not url:
        response.status = 400
        return {'error': 'Parameter "company_url" is required.'}
    
    # 連絡先の検索
    # logging.debug(f"Extracting information for URL: {url}")
    # result = extract_contact_info(url)

    # JSON形式で返却
    # response.content_type = 'application/json'
    # return json.dumps(result, ensure_ascii=False, indent=4)

    # Celeryタスクを非同期に実行
    # celery -A celery_worker worker --loglevel=info
    task = cel.send_task('tasks.extract_contact_info_task', args=[url])

    # タスクIDを返却（クライアントでポーリングするため）
    return {'task_id': task.id}

@app.route('/task_result/<task_id>', method='GET')
def task_result(task_id):
    # result = cel.extract_contact_info_task.AsyncResult(task_id)
    result = AsyncResult(task_id, app=cel)

    if result.state == 'PENDING':
        response.content_type = 'application/json'
        return {'state': result.state}

    elif result.state != 'FAILURE':
        return {
            'state': result.state,
            'result': result.result,
        }
    else:
        return {
            'state': result.state,
            'error': str(result.info),
        }
    
@app.route('/update_task_result/<task_id>', method='GET')
def update_task_result(task_id):
    # result = cel.extract_contact_info_task.AsyncResult(task_id)
    result = AsyncResult(task_id, app=cel)

    if result.state == 'PENDING':
        response.content_type = 'application/json'
        return {'state': result.state}

    elif result.state != 'FAILURE':
        return {
            'state': result.state,
            'result': result.result,
        }
    else:
        return {
            'state': result.state,
            'error': str(result.info),
        }


# スプレッドシートの読み取り/更新
@app.route('/update_spreadsheet', methods=['GET'])
def update_spreadsheet():

    # スプレッドシートの読み込み
    spreadsheet_id = request.query.get('spreadsheet_id')
    if not spreadsheet_id:
        response.status = 400
        return json.dumps({"error": "スプレッドシートIDが必要です。"}, ensure_ascii=False, indent=4)

    # 読み込んだスプレッドシートのA列＝会社URL（1行目はヘッダー）
    try:
        # 連絡先を検索
        # task = cel.update_spreadsheet_task.delay(spreadsheet_id)
        task = cel.send_task('tasks.update_spreadsheet_task', args=[spreadsheet_id])

        return json.dumps({"task_id": task.id}, ensure_ascii=False, indent=4)

    # エラーハンドリング
    except gspread.SpreadsheetNotFound:
        # logging.error("Spreadsheet not found.")
        response.status = 404
        return json.dumps({"error": "スプレッドシートが見つかりません。"}, ensure_ascii=False, indent=4)
    except gspread.APIError as e:
        # logging.error(f"Google Sheets API error: {str(e)}")
        response.status = 500
        return json.dumps({"error": f"Google Sheets APIエラー: {str(e)}"}, ensure_ascii=False, indent=4)
    except Exception as e:
        # logging.error(f"Error updating spreadsheet: {str(e)}")
        response.status = 500
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=4)

# アプリケーションの実行
if __name__ == '__main__':
    app.run(host='localhost', port=8080, debug=True)
