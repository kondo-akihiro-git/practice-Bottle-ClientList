<html>
  
# App「会社情報スクレイピングAPI」

## 概要

会社ホームページのURLから遷移先までHTML解析することで、<br>
会社の連絡先（電話番号/メールアドレス/お問い合わせリンク）を取得できるAPIです。<br>
営業リストを効率的に作成することを目的としております。<br>
精度は7割程度のため、取得データに誤りがある点はご了承ください。<br>
| <img width="969" alt="スクリーンショット 2024-09-26 17 45 47" src="https://github.com/user-attachments/assets/5a9d35ac-83d3-4cd7-9eec-77e6e8f8695f" > |
|---|

## 機能

- フォーム入力機能<br>
  会社ホームページのURLをフォーム送信することで、取得した連絡先を画面に表示できる<br>
- JSON取得機能<br>
  URLから連絡先の検索を実行でき、取得した連絡先をJSONで取得できる<br>
- スプレッドシート更新機能<br>
  スプレッドシートからURLを読み取り、取得した連絡先をスプレッドシート上に更新できる<br>

※メイン機能はスプレッドシート更新機能です。営業リストの作成イメージは以下になります。<br>
以下のように営業リストの会社ホームページのURLが記載されていることを前提としております。
| <img width="661" alt="スクリーンショット 2024-09-26 17 21 45" src="https://github.com/user-attachments/assets/f78a6c95-2a1b-43ea-a04d-ee20780d72c6"> |
|---|

以下のように会社の連絡際を出力できます。
| <img width="880" alt="スクリーンショット 2024-09-26 17 20 58" src="https://github.com/user-attachments/assets/66fe3bb7-e851-417c-9492-df78cb6b4f0d"> |
|---|
## 主に利用した技術（フレームワークやライブラリ）

1. Bottle: Pythonの軽量なWebフレームワークで、小規模なアプリやAPI開発に適しています。
2. Celery: 非同期タスクキューを管理するためのライブラリです。
3. Redis: 高速なキー・バリュー型データストアです。Celeryのブローカーとして使用しています。
4. Beautiful Soup: HTMLおよびXMLの解析を行うためのライブラリです。
5. gspread: Google Sheets APIを操作するためのPythonライブラリです。
6. lxml: XMLおよびHTMLの解析および生成を行うための高性能なライブラリです。
7. Vercel: フロントエンドのデプロイメントプラットフォームです。
8. Amazon EC2: 非同期タスク用のサーバです。
9. Redis Cloud: Redisのマネージドサービスで、クラウド上でRedisを簡単に管理できます。

## 主な画面
トップ画面（フォーム入力）
| <img width="927" alt="スクリーンショット 2024-09-26 17 45 03" src="https://github.com/user-attachments/assets/5bc0a35d-ba86-4cb4-82a3-315014e3d26e"> |
|---|

トップ画面（JSON取得）
| <img width="943" alt="スクリーンショット 2024-09-26 17 23 55" src="https://github.com/user-attachments/assets/dc297a85-de51-4ca8-aba1-a9805f217535"> |
|---|

トップ画面（スプレッドシート更新）
| <img width="992" alt="スクリーンショット 2024-09-26 17 23 18" src="https://github.com/user-attachments/assets/b8f40ba4-9a7c-4e31-932b-d3c4d8ae4968"> |
|---|
