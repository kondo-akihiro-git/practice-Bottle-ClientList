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
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

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
        print("start")

        # レスポンスエラーの場合は連絡先は全て空として返却
        response = requests.get(url)
        if response.status_code != 200:
            return {

                'phone_numbers': [],
                'emails': [],
                'contact_links': []
            }
        
        # HTML解析する
        html_content = response.text
        soup = BeautifulSoup(html_content, 'lxml')

        # メインURLのドメインを取得
        main_domain = urlparse(url).netloc

        # 電話番号を正規表現で抽出

        phone_pattern = re.compile(r'\+?\d[\d -]{8,}\d')
        phone_numbers=set()
        phone_numbers.update(phone_pattern.findall(soup.get_text()))

        # メールアドレスを正規表現で抽出
        email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        emails=set()
        emails.update(email_pattern.findall(soup.get_text()))

        # お問い合わせリンクの抽出用変数
        all_links = set() 
        contact_links = set()
        form_pattern = 'forms.gle' 
        unnatural_pattern = re.compile(r'(?=.*[a-zA-Z])(?=.*\d)[a-zA-Z\d]{8,}')
        def is_valid_url(url):
            return not ('error' in url or '404' in url)  or unnatural_pattern.search(url)

        # お問い合わせリンクの抽出
        contact_paths = [
            '/contact',
            '/問い合わせ',
            '/お問い合わせ',
            '/コンタクト',
            '/フォーム',
            '/form'
        ]

        # 相対パスの場合は/contactを返す/絶対パスの場合はhttps://？/contactにメインドメインが含まれているのか確認する   
        unnatural_link_patterns = {'mailto:', 'tel:', 'ftp:', 'file:', 'data:'}
        def is_valid_href(href):
            if href is not None:
                parsed_href = urlparse(href)
            if href is not None and form_pattern in parsed_href.netloc and any(pattern not in href.lower() for pattern in unnatural_link_patterns):
                return True
            if href is None or href.lower().endswith('.pdf') or not is_valid_url(href.lower()) or any(pattern in href.lower() for pattern in unnatural_link_patterns) :
                return False
            if parsed_href.netloc == '' or form_pattern in parsed_href.netloc:
                return True
            return main_domain in parsed_href.netloc

        seen_links = set()
        def is_unique_href(href):
            if href in seen_links:
                return False
            seen_links.add(href)
            return True

        def is_valid_and_unique_href(href):
            return is_valid_href(href) and is_unique_href(href)

        # 全リンクの抽出
        a_tags = soup.find_all('a', href=lambda href: is_valid_and_unique_href(href))
        print(a_tags)
        print(f"メインURLから見つかったaタグの量{len(a_tags)}")
        for a_tag in a_tags:
            href = a_tag['href']

            if form_pattern in href:
                contact_links.add(href)

            # リンクが/contactのみのパターンもあるため繋ぎ合わせでリンクを作成
            if not href.startswith('http'):
                href = url.rstrip('/') + '/' + href.lstrip('/')
            normalized_href = href.rstrip('/')

            # 作成したリンクが適切ではない場合に備えてリダイレクトでチェック
            try:
                response = requests.get(normalized_href)
                if response.status_code == 200:
                    normalized_href = response.url 
                else:
                    continue
            except requests.RequestException as e:
                logging.error(f"Error fetching URL {normalized_href}: {str(e)}")
                continue

            # フィルタリング -yahoo.co.jpなどSNSを除外 -PDFファイルを除外 -リクエストエラーを除外
            if normalized_href is not None and main_domain in normalized_href and not normalized_href.lower().endswith('.pdf') and is_valid_url(normalized_href.lower()) and any(pattern not in normalized_href.lower() for pattern in unnatural_link_patterns):  
                for path in contact_paths:
                    if path in normalized_href:
                        print(normalized_href)
                        contact_links.add(normalized_href)

                all_links.add(normalized_href)

        len_all=len(all_links)
        print(f"メインURLから調査したこれから解析予定のリンク量 : {len_all}")

        # 全リンク解析
        for link in all_links:
            try:
                print(f"サブURL検索開始: {link}")
                link_response = requests.get(link)
                if link_response.status_code == 200:
                    link_html_content = link_response.text
                    link_soup = BeautifulSoup(link_html_content, 'lxml')

                    # 電話番号、メールを再度抽出して統合
                    phone_numbers.update(phone_pattern.findall(link_soup.get_text()))
                    emails.update(email_pattern.findall(link_soup.get_text()))

                    # 遷移先のお問い合わせリンクも抽出
                    a_tags = link_soup.find_all('a', href=lambda href: href is not None and any(keyword in href for keyword in contact_paths))
                    if a_tags is not None and len(a_tags) > 0:

                        print(f"サブURLから見つかったaタグの量 :{len(a_tags)}")
                        for a_tag in a_tags:
                            href = a_tag['href']

                            if 'forms.gle' in href:
                                contact_links.add(href)

                            # リンクが/contactのみのパターンもあるため繋ぎ合わせでリンクを作成
                            if not href.startswith('http'):
                                href = link.rstrip('/') + '/' + href.lstrip('/')
                            normalized_href = href.rstrip('/')

                            # 作成したリンクが適切ではない場合に備えてリダイレクトでチェック
                            try:
                                response = requests.get(normalized_href)
                                if response.status_code == 200:
                                    normalized_href = response.url  # リダイレクト後のURLに更新
                                else:
                                    continue
                            except requests.RequestException as e:
                                continue
                            
                            # フィルタリング -yahoo.co.jpなどSNSを除外 -PDFファイルを除外 -リクエストエラーを除外
                            if normalized_href is not None and main_domain in normalized_href and not normalized_href.lower().endswith('.pdf') and is_valid_url(normalized_href.lower()) and not any(pattern not in normalized_href.lower() for pattern in unnatural_link_patterns):  
                                for path in contact_paths:
                                    if path in normalized_href:
                                        contact_links.add(normalized_href)
                                
            except Exception as e:
                logging.error(f"Error processing link {link}: {str(e)}")
                print(e)

                return {
                    'error': [str(e)],
                    'phone_numbers': [],
                    'emails': [],
                    'contact_links': []
                }
        
        print("end")

        return {
            'phone_numbers': list(phone_numbers),
            'emails': list(emails),
            'contact_links': list(contact_links)
        }
    
    except Exception as e:
        print(e)
        logging.error(f"Error extracting contact info from {url}: {str(e)}")

        return {
            'error': [str(e)],
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

        # ヘッダーの追加
        header = ['URL', '電話番号', 'メールアドレス', 'お問い合わせリンク']
        existing_headers = sheet.row_values(1)
        
        if existing_headers != header:
            sheet.insert_row(header, 1)

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
