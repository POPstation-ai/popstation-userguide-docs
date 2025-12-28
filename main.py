# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from notion_client import Client
from notion_to_md import NotionToMarkdownConverter

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
notion = Client(auth=NOTION_TOKEN)
ROOT_PAGE_ID = os.getenv("ROOT_PAGE_ID")
base_docs_dir = os.getenv("BASE_DOCS_DIR", "docs")

#ルートページからMarkdownに変換
if __name__ == "__main__":
    #クラスのインスタンス化
    converter = NotionToMarkdownConverter(notionclient=notion, output_dir=base_docs_dir)
    if ROOT_PAGE_ID is None:
        raise ValueError("ROOT_PAGE_ID is not set in environment variables.")
    else:
        converter.run(ROOT_PAGE_ID)