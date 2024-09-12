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

# 本番用
# credentials_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
# creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(credentials_json), scope)

# DEBUG用
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)

client = gspread.authorize(creds)

# トップページの表示ルート
@app.route('/')
def index():
    return static_file('index.html', root='.')

# URLから情報を取得する関数(フォーム入力/URL/スプレッドシート全て共通の処理)
def extract_contact_info(url):
    try:

        # レスポンスエラーの場合は連絡先は全て空として返却
        response = requests.get(url)
        if response.status_code != 200:
            return {
                'phone_numbers': [],
                'emails': [],
                'contact_links': []
            }

        # HTML解析する
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
            href = a_tag['href']
            if 'contact' in a_tag.text.lower() or 'お問い合わせ' in a_tag.text:
                # 相対パスのリンクを絶対パスに変換
                if not href.startswith('http'):
                    href = url.rstrip('/') + '/' + href.lstrip('/')
                contact_links.add(href)

        return {
            'phone_numbers': list(phone_numbers),
            'emails': list(emails),
            'contact_links': list(contact_links)
        }
    
    except Exception as e:
        return {'error': str(e)}

    # 例外時も全て空として返却
    # except Exception:
    #     print("----exception---")
    #     return {
    #         'phone_numbers': [],
    #         'emails': [],
    #         'contact_links': []
    #     }

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
    result = extract_contact_info(url)

    # JSON形式で返却
    response.content_type = 'application/json'
    return json.dumps(result, ensure_ascii=False, indent=4)


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
        sheet = client.open_by_key(spreadsheet_id).sheet1
        urls = sheet.col_values(1)[1:]  
        
        # B列、C列、D列を更新するために2から始める
        for index, url in enumerate(urls, start=2):  

            # URL形式かどうかを確認
            if not (url.startswith("http://") or url.startswith("https://")):
                # URLではない場合は、BCD列に全角の「ー」を出力
                sheet.update_cell(index, 2, 'ー')  # B列
                sheet.update_cell(index, 3, 'ー')  # C列
                sheet.update_cell(index, 4, 'ー')  # D列
                continue  # 次のループへ

            # 連絡先を検索
            info = extract_contact_info(url)

            # スプレッドシートの更新（検索結果が空の場合に「ー」を表示）
            if not info['phone_numbers']:
                sheet.update_cell(index, 2, 'ー')  # B列
            else:
                sheet.update_cell(index, 2, ', '.join(info['phone_numbers']))  # B列

            if not info['emails']:
                sheet.update_cell(index, 3, 'ー')  # C列
            else:
                sheet.update_cell(index, 3, ', '.join(info['emails']))  # C列

            if not info['contact_links']:
                sheet.update_cell(index, 4, 'ー')  # D列
            else:
                sheet.update_cell(index, 4, ', '.join(info['contact_links']))  # D列


        return json.dumps({"success": "スプレッドシートが更新されました。"}, ensure_ascii=False, indent=4)

    # エラーハンドリング
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
