from bottle import Bottle, request, response, static_file
import requests
import gspread
from bs4 import BeautifulSoup
from oauth2client.service_account import ServiceAccountCredentials
import json
import re
import os

app = Bottle()

# Google Sheets API認証設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(credentials_json), scope)
client = gspread.authorize(creds)

# トップページを表示するためのルート
@app.route('/')
def index():
    return static_file('index.html', root='.')

# URLから情報を取得する関数
def extract_contact_info(url):
    try:
        # Webページの内容を取得
        response = requests.get(url)
        response.raise_for_status()  # HTTPエラーチェック
        soup = BeautifulSoup(response.text, 'html.parser')

        # 電話番号、メールアドレス、お問い合わせリンクの抽出
        phone_numbers = set()
        emails = set()
        contact_links = set()

        # 電話番号を正規表現で抽出
        phone_pattern = re.compile(r'\+?\d[\d -]{8,}\d')
        for match in phone_pattern.findall(soup.get_text()):
            phone_numbers.add(match)

        # メールアドレスを正規表現で抽出
        email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        for match in email_pattern.findall(soup.get_text()):
            emails.add(match)

        # お問い合わせリンクを抽出
        for a_tag in soup.find_all('a', href=True):
            if 'contact' in a_tag.text.lower() or 'お問い合わせ' in a_tag.text:
                contact_links.add(a_tag['href'])

        return {
            'phone_numbers': list(phone_numbers),
            'emails': list(emails),
            'contact_links': list(contact_links)
        }
    except Exception as e:
        return {'error': str(e)}

# APIエンドポイント
@app.route('/extract', method='GET')
def extract_info():
    # クエリパラメータからURLを取得
    url = request.query.get('company_url')
    if not url:
        response.status = 400
        return {'error': 'Parameter "company_url" is required.'}
    
    result = extract_contact_info(url)

    response.content_type = 'application/json'
    return json.dumps(result, ensure_ascii=False, indent=4)

@app.route('/update_spreadsheet', methods=['GET'])
def update_spreadsheet():
    spreadsheet_id = request.query.get('spreadsheet_id')
    if not spreadsheet_id:
        response.status = 400
        return json.dumps({"error": "スプレッドシートIDが必要です。"}, ensure_ascii=False, indent=4)

    try:
        sheet = client.open_by_key(spreadsheet_id).sheet1
        urls = sheet.col_values(1)[1:]  # A列の値を取得（1行目はヘッダー）
        

        for index, url in enumerate(urls, start=2):  # B列、C列、D列を更新するために2から始める
            info = extract_contact_info(url)
            sheet.update_cell(index, 2, ', '.join(info['phone_numbers']))  # B列
            sheet.update_cell(index, 3, ', '.join(info['emails']))  # C列
            sheet.update_cell(index, 4, ', '.join(info['contact_links']))  # D列

        return json.dumps({"success": "スプレッドシートが更新されました。"}, ensure_ascii=False, indent=4)

    except gspread.SpreadsheetNotFound:
        response.status = 404
        return json.dumps({"error": "スプレッドシートが見つかりません。"}, ensure_ascii=False, indent=4)
    except gspread.APIError as e:
        response.status = 500
        return json.dumps({"error": f"Google Sheets APIエラー: {str(e)}"}, ensure_ascii=False, indent=4)
    except Exception as e:
        response.status = 500
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=4)


# アプリケーションの実行
if __name__ == '__main__':
    app.run(host='localhost', port=8080, debug=True)
