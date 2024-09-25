# celery_worker.py
from celery import Celery
from credentials import get_credentials
import gspread
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

app = Celery('tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

# Google Sheets API認証設定
creds = get_credentials()
client = gspread.authorize(creds)

@app.task
def extract_contact_info_task(url):

    try:
        # レスポンスエラーの場合は連絡先は全て空として返却
        response = requests.get(url)
        if response.status_code != 200:
            return {
                'error':['200 Error'],
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

        phone_pattern = re.compile(r'(?!\d{12})\+?\d[\d -]{8,11}\d(?!\d{3,})')

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
                # logging.error(f"Error fetching URL {normalized_href}: {str(e)}")
                continue

            # フィルタリング -yahoo.co.jpなどSNSを除外 -PDFファイルを除外 -リクエストエラーを除外
            if normalized_href is not None and main_domain in normalized_href and not normalized_href.lower().endswith('.pdf') and is_valid_url(normalized_href.lower()) and any(pattern not in normalized_href.lower() for pattern in unnatural_link_patterns):  
                for path in contact_paths:
                    if path in normalized_href:
                        print(normalized_href)
                        contact_links.add(normalized_href)

                all_links.add(normalized_href)


        # 全リンク解析
        for link in all_links:
            try:
                
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
                # logging.error(f"Error processing link {link}: {str(e)}")
                return {
                  'error': [str(e)],
                  'phone_numbers': [],
                  'emails': [],
                  'contact_links': [],
                  'status_code': 500
                }
        return {
            'phone_numbers': list(phone_numbers),
            'emails': list(emails),
            'contact_links': list(contact_links)
        }
    
    except Exception as e:
        # logging.error(f"Error extracting contact info from {url}: {str(e)}")
        return {
          'error': [str(e)],
          'phone_numbers': [],
          'emails': [],
          'contact_links': [],
          'status_code': 500
        }


@app.task
def update_spreadsheet_task(spreadsheet_id):
    if not spreadsheet_id:
        response.status = 400
        return {"error": ["スプレッドシートIDが必要です。"]}

    try:
        sheet = client.open_by_key(spreadsheet_id).sheet1
        header = ['URL', '電話番号', 'メールアドレス', 'お問い合わせリンク']
        existing_headers = sheet.row_values(1)
        
        if existing_headers != header:
            sheet.update_cell(1,1,header[0])
            sheet.update_cell(1,2,header[1])
            sheet.update_cell(1,3,header[2])
            sheet.update_cell(1,4,header[3])

        urls = sheet.col_values(1)[1:]  

        output_row = 2  # 出力行を明示的に定義
        
        for url in urls:
            info = extract_contact_info_task(url) 
            status_code = info.pop('status_code', 200)

            if status_code != 200:
                sheet.update_cell(output_row, 2, 'ー')  
            else:
                
                phone_numbers = ["'" + number if number.startswith('+') else number for number in info['phone_numbers']]
                sheet.update_cell(output_row, 2, ', '.join(phone_numbers))

            if not info['emails']:
                sheet.update_cell(output_row, 3, 'ー')  
            else:
                sheet.update_cell(output_row, 3, ', '.join(info['emails']))

            if not info['contact_links']:
                sheet.update_cell(output_row, 4, 'ー')  
            else:
                sheet.update_cell(output_row, 4, ', '.join(info['contact_links'])) 
            
            output_row += 1  # 出力行をインクリメントして次の行に進む

    except gspread.SpreadsheetNotFound:
        response.status = 404
        return {"error": ["スプレッドシートが見つかりません。"]}
    except Exception as e:
        response.status = 500
        return {'error': [str(e)]}