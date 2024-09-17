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

app = Bottle()

# Google Sheets API認証設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Google Sheets API認証設定
creds = get_credentials()
client = gspread.authorize(creds)

# 環境変数に基づいて設定を分ける
environment = os.getenv('ENVIRONMENT', 'local')

# ロガーの設定
logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')


# トップページの表示ルート
@app.route('/')
def index():
    return static_file('index.html', root='.')

# URLから情報を取得する関数(フォーム入力/URL/スプレッドシート全て共通の処理)
@lru_cache(maxsize=100)
def extract_contact_info(url):
    try:
        logging.debug(f"Fetching URL: {url}")

        # レスポンスエラーの場合は連絡先は全て空として返却
        response = requests.get(url)
        if response.status_code != 200:
            logging.warning(f"Failed to fetch URL: {url} with status code: {response.status_code}")
            return {
                'phone_numbers': [],
                'emails': [],
                'contact_links': []
            }
        
        # HTML解析する前にHTMLを出力
        html_content = response.text
        logging.debug(f"HTML content fetched from {url}.")
        
        ###############################################テスト################################################

        # 解析対象のHTMLの最初の1000文字をログに出力
        # logging.debug(f"HTML content from {url}:\n{html_content[:]}") 
        
        # HTMLをファイルに保存（必要に応じて）
        # with open('output.html', 'w', encoding='utf-8') as file:
        #     file.write(html_content)        

        ####################################################################################################

        # HTML解析する
        soup = BeautifulSoup(html_content, 'html.parser')

        # メインURLのドメインを取得
        main_domain = urlparse(url).netloc

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
        all_links = set() 
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if not href.startswith('http'):
                href = url.rstrip('/') + '/' + href.lstrip('/')
            normalized_href = href.rstrip('/')
            if main_domain == urlparse(normalized_href).netloc and not normalized_href.lower().endswith('.pdf'):
                all_links.add(normalized_href)

            if 'contact' in href.lower() or '問い合わせ' in href or 'コンタクト' in href or 'フォーム' in href or 'form' in href.lower():
                contact_links.add(normalized_href)

        # all_linksに含まれるすべてのリンクについても解析
        for link in all_links:
            try:
                logging.debug(f"Fetching linked URL: {link}")
                link_response = requests.get(link)
                if link_response.status_code == 200:
                    link_html_content = link_response.text
                    link_soup = BeautifulSoup(link_html_content, 'html.parser')

                    # 各遷移先の電話番号、メール、リンク情報を再度抽出して統合
                    for match in phone_pattern.findall(link_soup.get_text()):
                        phone_numbers.add(match)

                    for match in email_pattern.findall(link_soup.get_text()):
                        emails.add(match)

                    # 遷移先のお問い合わせリンクも抽出
                    for a_tag in link_soup.find_all('a', href=True):
                        href = a_tag['href']
                        if not href.startswith('http'):
                            href = link.rstrip('/') + '/' + href.lstrip('/')
                        normalized_href = href.rstrip('/')

                        # 全リンクと同時に、お問い合わせリンクも抽出
                        if 'contact' in href.lower() or '問い合わせ' in href or 'コンタクト' in href or 'フォーム' in href or 'form' in href.lower():
                            contact_links.add(normalized_href)

            except Exception as e:
                logging.error(f"Error processing link {link}: {str(e)}")
                if environment == 'production':
                    print("----exception---")
                    return {
                        'phone_numbers': [],
                        'emails': [],
                        'contact_links': []
                    }

        return {
            'phone_numbers': list(phone_numbers),
            'emails': list(emails),
            'contact_links': list(contact_links)
        }
    
    except Exception as e:
        logging.error(f"Error extracting contact info from {url}: {str(e)}")
        if environment == 'production':
            print("----exception---")
            return {
                'phone_numbers': [],
                'emails': [],
                'contact_links': []
            }


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
    logging.debug(f"Extracting information for URL: {url}")
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
                logging.warning(f"Invalid URL format: {url}")
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
        logging.error("Spreadsheet not found.")
        response.status = 404
        return json.dumps({"error": "スプレッドシートが見つかりません。"}, ensure_ascii=False, indent=4)
    except gspread.APIError as e:
        logging.error(f"Google Sheets API error: {str(e)}")
        response.status = 500
        return json.dumps({"error": f"Google Sheets APIエラー: {str(e)}"}, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Error updating spreadsheet: {str(e)}")
        response.status = 500
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=4)

# アプリケーションの実行
if __name__ == '__main__':
    app.run(host='localhost', port=8080, debug=True)
