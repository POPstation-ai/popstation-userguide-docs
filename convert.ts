import { Client } from "@notionhq/client";
import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";
import axios from "axios"; // Pythonのrequestsの代わり

dotenv.config();

// --- ユーティリティ関数 ---
const extractText = (richTextArray: any[]): string => {
  return richTextArray?.map((t) => t.plain_text).join("") || "";
};

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

class NotionToMarkdownConverter {
  private notion: Client;
  private queue: Array<{ id: string; title: string; fileName: string }> = [];
  private processedIds = new Set<string>();
  private outputDir: string;
  private imageDir: string;
  private fileDir: string;
  private INDENT_UNIT = "    ";

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

    for (const block of blockList) {
      const bType = block.type;

      // 1. 子ページの処理 (Python版同様にキューに追加)
      if (bType === "child_page") {
        const childTitle = block.child_page.title;

        // 【修正ポイント】タイトルが空、またはスペースのみなら無視して次へ
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
        // リンクを ./ から始めることで確実に相対パスとして認識させます
        //mdOutput += `${currentIndent}### 📄 [${childTitle}](./${encodeURIComponent(fileName)})\n\n`; // インデント削除
        mdOutput += `\n\n### 📄 [${childTitle}](./${fileName})\n\n`;
      }

      // 2. 画像の処理
      else if (bType === "image") {
        const img = block.image;
        const url = img.type === "external" ? img.external.url : img.file.url;
        const fileName = `${block.id}.png`;
        const filePath = path.join(this.imageDir, fileName);

        // ダウンロードを試みるが、成否に関わらず処理を続ける
        const success = await downloadFile(url, filePath);

        if (success) {
          console.log(`✅ 画像保存完了: ${fileName}`);
        } else {
          console.log(
            `⚠️ 画像保存に失敗しましたが、リンクのみ記載します: ${fileName}`,
          );
        }
        //ダウンロードの成否を問わず mdOutput に追加する
        mdOutput += `\n\n![image](images/${fileName})\n\n`;
      }

      // 3. PDF / ファイル（Python版の移植）
      else if (bType === "file") {
        const fileData = block.file;
        const fileUrl =
          fileData.type === "external"
            ? fileData.external.url
            : fileData.file.url;
        const caption = extractText(fileData.caption);
        const fileName = caption
          ? `${caption.replace(/\s+/g, "_")}.pdf`
          : `${block.id}.pdf`;
        const filePath = path.join(this.fileDir, fileName);

        const success = await downloadFile(fileUrl, filePath);
        if (success) {
          //mdOutput += `\n\n${currentIndent}[📎 添付PDF: ${fileName}](files/${fileName})\n\n`; インデント削除
          mdOutput += `\n\n[📎 添付PDF: ${fileName}](files/${fileName})\n\n`;
          console.log(`   📎 ファイルリンク追加: files/${fileName}`);
        }
      }

      // 4. テキスト系 (H1, H2, H3, Paragraph)
      else if (
        ["heading_1", "heading_2", "heading_3", "paragraph"].includes(bType)
      ) {
        const text = extractText(block[bType].rich_text);
        const prefix =
          bType === "heading_1"
            ? "## "
            : bType === "heading_2"
              ? "### "
              : bType === "heading_3"
                ? "#### "
                : "";

        // スキップキーワード判定
        const skipKeywords = ["トップページに戻る", "TOPへ戻る"];
        if (!skipKeywords.some((k) => text.includes(k))) {
          //mdOutput += `${currentIndent}${prefix}${text}\n\n`;
          mdOutput += `${prefix}${text}\n\n`;
        }
      }

      // 5. リスト系
      else if (bType === "bulleted_list_item") {
        const text = extractText(block.bulleted_list_item.rich_text);
        //mdOutput += `${currentIndent}* ${text}\n`;
        mdOutput += `* ${text}\n`;
      }

      // 6. ネスト（has_children）の再帰処理
      if (block.has_children && bType !== "child_page") {
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
