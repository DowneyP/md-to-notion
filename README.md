# md-to-notion

**将 Markdown + LaTeX 文件批量导入 Notion 的命令行工具**

A CLI tool to batch-import Markdown files (with LaTeX math) into Notion via the official API.

---

## 目录 / Table of Contents

- [功能特性](#功能特性--features)
- [快速开始 (中文)](#快速开始)
- [Quick Start (English)](#quick-start)
- [命令行参数](#命令行参数--cli-options)
- [使用示例](#使用示例--examples)
- [常见问题](#常见问题--faq)

---

## 功能特性 / Features

- 支持块级数学公式 `$$...$$` → Notion Equation Block（KaTeX 渲染）
- 支持行内数学公式 `$...$` → Notion Inline Equation
- 支持 Markdown 常用语法：标题、列表、代码块、引用、分隔线、链接、加粗、斜体
- 批量处理：可指定多个文件或整个目录
- 自动分批上传，规避 Notion API 的 100 blocks/次限制
- 仅转换模式（不上传，只输出处理后的 Markdown）
- 支持通过环境变量管理 Token，避免命令行明文泄露

---

## 快速开始

### 第一步：安装依赖

```bash
pip install requests
```

> 只依赖 `requests`，无需其他第三方库。

---

### 第二步：创建 Notion Integration（获取 Token）

1. 打开 [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. 点击右上角 **"+ New integration"**
3. 填写名称（随意，如 `md-importer`），选择关联的 Workspace
4. 点击 **"Submit"**，然后复制 **"Internal Integration Token"**（格式为 `ntn_xxxxxxxxxx`）

> 这个 Token 就是你的 API 密钥，请妥善保存，不要泄露。

---

### 第三步：获取目标页面 ID

1. 在 Notion 中打开你想将文件导入到的父页面（目标页面）
2. 点击右上角 **"···"** → **"Copy link"**
3. 链接格式为：`https://www.notion.so/你的页面标题-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
4. 最后那一串 32 位的十六进制字符串就是 **Page ID**

   例如：`https://www.notion.so/My-Notes-a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4`

   Page ID = `a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4`

---

### 第四步：将 Integration 连接到该页面

> **这一步很容易忘！不做这步会报 404 错误。**

1. 打开目标页面
2. 点击右上角 **"···"** → **"Connections"**
3. 搜索并添加你刚创建的 Integration

---

### 第五步：运行脚本

```bash
# 上传单个文件
python md_to_notion_batch.py --token ntn_你的token --parent 你的页面ID chapter1.md

# 批量上传多个文件
python md_to_notion_batch.py --token ntn_你的token --parent 你的页面ID *.md

# 上传整个目录
python md_to_notion_batch.py --token ntn_你的token --parent 你的页面ID --dir ./my_notes/

# 推荐：用环境变量，避免 token 出现在命令行历史
export NOTION_TOKEN=ntn_你的token
export NOTION_PARENT_PAGE=你的页面ID
python md_to_notion_batch.py *.md
```

---

## Quick Start

### Step 1: Install Dependencies

```bash
pip install requests
```

Only `requests` is required. No other third-party libraries needed.

---

### Step 2: Create a Notion Integration (Get Your Token)

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **"+ New integration"** in the top right
3. Give it a name (e.g. `md-importer`), select your Workspace
4. Click **"Submit"**, then copy the **"Internal Integration Token"** (starts with `ntn_`)

> Keep this token private — treat it like a password.

---

### Step 3: Get Your Target Page ID

1. Open the Notion page where you want to import files
2. Click **"···"** (top right) → **"Copy link"**
3. The URL looks like: `https://www.notion.so/Page-Title-a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4`
4. The 32-character hex string at the end is the **Page ID**

---

### Step 4: Connect the Integration to Your Page

> **Don't skip this step — you'll get a 404 error if you do.**

1. Open the target page in Notion
2. Click **"···"** → **"Connections"**
3. Search for and add the Integration you just created

---

### Step 5: Run the Script

```bash
# Upload a single file
python md_to_notion_batch.py --token ntn_YOUR_TOKEN --parent YOUR_PAGE_ID notes.md

# Upload multiple files
python md_to_notion_batch.py --token ntn_YOUR_TOKEN --parent YOUR_PAGE_ID *.md

# Upload an entire directory
python md_to_notion_batch.py --token ntn_YOUR_TOKEN --parent YOUR_PAGE_ID --dir ./my_notes/

# Recommended: use environment variables to keep your token out of shell history
export NOTION_TOKEN=ntn_YOUR_TOKEN
export NOTION_PARENT_PAGE=YOUR_PAGE_ID
python md_to_notion_batch.py *.md
```

---

## 命令行参数 / CLI Options

| 参数 / Option | 说明 / Description |
|---|---|
| `files` | 要上传的 Markdown 文件（可多个）|
| `--dir DIR` | 上传指定目录下所有 `.md` 文件 |
| `--token TOKEN` | Notion Integration Token |
| `--parent PAGE_ID` | 目标父页面 ID |
| `--convert-only` | 仅转换格式，不上传（输出到 `./converted/`）|
| `-o OUTPUT` | 指定转换输出目录（默认 `./converted`）|
| `--test` | 测试 API 连接是否正常 |
| `--dry-run` | 模拟运行，不实际上传 |
| `-v, --verbose` | 显示详细日志 |

---

## 使用示例 / Examples

```bash
# 测试连接
python md_to_notion_batch.py --token ntn_YOUR_TOKEN --test

# 模拟运行（检查会生成多少 blocks，不上传）
python md_to_notion_batch.py --token ntn_YOUR_TOKEN --parent YOUR_PAGE_ID --dry-run *.md

# 仅转换，查看处理结果（不上传）
python md_to_notion_batch.py --convert-only -o ./output/ chapter1.md chapter2.md
```

---

## 常见问题 / FAQ

**Q: 运行时报 `401 Unauthorized`**
> Token 无效或拼写错误，请重新从 [my-integrations](https://www.notion.so/my-integrations) 复制。

**Q: 运行时报 `404 Not Found`**
> 忘记在目标页面添加 Integration 了。请参考「第四步」。

**Q: LaTeX 公式没有正确渲染**
> 确认公式格式：块级公式用 `$$\n公式\n$$`（单独成行），行内公式用 `$公式$`。

**Q: 上传速度很慢**
> Notion API 有速率限制，脚本已自动加入 0.35 秒延迟，属正常现象。

**Q: 文件很大，blocks 超过 100 个怎么办？**
> 脚本会自动分批上传，无需手动处理。

---

## License

MIT
