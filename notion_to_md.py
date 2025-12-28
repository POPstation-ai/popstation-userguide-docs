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

    def __init__(self, notionclient, output_dir="docs", indent_unit="    "):
        self.notion = notionclient
        self.queue = []         # 未処理のページ
        self.processed_ids = set() # 処理済みID（二重処理防止）
        self.INDENT_UNIT = indent_unit

        # 出力先ディレクトリを保持(画像保存用はimagesサブディレクトリ)
        self.output_dir = output_dir
        self.image_dir = os.path.join(self.output_dir, 'images')

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
        }

    def fetch_all_blocks(self, block_id):
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

    def run(self, root_page_id):
        """変換処理のメインループ
           run が「どのページをやるか」を決め、実務担当の convert_page が「実際にファイルを作る」 
        Args:
            root_page_id (str): ルートページのNotion ID
        """
        # 出力ディレクトリを作成
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.image_dir, exist_ok=True)
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
            self.convert_page(
                page_id=page["id"],
                title=page["title"],
                file_name=page["file_name"]
            )
                
            # 処理済みリストに記録
            self.processed_ids.add(page["id"])
            
        print("--- すべての変換が終了しました ---")

    def convert_page(self, page_id, title, file_name):
        """
        1ページをMarkdownに変換するコアロジック
        Args:
            page_id (str): NotionのページID
            title (str): ページタイトル（ファイル先頭に見出しとして入れる用）
            file_name (str): 保存するMarkdownファイル名
        """
        # 1. Notionからそのページ内のブロックを全部持ってくる
        blocks = self.fetch_all_blocks(page_id)
        
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

    def blocks_to_markdown(self, block_list, depth=0):
            """
            リストを走査し、再帰とインデントを管理する
            """
            md_output = ""
            skip_indices = set()
            indent = self.INDENT_UNIT * depth

            for i, block in enumerate(block_list):
                if i in skip_indices:
                    continue

                b_type = block["type"]
                
                # --- A. 子ページ（別ファイル化）の処理 ---
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
                    md_output += self._handle_image_block(block, alt_text, depth)

                # --- C. その他の通常ブロック ---
                else:
                    # 外部の handle_single_block を呼び出す
                    # ※ handle_single_block 側でインデントを付けてもらう想定
                    md_output += self.handle_single_block(block, depth)
                    
                    # 子要素（トグルの中身やコールアウトの中身など）があれば再帰
                    if block.get("has_children"):
                        # ここで自分自身を再帰呼び出し（depthを+1）
                        children = self.notion.blocks.children.list(block_id=block["id"]).get("results", [])
                        md_output += self.blocks_to_markdown(children, depth + 1)

            return md_output

    def handle_single_block(self, block, depth=0):
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
        indent = NotionToMarkdownConverter.INDENT_UNIT * depth
        md_content = ""

        # 辞書にあれば実行、なければデフォルトの処理（フォールバック）
        handler = self.handlers.get(b_type)
        if handler:
            md_content = handler(block)
        else:
            # 知らないブロックでも中身のテキストがあれば抜き出す.別のブロックと「くっつく」のを防ぐため、改行をふたつ追加
            content = block.get(b_type, {})
            if "rich_text" in content:
                text = self.extract_text(content["rich_text"])
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
    def _handle_child_page(self, block):
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

        return f"### 📄 [{title}]({file_name})\n\n"

    def _handle_image_block(self, block, alt_text="", depth=0):
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
        relative_image_path = download_image(url, block_id, base_docs_dir=self.output_dir, image_dir=self.image_dir)
        
        # Markdown形式で返す
        return f"![{alt_text}]({relative_image_path})\n"

    def _handle_callout(self, block, **kwargs):
        """calloutブロックを処理する

        Args:
            block (object dict): Notion APIから取得した見出し1ブロックオブジェクト

        Returns:
            str: 見出し1のMarkdown形式のテキスト
        """
        callout = block.get("callout", {})
        text = self.extract_text(callout.get("rich_text", []))

        # 安全にアイコンを取得
        icon = self.get_icon(block)

        return f"> {icon} {text}\n"

    def _handle_h1_block(self, block, **kwargs):
        """見出し1ブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した見出し1ブロックオブジェクト

        Returns:
            str: 見出し1のMarkdown形式のテキスト
        """
        text = self.extract_text(block['heading_1']['rich_text'])
        return f"\n## {text}\n\n"

    def _handle_h2_block(self, block, **kwargs):
        """見出し2ブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した見出し2ブロックオブジェクト

        Returns:
            str: 見出し2のMarkdown形式のテキスト
        """
        text = self.extract_text(block['heading_2']['rich_text'])
        return f"\n### {text}\n\n"

    def _handle_h3_block(self, block, **kwargs):
        """見出し3ブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した見出し3ブロックオブジェクト
        Returns:
            str: 見出し3のMarkdown形式のテキスト
        """
        text = self.extract_text(block['heading_3']['rich_text'])
        return f"\n#### {text}\n\n"

    def _handle_paragraph_block(self, block, **kwargs):
        """段落ブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した段落ブロックオブジェクト

        Returns:
            str: 段落のMarkdown形式のテキスト
        """
        text = self.extract_text(block['paragraph']['rich_text'])
        # 【スキップ判定】特定のキーワードが含まれていたら無視する
        skip_keywords = ["トップページに戻る", "トップページへ戻る", "TOPへ戻る", "目次へ戻る"]
        if any(keyword in text for keyword in skip_keywords):
            return ""
        else:
            return f"{text}\n\n"

    def _handle_bulleted_list_item_block(self, block, **kwargs):
        """箇条書きブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した箇条書きブロックオブジェクト

        Returns:
            str: 箇条書きのMarkdown形式のテキスト
        """
        text = self.extract_text(block['bulleted_list_item']['rich_text'])
        return f"* {text}\n"

    def _handle_numbered_list_item_block(self, block, **kwargs):
        """番号付きリストブロックをMarkdown形式に変換する

        Args:
            block (object dict): Notion APIから取得した番号付きリストブロックオブジェクト
            count (int, optional): リスト番号。デフォルトは1。

        Returns:
            str: 番号付きリストのMarkdown形式のテキスト
            int: 次のリスト番号
        """
        #count = kwargs.get("count", 1) # 引数がなければ1にする
        text = self.extract_text(block['numbered_list_item']['rich_text'])
        return f"1. {text}\n"

    def _handle_column_list(block, **kwargs):
        # column_list自体は何も出力しない。
        # blocks_to_markdown の再帰処理が中身（column）を拾いに行くのを待つ。
        return ""

    def _handle_column(block, **kwargs):
        # 各列の区切りとして少し余白を入れる程度にする
        return "\n\n"

    def _get_toggle_content(self, toggle_block_id):
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
        return " ".join(texts).replace("\n", " ")

    #----------　ハンドラ内で使う関数　----------

#----------　クラス定義ここまで　----------
