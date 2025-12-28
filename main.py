# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from notion_client import Client
from notion_to_md import NotionToMarkdownConverter

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
notion = Client(auth=NOTION_TOKEN)

converter = NotionToMarkdownConverter(notionclient=notion)