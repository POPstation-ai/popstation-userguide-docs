# -*- coding: utf-8 -*-
import requests
import json
import os
from dotenv import load_dotenv
from notion_client import Client

# .envファイルを読み込む
load_dotenv()
# ロードされた環境変数を取得
notion_token = os.environ.get("NOTION_TOKEN")
# Notionクライアントを初期化
notion = Client(auth=notion_token)

# パス設定
BASE_DOCS_DIR = "docs"
IMAGE_DIR = "images"

#----------　各ハンドラ関数定義ここから　----------
def get_toggle_content(toggle_block_id):
    """トグルのタイトルではなく、その中にあるブロックのテキストだけを取得する
    Args:
        toggle_block_id (str): トグルブロックのID。
    Returns:
        str: トグル内のテキストコンテンツ。
    """
    try:
        # トグルの子要素を取得
        child_blocks = notion.blocks.children.list(block_id=toggle_block_id).get("results", [])
        extracted_texts = []
        content = ""        
        for child in child_blocks:
            # トグル内の各ブロックを処理
            # 段落ブロックのテキストを抽出
            if child["type"] == "paragraph":
                # リッチテキストは配列なのでプレーンテキストに変換
                print('paragraph found in toggle')
                content += "".join([t["plain_text"] for t in child["paragraph"]["rich_text"]])
                if content:
                    extracted_texts.append(content)
            # 中身が段落以外の場合（箇条書きなど）、必要に応じて他のタイプも処理を追加すること！

    except Exception as e:
            print(f"Error fetching toggle children: {e}")
            return ""
    
    # 抽出したテキストを改行で結合して返す
    return "\n".join(extracted_texts)

def image_block_to_markdown(block, alt_text=""):
    """画像ブロックをMarkdown形式に変換し、画像を保存する

    Args:
        block (object dict): Notion APIから取得した画像ブロックオブジェクト
        alt_text (str): 画像の代替テキスト（alt属性）

    Returns:
        str: 画像のMarkdown形式のリンク
    """
    img = block['image']
    url = img["file"]["url"] if "file" in img else img["external"]["url"]
    block_id = block['id']
    # 画像をダウンロードして保存
    relative_image_path = download_image(url, block_id)
    # Markdown形式で返す
    return f"![{alt_text}]({relative_image_path})\n"


def download_image(url, block_id):
    """画像を保存し、Markdown形式のリンクを返す（相対パス）

    Args:
        url (str): Notion APIから取得した画像の期間限定URL。
        block_id (str): 画像ブロックのID。ファイル名に使用する。

    Returns:
        str: 保存された画像の相対パス（例: 'images/abc-123.png'）。

    Raises:
        requests.exceptions.RequestException: ダウンロードに失敗した場合に発生。
    """
    os.makedirs(os.path.join(BASE_DOCS_DIR, IMAGE_DIR), exist_ok=True)
    filename = f"{block_id}.png"
    filepath = os.path.join(BASE_DOCS_DIR, IMAGE_DIR, filename)

    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(filepath, 'wb') as f: #画像をバイナリで保存
            # 1KBずつ書き込み
            for chunk in response.iter_content(1024):
                f.write(chunk)
    
    return f"{IMAGE_DIR}/{filename}"


def extract_text(rich_text_array):
    """Notionのリッチテキスト配列を単純な文字列に変換
    Args:
        rich_text_array (object list): Notion APIから取得したリッチテキストの配列
    Returns:
        str: プレーンテキストの結合結果
    """
    return "".join([t["plain_text"] for t in rich_text_array]) if rich_text_array else ""


def handle_callout(block, **kwargs):
    """calloutブロックを処理する

    Args:
        block (object dict): Notion APIから取得した見出し1ブロックオブジェクト

    Returns:
        str: 見出し1のMarkdown形式のテキスト
    """
    text = extract_text(block["callout"]["rich_text"])
    icon = block["callout"].get("icon", {}).get("emoji", "💡")

    return f"> {icon} {text}\n"



def handle_h1_block(block, **kwargs):
    """見出し1ブロックをMarkdown形式に変換する

    Args:
        block (object dict): Notion APIから取得した見出し1ブロックオブジェクト

    Returns:
        str: 見出し1のMarkdown形式のテキスト
    """
    text = extract_text(block['heading_1']['rich_text'])
    return f"## {text}\n\n"

def handle_h2_block(block, **kwargs):
    """見出し2ブロックをMarkdown形式に変換する

    Args:
        block (object dict): Notion APIから取得した見出し2ブロックオブジェクト

    Returns:
        str: 見出し2のMarkdown形式のテキスト
    """
    text = extract_text(block['heading_2']['rich_text'])
    return f"### {text}\n\n"

def handle_h3_block(block, **kwargs):
    """見出し3ブロックをMarkdown形式に変換する

    Args:
        block (object dict): Notion APIから取得した見出し3ブロックオブジェクト
    Returns:
        str: 見出し3のMarkdown形式のテキスト
    """
    text = extract_text(block['heading_3']['rich_text'])
    return f"#### {text}\n\n"

def handle_paragraph_block(block, **kwargs):
    """段落ブロックをMarkdown形式に変換する

    Args:
        block (object dict): Notion APIから取得した段落ブロックオブジェクト

    Returns:
        str: 段落のMarkdown形式のテキスト
    """
    text = extract_text(block['paragraph']['rich_text'])
    return f"{text}\n\n"

def handle_bulleted_list_item_block(block, **kwargs):
    """箇条書きブロックをMarkdown形式に変換する

    Args:
        block (object dict): Notion APIから取得した箇条書きブロックオブジェクト

    Returns:
        str: 箇条書きのMarkdown形式のテキスト
    """
    text = extract_text(block['bulleted_list_item']['rich_text'])
    return f"* {text}\n"

def handle_numbered_list_item_block(block, **kwargs):
    """番号付きリストブロックをMarkdown形式に変換する

    Args:
        block (object dict): Notion APIから取得した番号付きリストブロックオブジェクト
        count (int, optional): リスト番号。デフォルトは1。

    Returns:
        str: 番号付きリストのMarkdown形式のテキスト
        int: 次のリスト番号
    """
    #count = kwargs.get("count", 1) # 引数がなければ1にする
    text = extract_text(block['numbered_list_item']['rich_text'])
    return f"1. {text}\n"
#----------　各ハンドラ関数定義ここまで　----------

# 処理関数を辞書で管理（拡張しやすい！）
handlers = {
    "heading_1": handle_h1_block,
    "heading_2": handle_h2_block,
    "paragraph": handle_paragraph_block,
    "bulleted_list_item": handle_bulleted_list_item_block,
    "numbered_list_item": handle_numbered_list_item_block,

    #"image": handle_image_block,  # 画像は別関数で処理
    # 新しいブロックが増えたらここに1行足すだけ
}

def block_to_markdown(block):
    """1つのブロックオブジェクトから、Markdownを作成(imgae以外)

    Args:
        block (object dict): Notion APIから取得したブロックオブジェクト

    Returns:
        str (markdown): markdown形式のテキスト

    Raises:
        
    """
    b_type = block['type']
    md = "" # 最終的に返すMarkdownテキストの初期化

    # 辞書にあれば実行、なければデフォルトの処理（フォールバック）
    handler = handlers.get(b_type)
    if handler:
        md = handler(block)
    else:
        # 知らないブロックでも中身のテキストがあれば抜き出す
        content = block.get(b_type, {})
        if "rich_text" in content:
            text = extract_text(content["rich_text"])
            print(f"⚠️  Unknown block type '{b_type}': Text extracted anyway.")
            #return f"{text}\n\n"
            md = f"{text}\n\n"
        else:
            # テキストすらない場合は空文字を返して無視
            print(f"❌  Unsupported block type '{b_type}': Skipped.")
            md = ""

    return md

def handle_single_block(block, depth=0):
    """1つのブロックオブジェクトから、Markdownを作成(imgae以外)

    Args:
        block (object dict): Notion APIから取得したブロックオブジェクト
        depth (int): ブロックの深さ（ネストレベル）

    Returns:
        str (markdown): markdown形式のテキスト

    Raises:
        
    """
    md = block_to_markdown(block)
    # ネストレベルに応じてインデントを追加
    b_type = block['type']
    indent = "  " * depth
    md_content = ""

    # 辞書にあれば実行、なければデフォルトの処理（フォールバック）
    handler = handlers.get(b_type)
    if handler:
        md_content = handler(block)
    else:
        # 知らないブロックでも中身のテキストがあれば抜き出す.別のブロックと「くっつく」のを防ぐため、改行をふたつ追加
        content = block.get(b_type, {})
        if "rich_text" in content:
            text = extract_text(content["rich_text"])
            print(f"⚠️  Unknown block type '{b_type}': Text extracted anyway.")
            #return f"{text}\n\n"
            md_content = f"{text}\n\n"
        else:
            # テキストすらない場合は空文字を返して無視
            print(f"❌  Unsupported block type '{b_type}': Skipped.")
            md_content = ""

    # 各行の先頭に現在の深さのインデントを付与
    content = "".join([f"{indent}{line}\n" for line in md_content.splitlines()])

    return content


def fetch_all_blocks(block_id):
    """指定したidのブロック以下の全てのブロックを取得する
    Args:
        block_id (str): NotionのブロックID

    Returns:
        object list: ブロックオブジェクトのリスト
    """
    #初期化
    blocks = []
    cursor = None

    while True:
        return_data = notion.blocks.children.list(
            block_id=block_id,
            start_cursor=cursor
        )
        #結果を追加
        blocks.extend(return_data['results'])
        if not return_data['has_more']:
            break
        cursor = return_data['next_cursor']

    return blocks

def convert_blocks_to_markdown(block_list, depth=0):
    """ ブロックのリストを走査し、画像+トグルペア等を考慮しながらMarkdown化する
    Args:
        block_id (str): NotionのブロックID

    Returns:
        object list: ブロックオブジェクトのリスト    
    """
    md = ""
    skip_indices = set()
    indent = "    " * depth
    
    for i, block in enumerate(block_list):
        if i in skip_indices: continue
        b_type = block["type"]
        
        if b_type == "image":            
            # 画像+トグルのペア処理
            # 次のブロックが存在し、かつトグルであるか確認（先読み）
            if i + 1 < len(block_list) and block_list[i+1]["type"] == "toggle":
                # トグルの「中身」を別関数で取得
                alt_text = get_toggle_content(block_list[i+1]["id"])
                # トグルを消費したのでスキップ登録
                skip_indices.add(i + 1)
            # 画像のMarkdown変換（引数にalt_textを渡せるように関数を調整）
            md += image_block_to_markdown(block, alt_text)                
            
        else:
            # image以外のブロック処理
            md += handle_single_block(block)

            # ネストされた子ブロックがあれば再帰的に処理
            if block.get("has_children"):
                child_blocks = fetch_all_blocks(block["id"])
                md += convert_blocks_to_markdown(child_blocks, depth + 1)            
    return md



def convert_page_to_md(page_id, output_filename):
    """指定のnotionページをMarkdownに変換し、保存する

    Args:
        page_id (str): NotionのページID
        output_filename (str): 出力するMarkdownファイル名

    Returns:
        None
    """
    print(f"Connections notion page: {page_id}")
    blocks = fetch_all_blocks(page_id)
    md_lines = ""
    # 処理済みのインデックスを記録するセット（画像下のImage Metaトグルを二重出力しないため）
    skip_indices = set()

    for i, block in enumerate(blocks):
        #md = get_markdown_from_block(block)
        #md_lines += md + "\n"
        if i in skip_indices:
                    continue
        
        b_type = block['type']
        # --- 画像ブロックの特別処理 ---
        if b_type == "image":
            alt_text = ""
            # 次のブロックが存在し、かつトグルであるか確認（先読み）
            if i + 1 < len(blocks) and blocks[i+1]["type"] == "toggle":
                # トグルの「中身」を別関数で取得
                alt_text = get_toggle_content(blocks[i+1]["id"])
                # トグルは画像の一部として処理したので、次のループではスキップ
                skip_indices.add(i + 1)
            
            # 画像のMarkdown変換（引数にalt_textを渡せるように関数を調整）
            md_lines += image_block_to_markdown(block, alt_text)
                    
        else:
            # image以外のブロック処理
            md_lines += block_to_markdown(block)

    #ファイルに保存
    os.makedirs(BASE_DOCS_DIR, exist_ok=True)
    save_path = os.path.join(BASE_DOCS_DIR, f"{output_filename}.md")
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(md_lines)

    print(f"🎉 Success! Generated: {save_path}")
    return
