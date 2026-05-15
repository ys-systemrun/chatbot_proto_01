import time
from src.embedding import get_embedding
from src.db import DB
import os

# 登録したいQ&A
QA_DATA = [
    {
        "question": "マスタの読み込み時に'Unable to open the physical file \"...\\Documents\\Systemrun\\IzumiV7\\Caches\\d159e27eef87ebd52fd336755077c030\\bugakari_master.mdf\". Operating system error 32: \"32(プロセスはファイルにアクセスできません。別のプロセスが使用中です。)\".'というエラーが発生します。",
        "answer": "御社環境で、バックアップソフト等の定期的または不定期にファイルにアクセスするソフトが導入されている場合、そのソフトがマスタファイルを参照している状態だと上記エラーが発生する場合がございます。システム管理者の方にそういったソフトがあるかご確認の上、必要に応じてバックアップの例外リスト等に入れて頂くことで改善するかと思われます。"
    },
    {
        "question": "プロセスがファイルにアクセスできないというエラーが発生します。",
        "answer": "御社環境で、バックアップソフト等の定期的または不定期にファイルにアクセスするソフトが導入されている場合、そのソフトがマスタファイルを参照している状態だと上記エラーが発生する場合がございます。システム管理者の方にそういったソフトがあるかご確認の上、必要に応じてバックアップの例外リスト等に入れて頂くことで改善するかと思われます。"
    },
    {
        "question": "マスタの読み込み時にフリーズしたりタイムアウトしてエラーを吐いたり、維津美がそのまま落ちたりすることがある。",
        "answer": "(1)スタートメニューを右クリック＞「アプリと機能」＞「Microsoft SQL Server LocalDB 2017」をアンインストールしてください(場合によっては C:\\Users\\ユーザー名\\AppData\\Local\\Microsoft\\Microsoft SQL Server のフォルダを直接削除しないとダメかも？)。その後サポートページの「ダウンロード」＞「積算システム」欄＞「SQL Server LocalDB 2017」をクリックしてダウンロード、実行してインストールを行ってください。(2)ツール(T)＞「メンテナンス」＞「データベース」をクリックし、「データベースのメンテナンス」画面で「インスタンスの停止2」→「インスタンス削除2」→「インスタンスの作成2」→「インスタンスの開始2」の順に「選択した処理を実行」を行なってください。下部のテキストボックスにログが表示されるので、エラーなく終わりましたら再度維津美での動作をご確認ください。インスタンスの削除等ができない場合は、パス：C:\\Users\\(ユーザー名)\\AppData\\Local\\Microsoft\\Microsoft SQL Server Local DB\\Instances\\Izumi7Instance のファイルを手動で削除しても改善する場合がございます。(3):(1)(2)で解決しない場合、メモリ不足や不良によるものの可能性もございます。何も起動していない状態でメモリ使用量が90％を超えているような環境ですとメモリの交換等検討いただいた方がよろしいかもしれません。"
    },
    {
        "question": "ネットワークキーで以下のエラーが発生しました。ログインエラー：too many users",
        "answer": "(当ページ上部の『認証方法の判別』の手順により・または利用したい認証方法を直接お客様に確認し、利用したい認証が『ネットワーク認証』以外の場合)『認証設定』＞『認証方法』欄の選択が間違っています。適切な認証方法を選択してください。(利用したい認証が『ネットワーク認証』の場合)接続数がライセンス数いっぱいになっております。ライセンスの空きが出るのをお待ちください。他で認証していないという場合はネットワークキーを抜き差しして頂く、あるいは数分お待ちいただくことで認証できるようになる場合がございます。"
    },
]

EMBEDDING_URL = os.environ["LMSTUDIO_EMBEDDING_URL"]
EMBEDDING_MODEL=os.environ["MODEL_EMBEDDING"]
DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    with DB(DATABASE_URL) as db:
        exists = db.exist_any()
        if exists:
            print("already seeded.")
            return 
        for qa in QA_DATA:
            print(f"Processing: {qa['question']}")

            # 1. embedding生成
            emb = get_embedding(
                EMBEDDING_URL, 
                EMBEDDING_MODEL, 
                qa["question"]
            )
            # 2. DB登録
            db.insert_qa(qa["question"], qa["answer"], emb)
            # API負荷軽減（任意）
            time.sleep(0.5)
    print("Done.")


if __name__ == "__main__":
    main()