import { Client } from "@notionhq/client";
import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";
import axios from "axios"; // Pythonのrequestsの代わり

dotenv.config();

// --- ユーティリティ関数 ---
async function downloadFile(url: string, filePath: string): Promise<boolean> {
  try {
    // 保存先フォルダがなければ作成（これ重要！）
    const dir = path.dirname(filePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    const response = await axios({
      url,
      method: "GET",
      responseType: "stream",
      timeout: 5000, // 5秒でタイムアウトさせる
    });

    return new Promise((resolve, reject) => {
      const writer = fs.createWriteStream(filePath);
      response.data.pipe(writer);
      writer.on("finish", () => resolve(true));
      writer.on("error", (err) => {
        console.error(`❌ 書き込みエラー: ${filePath}`, err.message);
        resolve(false); // 失敗しても止まらないように resolve(false)
      });
    });
  } catch (error: any) {
    console.error(
      `❌ Dounload failed: ${url.substring(0, 50)}...`,
      error.message,
    );
    return false; // エラーが起きても false を返して、メインのループを続行させる
  }
}

// handlerの型定義
type BlockHandler = (block: any, indent: string) => Promise<string> | string;

class NotionToMarkdownConverter {
  // --Handler化　途中
  // 2. ハンドラ辞書の定義
  private handlers: Record<string, BlockHandler> = {
    heading_1: (b) => `## ${this.extractText(b.heading_1.rich_text)}\n\n`,
    heading_2: (b) => `### ${this.extractText(b.heading_2.rich_text)}\n\n`,
    heading_3: (b) => `#### ${this.extractText(b.heading_3.rich_text)}\n\n`,
    paragraph: (b) => {
      const text = this.extractText(b.paragraph.rich_text);
      const skipKeywords = ["トップページに戻る", "TOPへ戻る"];
      return skipKeywords.some((k) => text.includes(k)) ? "" : `${text}\n\n`;
    },
    bulleted_list_item: (b) =>
      `* ${this.extractText(b.bulleted_list_item.rich_text)}\n`,
    callout: (b) =>
      `> ${this.getIcon(b)} ${this.extractText(b.callout.rich_text)}\n\n`,
    // child_page, image, file は特殊ロジックが必要なので個別にメソッド化して登録
    child_page: (b) => this.handleChildPage(b),
    image: (b, i) => this.handleImage(b, i), // 引数を渡せるように調整
    file: (b) => this.handleFile(b),
  };

  /**
   * メインのループ処理
   */
  private async blocksToMarkdown_Handler(
    blockList: any[],
    currentIndent: string,
  ): Promise<string> {
    let mdOutput = "";
    const skipIndices = new Set<number>();

    for (let i = 0; i < blockList.length; i++) {
      if (skipIndices.has(i)) continue;

      const block = blockList[i];
      const bType = block.type;

      // --- 特殊ロジック：画像とトグルのペアリング ---
      if (
        bType === "image" &&
        i + 1 < blockList.length &&
        blockList[i + 1].type === "toggle"
      ) {
        mdOutput += await this.handleImageWithToggle(block, blockList[i + 1]);
        skipIndices.add(i + 1); // 次のトグルをスキップ
        continue;
      }

      // --- ハンドラによる通常処理 ---
      const handler = this.handlers[bType];
      if (handler) {
        mdOutput += await handler(block, currentIndent);
      } else {
        // --- フォールバック：未知のブロックからテキスト抽出 ---
        const content = block[bType];
        if (content && content.rich_text) {
          mdOutput += `${this.extractText(content.rich_text)}\n\n`;
          console.log(`⚠️ Unknown block '${bType}': Text extracted.`);
        }
      }

      // --- 子要素の再帰処理 ---
      // child_page自体は別ファイルになるのでここでは掘らない
      if (block.has_children && bType !== "child_page" && !skipIndices.has(i)) {
        const children = await this.fetchAllBlocks(block.id);
        mdOutput += await this.blocksToMarkdown_Handler(
          children,
          currentIndent + "  ",
        );
      }
    }
    return mdOutput;
  }

  private handleChildPage(block: any): string {
    const childTitle = block.child_page.title;
    if (!childTitle) return "";

    const safeTitle = childTitle.replace(/[\\/*?:"<>|]/g, "_").trim();
    const fileName = `${safeTitle}.md`;

    if (!this.processedIds.has(block.id)) {
      this.queue.push({ id: block.id, title: childTitle, fileName });
    }
    return `\n\n### 📄 [${childTitle}](./${fileName})\n\n`;
  }

  /**
   * Fileブロック（PDF等）を処理するハンドラ
   * @param block Notionのfileブロック
   * @returns Markdown形式のリンク文字列
   */
  private async handleFile(block: any): Promise<string> {
    const fileData = block.file;
    if (!fileData) return "";

    // 1. URLの取得（外部URLかNotionホストのファイルか）
    const fileUrl =
      fileData.type === "external" ? fileData.external.url : fileData.file.url;

    // 2. ファイル名の決定
    // キャプションがあればそれを使い、なければブロックIDをファイル名にする
    const caption = this.extractText(fileData.caption);
    const rawFileName = caption ? caption.trim() : block.id;

    // ファイル名から不正な文字を除去し、スペースをアンダースコアに置換
    const safeBaseName = rawFileName
      .replace(/[\\/*?:"<>|]/g, "_")
      .replace(/\s+/g, "_");

    // 拡張子の処理（Notion側で拡張子が含まれていない場合を考慮して.pdfを付与）
    const fileName = safeBaseName.toLowerCase().endsWith(".pdf")
      ? safeBaseName
      : `${safeBaseName}.pdf`;

    const filePath = path.join(this.fileDir, fileName);

    // 3. ファイルのダウンロード実行
    try {
      const success = await downloadFile(fileUrl, filePath);

      if (success) {
        console.log(`   📎 ファイル保存完了: ${fileName}`);
        // AIが「これは添付資料だ」と認識しやすいように絵文字とラベルを付与
        return `\n\n[📎 添付PDF: ${fileName}](files/${fileName})\n\n`;
      } else {
        console.error(`   ❌ ファイルダウンロード失敗: ${fileName}`);
        return `\n\n> ⚠️ 添付ファイル（${fileName}）のダウンロードに失敗しました。\n\n`;
      }
    } catch (error) {
      console.error(`   🚨 File handler error:`, error);
      return "";
    }
  }

  private async handleImageWithToggle(
    imageBlock: any,
    toggleBlock: any,
  ): Promise<string> {
    // 既存の画像保存ロジックを実行
    const imgMd = await this.handleImage(imageBlock, "");
    // トグルの中身をMeta情報として取得
    const metaContent = await this.getToggleContent(toggleBlock.id);

    return `${imgMd}> 🤖 **Image Meta**: ${metaContent}\n\n`;
  }

  private async handleImage(block: any, indent: string): Promise<string> {
    const img = block.image;
    const url = img.type === "external" ? img.external.url : img.file.url;
    const fileName = `${block.id}.png`;
    const filePath = path.join(this.imageDir, fileName);

    await downloadFile(url, filePath); // ダウンロード実行

    const captionText =
      img.caption?.length > 0 ? this.extractText(img.caption) : "";
    const imageAlt = captionText || "画像資料";

    return `\n\n![${imageAlt}](images/${fileName})\n`;
  }

  // Hander化　ここまで

  private notion: Client;
  private queue: Array<{ id: string; title: string; fileName: string }> = [];
  private processedIds = new Set<string>();
  private outputDir: string;
  private imageDir: string;
  private fileDir: string;
  private INDENT_UNIT = "    ";
  private readonly DEFAULT_ICON = "💡";

  constructor(token: string, outputDir = "docs") {
    this.notion = new Client({ auth: token });
    this.outputDir = outputDir;
    this.imageDir = path.join(this.outputDir, "images");
    this.fileDir = path.join(this.outputDir, "files");
  }

  async run(rootPageId: string) {
    // フォルダ作成
    [this.outputDir, this.imageDir, this.fileDir].forEach((dir) => {
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    });

    console.log(`📁 出力先: ${this.outputDir}`);

    // 初回キュー登録
    this.queue.push({
      id: rootPageId,
      title: "index",
      fileName: "index.md",
    });

    while (this.queue.length > 0) {
      const page = this.queue.shift()!;

      if (this.processedIds.has(page.id)) continue;

      console.log(`>>>🚀 処理中: ${page.title}`);
      await this.convertPage(page.id, page.title, page.fileName);
      this.processedIds.add(page.id);
    }

    console.log("--- すべての変換が終了しました ---");
  }

  private getIcon(block: any): string {
    // Optional Chaining (?.) を使って深く掘り下げる
    const icon = block?.callout?.icon;

    // 型が "emoji" かつ emoji プロパティが存在する場合のみ返す
    if (icon?.type === "emoji" && icon.emoji) {
      return icon.emoji;
    }

    // アイコンが外部画像 (external) や ファイル (file) の場合は
    // Markdownで扱いづらいため、デフォルトの絵文字を返す
    return this.DEFAULT_ICON;
  }

  private extractText(richTextArray: any[]): string {
    if (!richTextArray || !Array.isArray(richTextArray)) return "";

    return richTextArray
      .map((t: any) => {
        const textContent = t.plain_text;
        let linkUrl = t.href;

        if (linkUrl) {
          // 1. Notion内部リンクの判定 (URLにハイフンなしの32文字IDが含まれる場合)
          // 例: https://www.notion.so/My-Page-abc123456789...
          const notionPageIdMatch = linkUrl.match(/\/([a-f0-9]{32})/);

          if (notionPageIdMatch) {
            const pageId = notionPageIdMatch[1];
            // 2. 自分のサイト内の相対パスに変換
            // MkDocsの標準的なディレクトリ構造に合わせて [テキスト](../pageId/) に書き換える
            linkUrl = `../${pageId}/`;
          }

          return `[${textContent}](${linkUrl})`;
        }

        return textContent;
      })
      .join("");
  }

  // 追加：トグルの「中身」をテキストとして吸い出す関数
  private async getToggleContent(toggleBlockId: string): Promise<string> {
    // Notion APIで子ブロックをすべて取得
    const response = await this.notion.blocks.children.list({
      block_id: toggleBlockId,
    });

    const children = response.results;
    const texts: string[] = [];

    for (const child of children) {
      const cType = (child as any).type;
      const content = (child as any)[cType];

      // テキストが含まれるブロック（paragraph, bulleted_list_item等）から文字を抽出
      if (content && content.rich_text) {
        texts.push(this.extractText(content.rich_text));
      }
    }
    // 改行をスペースに変えて1行にまとめる
    return texts.join(" ").replace(/\n/g, " ").trim();
  }

  private async fetchAllBlocks(blockId: string): Promise<any[]> {
    const blocks: any[] = [];
    let cursor: string | undefined = undefined;

    while (true) {
      const response: any = await this.notion.blocks.children.list({
        block_id: blockId,
        start_cursor: cursor,
      });
      blocks.push(...response.results);
      if (!response.has_more) break;
      cursor = response.next_cursor;
    }
    return blocks;
  }

  private async convertPage(pageId: string, title: string, fileName: string) {
    const blocks = await this.fetchAllBlocks(pageId);
    // DEBUG: ブロック数を表示
    console.log(`DEBUG: Page [${title}] has ${blocks.length} blocks.`); // これを追加

    const markdownText = await this.blocksToMarkdown(blocks, "");

    const savePath = path.join(this.outputDir, fileName);
    const content = `# ${title}\n\n${markdownText}`;
    fs.writeFileSync(savePath, content, "utf-8");

    console.log(`   ✅ 保存完了: ${savePath}`);
  }

  private async blocksToMarkdown(
    blockList: any[],
    currentIndent: string,
  ): Promise<string> {
    let mdOutput = "";
    const indent = currentIndent + this.INDENT_UNIT;

    // トグルを画像キャプションとして処理済みの場合、そのインデックスを記録してスキップする
    const skipIndices = new Set<number>();

    for (let i = 0; i < blockList.length; i++) {
      // すでに処理済み（画像の下のトグルなど）なら飛ばす
      if (skipIndices.has(i)) continue;

      const block = blockList[i];
      const bType = block.type;

      // 1. 子ページの処理
      if (bType === "child_page") {
        const childTitle = block.child_page.title;
        if (!childTitle || childTitle.trim() === "") {
          console.log(
            `⚠️ スキップ: ID ${block.id} はタイトルが空のため無視します。`,
          );
          continue;
        }

        const safeTitle = childTitle.replace(/[\\/*?:"<>|]/g, "_").trim();
        const fileName = `${safeTitle}.md`;

        if (!this.processedIds.has(block.id)) {
          this.queue.push({ id: block.id, title: childTitle, fileName });
        }
        mdOutput += `\n\n### 📄 [${childTitle}](./${fileName})\n\n`;
      }

      // 2. 画像の処理 (Python版の「画像＋トグル」ペアロジック)
      else if (bType === "image") {
        //captionは人向けの説明、Toggleの中身はAI向けのMeta情報として扱うイメージ

        const img = block.image;
        const url = img.type === "external" ? img.external.url : img.file.url;
        const fileName = `${block.id}.png`;
        const filePath = path.join(this.imageDir, fileName);

        const success = await downloadFile(url, filePath);

        if (success) {
          console.log(`✅ 画像保存完了: ${fileName}`);
        } else {
          console.log(
            `⚠️ 画像保存に失敗しましたが、リンクのみ記載します: ${fileName}`,
          );
        }

        // Altテキストの決定（優先順位：Alt属性（まだ未公開） > キャプション > デフォルト）
        //const altText = img.alt_text || "";
        const captionText =
          img.caption && img.caption.length > 0
            ? this.extractText(img.caption)
            : "";

        // Markdownの ![ ] に入れる値を決定（Alt優先、次点でCaption）
        const imageAlt = captionText || "画像資料";

        // toggleがあれば　Meta情報として取得
        let metaContent = "";
        // 次のブロックが存在し、かつトグルであれば中身を取得
        if (i + 1 < blockList.length && blockList[i + 1].type === "toggle") {
          console.log(
            `🔗 画像直後のトグルをMeta情報として取得します: ${blockList[i + 1].id}`,
          );
          metaContent = await this.getToggleContent(blockList[i + 1].id);
          skipIndices.add(i + 1); // 次のループでこのトグルを単体出力しない
        }

        // Markdownに書き込み（画像リンクと、AIが読みやすいようにMeta情報も引用形式で添える）
        mdOutput += `\n\n![${imageAlt}](images/${fileName})\n`;

        // toggleで説明（RAG用Meta）があれば引用符で出力
        if (metaContent) {
          mdOutput += `> 🤖 **Image Meta**: ${metaContent}\n\n`;
        }
      }

      // 3. PDF / ファイル
      else if (bType === "file") {
        const fileData = block.file;
        const fileUrl =
          fileData.type === "external"
            ? fileData.external.url
            : fileData.file.url;
        const caption = this.extractText(fileData.caption);
        const fileName = caption
          ? `${caption.replace(/\s+/g, "_")}.pdf`
          : `${block.id}.pdf`;
        const filePath = path.join(this.fileDir, fileName);

        const success = await downloadFile(fileUrl, filePath);
        if (success) {
          mdOutput += `\n\n[📎 添付PDF: ${fileName}](files/${fileName})\n\n`;
          console.log(`   📎 ファイルリンク追加: files/${fileName}`);
        }
      }

      // 4. テキスト系 (H1, H2, H3, Paragraph)
      else if (
        ["heading_1", "heading_2", "heading_3", "paragraph"].includes(bType)
      ) {
        const text = this.extractText(block[bType].rich_text);
        const prefix =
          bType === "heading_1"
            ? "## "
            : bType === "heading_2"
              ? "### "
              : bType === "heading_3"
                ? "#### "
                : "";

        const skipKeywords = ["トップページに戻る", "TOPへ戻る"];
        if (!skipKeywords.some((k) => text.includes(k))) {
          mdOutput += `${prefix}${text}\n\n`;
        }
      }

      // 5. リスト系
      else if (bType === "bulleted_list_item") {
        const text = this.extractText(block.bulleted_list_item.rich_text);
        mdOutput += `* ${text}\n`;
      }

      // 6. ネスト（has_children）の再帰処理
      // トグルの場合は、すでに画像ペアとして中身を吸い出していたら再帰しない
      if (block.has_children && bType !== "child_page" && !skipIndices.has(i)) {
        const children = await this.fetchAllBlocks(block.id);
        mdOutput += await this.blocksToMarkdown(children, indent);
      }
    }
    return mdOutput;
  }
}

// 実行
const token = process.env.NOTION_TOKEN || "";
const rootId = process.env.NOTION_ROOT_PAGE_ID || "";

if (!token || !rootId) {
  console.error("❌ Token or Root ID is missing in .env");
} else {
  const converter = new NotionToMarkdownConverter(token);
  converter.run(rootId).catch(console.error);
}
