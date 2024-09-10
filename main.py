from bottle import Bottle, request, response, static_file
import requests
from bs4 import BeautifulSoup
import json
import re

app = Bottle()

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

# トップページを表示するためのルート
@app.route('/')
def index():
    return static_file('index.html', root='.')

# APIエンドポイント
@app.route('/extract', method='POST')
def extract_info():
    urls = request.json.get('urls', [])
    results = {}

    for url in urls:
        results[url] = extract_contact_info(url)

    response.content_type = 'application/json'
    return json.dumps(results, ensure_ascii=False, indent=4)

# アプリケーションの実行
if __name__ == '__main__':
    app.run(host='localhost', port=8080, debug=True)
