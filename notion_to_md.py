# -*- coding: utf-8 -*-
import requests
import os
import re

# .envファイルを読み込む
#load_dotenv()
# ロードされた環境変数を取得
#notion_token = os.environ.get("NOTION_TOKEN")
# Notionクライアントを初期化
#notion = Client(auth=notion_token)

# パス設定
#BASE_DOCS_DIR = "docs"
#IMAGE_DIR = "images"

def get_icon(block):
    """calloutブロックからアイコン（絵文字）を取得する
    Args:
        block (object dict): Notion APIから取得したcalloutブロックオブジェクト
    Returns:
        str: アイコンの絵文字、存在しない場合はデフォルトの絵文字
    """    
    callout = block.get("callout", {})
    icon_ptr = callout.get("icon")
    
    # icon_ptr が辞書であることを確認してから中身を見る
    if isinstance(icon_ptr, dict) and icon_ptr.get("type") == "emoji":
        return icon_ptr.get("emoji", "💡")
    
    return "💡" # デフォルト

def extract_text(rich_text_array):
    """Notionのリッチテキスト配列を単純な文字列に変換
    Args:
        rich_text_array (object list): Notion APIから取得したリッチテキストの配列
    Returns:
        str: プレーンテキストの結合結果
    """
    return "".join([t["plain_text"] for t in rich_text_array]) if rich_text_array else ""

def download_file(url, save_path):
    """ファイルを保存するユーティリティ関数

    Args:
        url (str): ダウンロード元のURL
        save_path (str): 保存先のファイルパス

    Returns:
        bool: ダウンロード成功ならTrue、失敗ならFalse

    Raises:
        requests.exceptions.RequestException: ダウンロードに失敗した場合に発生。
    """
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_path, 'wb') as f: #ファイルをバイナリで保存
            # 1KBずつ書き込み
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return True
    return False

def download_image(url, block_id, base_docs_dir="docs", image_dir="images"):
    """画像を保存し、Markdown形式のリンクを返す（相対パス）

    Args:
        url (str): Notion APIから取得した画像の期間限定URL。
        block_id (str): 画像ブロックのID。ファイル名に使用する。

    Returns:
        str: 保存された画像の相対パス（例: 'images/abc-123.png'）。

    Raises:
        requests.exceptions.RequestException: ダウンロードに失敗した場合に発生。
    """
    os.makedirs(os.path.join(base_docs_dir, image_dir), exist_ok=True)
    filename = f"{block_id}.png"
    filepath = os.path.join(base_docs_dir, image_dir, filename)

    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(filepath, 'wb') as f: #画像をバイナリで保存
            # 1KBずつ書き込み
            for chunk in response.iter_content(1024):
                f.write(chunk)
    
    return f"{NotionToMarkdownConverter.IMAGE_DIR}/{filename}"

#----------　クラス定義ここから　----------
class NotionToMarkdownConverter:
    # クラス全体で共通の設定値（定数）
    #INDENT_UNIT = "    "  # 半角スペース4つ。ここを書き換えるだけで全ページに反映される
    # パス設定
    BASE_DOCS_DIR = "docs"
    IMAGE_DIR = "images"
    FILE_DIR = "files"

    def __init__(self, notionclient, output_dir="docs", indent_unit="    "):
        self.notion = notionclient
        self.queue = []         # 未処理のページ
        self.processed_ids = set() # 処理済みID（二重処理防止）
        self.INDENT_UNIT = indent_unit

        # 出力先ディレクトリを保持(画像保存用はimagesサブディレクトリ)
        self.output_dir = output_dir
        self.image_dir = os.path.join(self.output_dir, self.IMAGE_DIR)
        self.file_dir = os.path.join(self.output_dir, self.FILE_DIR)

        # ハンドラを辞書形式で持っておく 未完成
        self.handlers = {
            "heading_1": self._handle_h1_block,
            "heading_2": self._handle_h2_block,
            "heading_3": self._handle_h3_block,
            "paragraph": self._handle_paragraph_block,
            "bulleted_list_item": self._handle_bulleted_list_item_block,
            "numbered_list_item": self._handle_numbered_list_item_block,
            "callout": self._handle_callout,
            "column_list": self._handle_column_list,
            "column": self._handle_column,
            "file": self._handle_file,
            "table": self._handle_table_block,
            "table_row": self._ignore_block,
            "divider": self._handle_divider,
        }

    def run(self, root_page_id):
        """変換処理のメインループ
           run が「どのページをやるか」を決め、実務担当の convert_page が「実際にファイルを作る」 
        Args:
            root_page_id (str): ルートページのNotion ID
        """
        # 出力ディレクトリを作成
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.image_dir, exist_ok=True)
        os.makedirs(self.file_dir, exist_ok=True)
        print(f"📁 出力先: {self.output_dir}")

        # 最初に親ページ（index）をキューに入れる
        self.queue.append({
            "id": root_page_id, 
            "title": "index", 
            "file_name": "index.md"
        })
        
        while self.queue:
            # キューから1ページ取り出し
            page = self.queue.pop(0)
            
            # すでに処理してたらスキップ
            if page["id"] in self.processed_ids:
                continue
                
            print(f">>>🚀 処理中: {page['title']}")
            
            # ページを変換して保存
            # child_pageがあれば self.queue に追加
            self._convert_page(
                page_id=page["id"],
                title=page["title"],
                file_name=page["file_name"]
            )
                
            # 処理済みリストに記録
            self.processed_ids.add(page["id"])
            
        print("--- すべての変換が終了しました ---")

    def _fetch_all_blocks(self, block_id):
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
            return_data = self.notion.blocks.children.list(
                block_id=block_id,
                start_cursor=cursor
            )
            #結果を追加
            blocks.extend(return_data['results'])
            if not return_data['has_more']:
                break
            cursor = return_data['next_cursor']

        return blocks

    def _convert_page(self, page_id, title, file_name):
        """
        1ページをMarkdownに変換するコアロジック
        Args:
            page_id (str): NotionのページID
            title (str): ページタイトル（ファイル先頭に見出しとして入れる用）
            file_name (str): 保存するMarkdownファイル名
        """
        # 1. Notionからそのページ内のブロックを全部持ってくる
        blocks = self._fetch_all_blocks(page_id)
        
        # 2. ブロックの塊をMarkdown文字列に変換する
        # (ここで self.indent_unit を使い、最初はインデントなし "" で開始)
        markdown_text = self.blocks_to_markdown(blocks, current_indent="")
        
        # 3. ファイルとして書き出す
        # docs フォルダがない場合に備えて os.makedirs を入れておくと親切
        import os
        os.makedirs("docs", exist_ok=True)
        
        save_path = os.path.join(self.output_dir, file_name)
        with open(save_path, "w", encoding="utf-8") as f:
            # 必要なら先頭にタイトルを見出しとして入れる
            f.write(f"# {title}\n\n")
            f.write(markdown_text)
            
        print(f"   ✅ 保存完了: {save_path}")

    def blocks_to_markdown(self, block_list, current_indent=""):
            """
            リストを走査し、再帰とインデントを管理する
            """
            md_output = ""
            skip_indices = set()
            indent = current_indent + self.INDENT_UNIT

            for i, block in enumerate(block_list):
                if i in skip_indices:
                    continue

                b_type = block["type"]
                
                # --- A. 子ページ（別ファイル化）の処理 再帰ではなく queue に積む---
                if b_type == "child_page":
                    # インデントを考慮してリンクを出力
                    # queue登録がhandler内で行われる
                    link_text = self._handle_child_page(block)
                    md_output += f"{indent}{link_text}"

                # --- B. 画像とトグルの特殊ペア処理 ---
                elif b_type == "image":
                    alt_text = ""
                    if i + 1 < len(block_list) and block_list[i+1]["type"] == "toggle":
                        alt_text = self._get_toggle_content(block_list[i+1]["id"])
                        skip_indices.add(i + 1)
                    md_output += self._handle_image_block(block, alt_text, current_indent=indent)
                
                # --- C. テーブル（子要素の row を一括で料理する） ---                
                elif b_type == "table":
                    md_output += self._handle_table_block(block, current_indent=indent)

                # --- D. その他の通常ブロック ---
                else:
                    # 外部の handle_single_block を呼び出す
                    # ※ handle_single_block 側でインデントを付けてもらう想定
                    md_output += self.handle_single_block(block, current_indent=indent)
                    
                    # 子要素（トグルの中身やコールアウトの中身など）があれば再帰
                    if block.get("has_children"):
                        # ここで自分自身を再帰呼び出し（depthを+1）
                        children = self.notion.blocks.children.list(block_id=block["id"]).get("results", [])
                        md_output += self.blocks_to_markdown(children, current_indent=indent)

            return md_output

    def handle_single_block(self, block, current_indent=""):
        """1つのブロックオブジェクトから、Markdownを作成(imgae以外)

        Args:
            block (object dict): Notion APIから取得したブロックオブジェクト
            depth (int): ブロックの深さ（ネストレベル）

        Returns:
            str (markdown): markdown形式のテキスト

        Raises:
            
        """
        # ネストレベルに応じてインデントを追加
        b_type = block['type']
        indent = self.INDENT_UNIT + current_indent
        md_content = ""

        # 辞書にあれば実行、なければデフォルトの処理（フォールバック）
        handler = self.handlers.get(b_type)
        if handler:
            md_content = handler(block, current_indent=indent)
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

        if not md_content:
            return ""
        else:
            # 各行の先頭に現在の深さのインデントを付与
            return "".join([f"{indent}{line}\n" for line in md_content.splitlines()])

    #----------　ハンドラ関数開始　----------
    def _ignore_block(self, block):
        """無視するブロックのハンドラ関数
        Args:
            block (object dict): Notion APIから取得した無視するブロックオブジェクト

        Returns:
            str: 空文字列
        """
        return ""
    
    def _handle_table_block(self, block, current_indent=""):
        """tableブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得したtableブロックオブジェクト

        Returns:
            str: tableのMarkdown形式のテキスト
        """
        table_id = block["id"]
        # 1. 全ての行を取得
        rows = self._fetch_all_blocks(table_id)
        if not rows:
            return ""

        md_table = ""
        column_count = block["table"]["table_width"]
        #has_column_header = block["table"]["has_column_header"]    #左端を強調したかったら生かす

        for i, row in enumerate(rows):
            # 2. 各セルのテキストを抽出
            cells = row["table_row"]["cells"]
            # 各セルの内容を [text, text, text] のリストにする
            cell_texts = [extract_text(c) for c in cells]
            
            # Markdownの行を作成: | cell1 | cell2 |
            formatted_row = f"{current_indent}| " + " | ".join(cell_texts) + " |\n"
            md_table += formatted_row

            # 3. 1行目の後にセパレーター (|---|---|) を挿入
            if i == 0:
                separator = f"{current_indent}| " + " | ".join(["---"] * column_count) + " |\n"
                md_table += separator

        return md_table + "\n"

    def _handle_child_page(self, block, current_indent=""):
        """
        child_pageブロックを処理するハンドラ関数
        子ページを見つけたら、リンクを返しつつキューに追加する
        """
        title = block["child_page"]["title"]
        page_id = block["id"]
        
        safe_title = re.sub(r'[\\/*?:"<>|]', '_', title)
        file_name = f"{safe_title}.md"

        # 自分の「持ち物（queue）」に記録する
        if page_id not in self.processed_ids:
            self.queue.append({
                "id": page_id,
                "title": title,
                "file_name": file_name
            })

        return f"{current_indent}### 📄 [{title}]({file_name})\n\n"

    def _handle_image_block(self, block, alt_text="", current_indent=""):
        """画像ブロックをMarkdown形式に変換し、画像を保存する

        Args:
            block (object dict): Notion APIから取得した画像ブロックオブジェクト
            alt_text (str): 画像の代替テキスト（alt属性）

        Returns:
            str: 画像のMarkdown形式のリンク
        """
        img = block['image']
        url = img["file"]["url"] if "file" in img else img["external"]["url"]
        #block_id = 
        # 画像をダウンロードして保存
        filename = f"{block['id']}.png"
        filepath = os.path.join(self.image_dir, filename)
        #relative_image_path = download_image(url, block_id, base_docs_dir=self.output_dir, image_dir=self.image_dir)
        relative_image_path = download_file(url, filepath)
        
        # Markdown形式で返す
        return f"{current_indent}![{alt_text}]({relative_image_path})\n"

    def _handle_file(self, block, current_indent=""):
            file_data = block.get("file", {})
            if not file_data:
                return ""

            # URLの取得
            file_url = file_data.get("file", {}).get("url")
            # 元のファイル名をNotion側から取得できないことが多いため、IDを名前にする
            # 可能ならキャプションから名前を取る
            caption_text = extract_text(file_data.get("caption", []))
            if caption_text:
                file_name = caption_text
            else:
                file_name = f"{block['id']}"

            save_path = os.path.join(self.file_dir, f"{file_name}.pdf")

            # ダウンロード実行
            if download_file(file_url, save_path):
                # Markdownでは [ファイル名](パス) のリンク形式にする
                # 💡 RAG用には「添付ファイル：PDF」などと書いておくとAIが認識しやすいです
                return f"{current_indent}[📎 添付PDF: {file_name}](files/{file_name})\n\n"
            
            return f"{current_indent}[📎 添付PDF(リンク切れ)]({file_url})\n\n"

    def _handle_callout(self, block, current_indent=""):
        """calloutブロックを処理する

        Args:
            block (object dict): Notion APIから取得した見出し1ブロックオブジェクト

        Returns:
            str: 見出し1のMarkdown形式のテキスト
        """
        callout = block.get("callout", {})
        text = extract_text(callout.get("rich_text", []))

        # 安全にアイコンを取得
        icon = get_icon(block)

        return f"{current_indent}> {icon} {text}\n"

    def _handle_h1_block(self, block, current_indent=""):
        """見出し1ブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した見出し1ブロックオブジェクト

        Returns:
            str: 見出し1のMarkdown形式のテキスト
        """
        text = extract_text(block['heading_1']['rich_text'])
        return f"{current_indent}\n## {text}\n\n"

    def _handle_h2_block(self, block, current_indent=""):
        """見出し2ブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した見出し2ブロックオブジェクト

        Returns:
            str: 見出し2のMarkdown形式のテキスト
        """
        text = extract_text(block['heading_2']['rich_text'])
        return f"{current_indent}\n### {text}\n\n"

    def _handle_h3_block(self, block, current_indent=""):
        """見出し3ブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した見出し3ブロックオブジェクト
        Returns:
            str: 見出し3のMarkdown形式のテキスト
        """
        text = extract_text(block['heading_3']['rich_text'])
        return f"{current_indent}\n#### {text}\n\n"

    def _handle_paragraph_block(self, block, current_indent=""):
        """段落ブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した段落ブロックオブジェクト

        Returns:
            str: 段落のMarkdown形式のテキスト
        """
        text = extract_text(block['paragraph']['rich_text'])
        # 【スキップ判定】特定のキーワードが含まれていたら無視する
        skip_keywords = ["トップページに戻る", "トップページへ戻る", "TOPへ戻る", "目次へ戻る"]
        if any(keyword in text for keyword in skip_keywords):
            return ""
        else:
            return f"{current_indent}{text}\n\n"

    def _handle_bulleted_list_item_block(self, block, current_indent=""):
        """箇条書きブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した箇条書きブロックオブジェクト

        Returns:
            str: 箇条書きのMarkdown形式のテキスト
        """
        text = extract_text(block['bulleted_list_item']['rich_text'])
        return f"{current_indent}* {text}\n"

    def _handle_numbered_list_item_block(self, block, current_indent=""):
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
        return f"{current_indent}1. {text}\n"

    def _handle_column_list(self, block, current_indent=""):
        # column_list自体は何も出力しない。
        # blocks_to_markdown の再帰処理が中身（column）を拾いに行くのを待つ。
        return ""

    def _handle_column(self, block, current_indent=""):
        # 各列の区切りとして少し余白を入れる程度にする
        return f"{current_indent}\n\n"

    def _get_toggle_content(self, toggle_block_id, current_indent=""):
        """トグルのタイトルではなく、その中にあるブロックのテキストだけを取得する
        Args:
            toggle_block_id (str): トグルブロックのID。
        Returns:
            str: トグル内のテキストコンテンツ。
        """
        children = self._fetch_all_blocks(toggle_block_id)
        # 各ブロックのテキストを抽出して結合（改行はスペースに置換）
        texts = []
        for child in children:
            c_type = child["type"]
            if "rich_text" in child[c_type]:
                # 外側の共通関数 extract_text を利用
                texts.append(extract_text(child[c_type]["rich_text"]))
        return f"{current_indent} {" ".join(texts).replace("\n", " ")}" 

    def _handle_divider(self, block, current_indent=""):
            # インデントを考慮しつつ、水平線を引く
            # 前後に空行をしっかり入れるのがMarkdownを壊さないコツです
            return f"{current_indent}---\n\n"

    def _handle_code(self, block, current_indent=""):
        code_obj = block.get("code", {})
        
        # 1. コード本体を取得
        code_text = extract_text(code_obj.get("rich_text", []))
        
        # 2. 言語名を取得（小文字化して空白を詰める）
        lang = code_obj.get("language", "plain text").lower().replace(" ", "")
        
        # 3. キャプションがあれば取得
        caption = extract_text(code_obj.get("caption", []))
        caption_md = f"{current_indent}*caption: {caption}*\n" if caption else ""

        # 4. 組み立て
        md = f"{current_indent}```{lang}\n"
        md += f"{code_text}\n"
        md += f"{current_indent}```\n"
        md += caption_md  # キャプションがあれば下に添える
        md += "\n"
        
        return md

    #----------　ハンドラ内で使う関数　----------

#----------　クラス定義ここまで　----------
