#!/usr/bin/env python3
"""
Markdown + LaTeX → Notion 批量导入工具
=======================================
将包含 LaTeX 数学公式的 Markdown 文件，通过 Notion API 批量创建为 Notion 页面。
公式会自动渲染为 Notion 的 Math Block（KaTeX）。

前置准备:
    1. pip install requests
    2. 创建 Notion Integration: https://www.notion.so/my-integrations
    3. 获取 Internal Integration Token
    4. 在 Notion 中创建一个目标页面，并将 Integration 连接到该页面
       (页面右上角 ••• → Connections → 添加你的 Integration)

使用方式:
    # 单个文件
    python md_to_notion_batch.py --token ntn_xxxxx --parent PAGE_ID file1.md

    # 批量文件
    python md_to_notion_batch.py --token ntn_xxxxx --parent PAGE_ID *.md

    # 整个文件夹
    python md_to_notion_batch.py --token ntn_xxxxx --parent PAGE_ID --dir ./my_notes/

    # 仅本地转换（不上传）
    python md_to_notion_batch.py --convert-only file1.md -o output_dir/

    # 使用环境变量存储 token
    export NOTION_TOKEN=ntn_your_integration_token_here
    export NOTION_PARENT_PAGE=your_parent_page_id_here
    python md_to_notion_batch.py file1.md file2.md

环境变量:
    NOTION_TOKEN       - Notion Integration Token
    NOTION_PARENT_PAGE - 目标父页面 ID
"""

import re
import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from typing import Optional

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)


# ============================================================
# LaTeX → Notion Markdown 转换器
# ============================================================

class LatexToNotionConverter:
    """将标准 Markdown+LaTeX 转换为 Notion 兼容格式"""
    
    def convert(self, markdown_text: str) -> str:
        """完整转换流程"""
        text = markdown_text.replace('\r\n', '\n')
        text = self._convert_block_math(text)
        text = self._convert_inline_math(text)
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        return text.strip()
    
    def _convert_block_math(self, text: str) -> str:
        """
        转换块级公式为标准多行格式: $$\\n公式\\n$$
        
        支持所有常见格式:
          格式1: $$公式$$          (单行，开闭在同一行)
          格式2: $$\\n公式\\n$$     (标准多行，已是正确格式)
          格式3: $$公式\\n$$        (公式紧跟开头$$，下一行关闭) ← 你的文件用的就是这种！
          格式4: $$\\n公式$$        (公式和关闭$$在同一行)
          格式5: $$公式\\n续行\\n$$ (多行公式，开头$$有内容)
        """
        lines = text.split('\n')
        result = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # 检测 $$ 开头
            if stripped.startswith('$$'):
                content_after_open = stripped[2:].strip()
                
                # Case 1: $$formula$$ 单行完整 (开闭都在)
                if content_after_open and content_after_open.endswith('$$'):
                    formula = content_after_open[:-2].strip()
                    result.append('')
                    result.append('$$')
                    result.append(formula)
                    result.append('$$')
                    result.append('')
                    i += 1
                    continue
                
                # Case 2: $$ 开头（可能有内容在同行，也可能没有）
                # 收集公式内容直到找到关闭的 $$
                math_lines = []
                if content_after_open:
                    # 格式3/5: $$formula... 
                    math_lines.append(content_after_open)
                
                i += 1
                found_closing = False
                while i < len(lines):
                    next_stripped = lines[i].strip()
                    
                    # 关闭: 独立的 $$
                    if next_stripped == '$$':
                        found_closing = True
                        i += 1
                        break
                    
                    # 关闭: 内容后跟 $$ (如 "formula$$")
                    if next_stripped.endswith('$$') and len(next_stripped) > 2:
                        math_lines.append(next_stripped[:-2].strip())
                        found_closing = True
                        i += 1
                        break
                    
                    # 安全限制: 如果收集超过 30 行还没找到 $$，说明不是块级公式
                    if len(math_lines) > 30:
                        break
                    
                    math_lines.append(lines[i])
                    i += 1
                
                if found_closing and math_lines:
                    # 成功识别块级公式
                    result.append('')
                    result.append('$$')
                    result.append('\n'.join(math_lines).strip())
                    result.append('$$')
                    result.append('')
                else:
                    # 未找到关闭 $$ 或没有内容，按原文保留
                    result.append(line)
                    for ml in math_lines:
                        result.append(ml)
                
                continue
            
            # 非 $$ 开头的行，原样保留
            result.append(line)
            i += 1
        
        return '\n'.join(result)
    
    def _convert_inline_math(self, text: str) -> str:
        """
        转换行内公式: $...$ → $`...`$
        Notion 使用 $`...`$ 格式渲染行内数学公式
        """
        lines = text.split('\n')
        result = []
        in_block_math = False
        
        for line in lines:
            stripped = line.strip()
            
            if stripped == '$$':
                in_block_math = not in_block_math
                result.append(line)
                continue
            
            if in_block_math or '$`' in line:
                result.append(line)
                continue
            
            # 转换 $...$ → $`...`$
            def replace_inline(match):
                content = match.group(1)
                if not content.strip():
                    return match.group(0)
                # 跳过纯数字金额 ($100, $3.50)，但保留含 LaTeX 的 ($2^{10}$)
                if content and content[0].isdigit() and re.match(r'^[\d,\.]+$', content):
                    return match.group(0)
                return f'$`{content}`$'
            
            line = re.sub(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', replace_inline, line)
            result.append(line)
        
        return '\n'.join(result)


# ============================================================
# Notion Markdown → API Blocks 转换器
# ============================================================

class NotionBlockBuilder:
    """将 Notion 兼容 Markdown 转换为 Notion API block 对象"""
    
    # Notion API 单个 rich_text content 最大 2000 字符
    MAX_TEXT_LENGTH = 2000
    # Notion API 单次最多 100 个 children blocks
    MAX_BLOCKS_PER_REQUEST = 100
    # Notion API 单个 block 的 rich_text 最多 100 个元素
    MAX_RICH_TEXT_ELEMENTS = 100
    
    def _split_block_if_needed(self, block: dict) -> list:
        """
        如果一个 block 的 rich_text 超过 100 个元素，拆分成多个 block。
        Notion API 限制每个 block 最多 100 个 rich_text 元素。
        """
        # 找到 block 中的 rich_text
        block_type = block.get("type")
        if not block_type:
            return [block]
        
        inner = block.get(block_type, {})
        rich_text = inner.get("rich_text")
        
        if not rich_text or len(rich_text) <= self.MAX_RICH_TEXT_ELEMENTS:
            return [block]
        
        # 需要拆分
        result_blocks = []
        for i in range(0, len(rich_text), self.MAX_RICH_TEXT_ELEMENTS):
            chunk = rich_text[i:i + self.MAX_RICH_TEXT_ELEMENTS]
            new_block = {
                "type": block_type,
                block_type: {"rich_text": chunk}
            }
            # 保留其他属性（如 code block 的 language）
            for key, value in inner.items():
                if key != "rich_text":
                    new_block[block_type][key] = value
            result_blocks.append(new_block)
        
        return result_blocks
    
    def build_blocks(self, text: str) -> list:
        """解析 Notion Markdown 为 block 列表"""
        blocks = []
        lines = text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            if not stripped:
                i += 1
                continue
            
            # 块级数学公式
            if stripped == '$$':
                math_lines = []
                i += 1
                found_closing = False
                while i < len(lines) and len(math_lines) < 50:  # 安全限制
                    if lines[i].strip() == '$$':
                        found_closing = True
                        i += 1
                        break
                    math_lines.append(lines[i])
                    i += 1
                
                if found_closing:
                    blocks.append({
                        "type": "equation",
                        "equation": {"expression": '\n'.join(math_lines).strip()}
                    })
                else:
                    # 未找到关闭 $$，当作普通段落
                    blocks.append({
                        "type": "paragraph",
                        "paragraph": {"rich_text": self._parse_rich_text('$$' + ' '.join(math_lines))}
                    })
                continue
            
            # 代码块
            if stripped.startswith('```'):
                lang = stripped[3:].strip()
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # 跳过 ```
                blocks.append({
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": '\n'.join(code_lines)}}],
                        "language": lang if lang else "plain text"
                    }
                })
                continue
            
            # 分隔线
            if stripped in ('---', '***', '___'):
                blocks.append({"type": "divider", "divider": {}})
                i += 1
                continue
            
            # 标题
            header_match = re.match(r'^(#{1,3})\s+(.*)', stripped)
            if header_match:
                level = len(header_match.group(1))
                block_type = f"heading_{level}"
                blocks.append({
                    "type": block_type,
                    block_type: {"rich_text": self._parse_rich_text(header_match.group(2))}
                })
                i += 1
                continue
            
            # 引用
            if stripped.startswith('> '):
                quote_lines = [stripped[2:]]
                i += 1
                while i < len(lines) and lines[i].strip().startswith('> '):
                    quote_lines.append(lines[i].strip()[2:])
                    i += 1
                blocks.append({
                    "type": "quote",
                    "quote": {"rich_text": self._parse_rich_text(' '.join(quote_lines))}
                })
                continue
            
            # 无序列表
            if stripped.startswith('- ') or stripped.startswith('* '):
                blocks.append({
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": self._parse_rich_text(stripped[2:])}
                })
                i += 1
                continue
            
            # 有序列表
            num_match = re.match(r'^\d+\.\s+(.*)', stripped)
            if num_match:
                blocks.append({
                    "type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": self._parse_rich_text(num_match.group(1))}
                })
                i += 1
                continue
            
            # 普通段落（合并连续行）
            para_lines = [stripped]
            i += 1
            while i < len(lines):
                next_s = lines[i].strip()
                if (not next_s or next_s.startswith('#') or next_s.startswith('- ') or
                    next_s.startswith('* ') or next_s == '$$' or next_s.startswith('```') or
                    next_s.startswith('> ') or next_s in ('---', '***', '___') or
                    re.match(r'^\d+\.\s+', next_s)):
                    break
                para_lines.append(next_s)
                i += 1
            
            blocks.append({
                "type": "paragraph",
                "paragraph": {"rich_text": self._parse_rich_text(' '.join(para_lines))}
            })
        
        # 拆分超过 100 个 rich_text 元素的 block
        final_blocks = []
        for block in blocks:
            final_blocks.extend(self._split_block_if_needed(block))
        
        return final_blocks
    
    def _parse_rich_text(self, text: str) -> list:
        """解析文本为 Notion rich_text 数组（支持行内公式、加粗、斜体、代码、链接）"""
        rich_text = []
        
        pattern = re.compile(
            r'(\$`[^`]+`\$)'            # 行内数学: $`...`$
            r'|(\*\*[^*]+\*\*)'         # 加粗: **...**
            r'|(\*[^*]+\*)'             # 斜体: *...*
            r'|(`[^`]+`)'              # 行内代码: `...`
            r'|(\[[^\]]+\]\([^)]+\))'   # 链接: [text](url)
        )
        
        last_end = 0
        for match in pattern.finditer(text):
            # 匹配前的纯文本
            if match.start() > last_end:
                plain = text[last_end:match.start()]
                if plain:
                    rich_text.extend(self._chunk_text(plain))
            
            matched = match.group(0)
            
            if matched.startswith('$`') and matched.endswith('`$'):
                rich_text.append({
                    "type": "equation",
                    "equation": {"expression": matched[2:-2]}
                })
            elif matched.startswith('**') and matched.endswith('**'):
                rich_text.extend(self._chunk_text(matched[2:-2], {"bold": True}))
            elif matched.startswith('*') and matched.endswith('*'):
                rich_text.extend(self._chunk_text(matched[1:-1], {"italic": True}))
            elif matched.startswith('`') and matched.endswith('`'):
                rich_text.extend(self._chunk_text(matched[1:-1], {"code": True}))
            elif matched.startswith('['):
                link_match = re.match(r'\[([^\]]+)\]\(([^)]+)\)', matched)
                if link_match:
                    rich_text.append({
                        "type": "text",
                        "text": {"content": link_match.group(1), "link": {"url": link_match.group(2)}}
                    })
            
            last_end = match.end()
        
        # 剩余纯文本
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                rich_text.extend(self._chunk_text(remaining))
        
        if not rich_text:
            rich_text.append({"type": "text", "text": {"content": text}})
        
        return rich_text
    
    def _chunk_text(self, content: str, annotations: dict = None) -> list:
        """将超长文本切分为 ≤2000 字符的块"""
        chunks = []
        while content:
            chunk = content[:self.MAX_TEXT_LENGTH]
            content = content[self.MAX_TEXT_LENGTH:]
            item = {"type": "text", "text": {"content": chunk}}
            if annotations:
                item["annotations"] = annotations
            chunks.append(item)
        return chunks


# ============================================================
# Notion API 客户端
# ============================================================

class NotionClient:
    """Notion API 简易客户端"""
    
    BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": self.API_VERSION
        }
    
    def create_page(self, title: str, blocks: list, parent_page_id: str) -> Optional[dict]:
        """创建 Notion 页面"""
        import requests
        
        first_batch = blocks[:100]
        
        body = {
            "parent": {"page_id": parent_page_id},
            "properties": {
                "title": [{"text": {"content": title}}]
            },
            "children": first_batch
        }
        
        resp = requests.post(f"{self.BASE_URL}/pages", headers=self.headers, json=body)
        
        if resp.status_code != 200:
            # 首批也可能失败，尝试先创建空页面再逐批追加
            log.warning(f"首批 blocks 创建失败，尝试创建空页面后追加...")
            body["children"] = []
            resp = requests.post(f"{self.BASE_URL}/pages", headers=self.headers, json=body)
            if resp.status_code != 200:
                log.error(f"创建页面失败: {resp.status_code} - {resp.text}")
                return None
            data = resp.json()
            page_id = data["id"]
            # 把所有 blocks 作为 remaining 来追加
            remaining = blocks
        else:
            data = resp.json()
            page_id = data["id"]
            remaining = blocks[100:]
        
        # 追加剩余 blocks
        while remaining:
            batch = remaining[:100]
            remaining = remaining[100:]
            self._append_blocks(page_id, batch)
            time.sleep(0.35)  # API rate limit: ~3 req/s
        
        return data
    
    def _append_blocks(self, page_id: str, blocks: list):
        """追加 blocks 到已有页面，失败时逐个重试"""
        import requests
        
        body = {"children": blocks}
        resp = requests.patch(
            f"{self.BASE_URL}/blocks/{page_id}/children",
            headers=self.headers, json=body
        )
        if resp.status_code == 200:
            return
        
        # 批量失败 → 逐个重试，避免丢失整批内容
        log.warning(f"批量追加失败 ({len(blocks)} blocks)，正在逐个重试...")
        
        for idx, block in enumerate(blocks):
            body = {"children": [block]}
            resp = requests.patch(
                f"{self.BASE_URL}/blocks/{page_id}/children",
                headers=self.headers, json=body
            )
            if resp.status_code != 200:
                # 提取错误信息
                try:
                    err_msg = resp.json().get("message", resp.text)
                except:
                    err_msg = resp.text
                block_type = block.get("type", "unknown")
                # 尝试获取 block 的文本预览
                preview = ""
                inner = block.get(block_type, {})
                rt = inner.get("rich_text", [])
                if rt:
                    first_text = rt[0].get("text", {}).get("content", "") if rt[0].get("type") == "text" else ""
                    preview = f" | 内容: {first_text[:50]}..."
                log.error(f"  ❌ Block #{idx} ({block_type}, {len(rt)} rich_text 元素{preview}): {err_msg}")
            else:
                time.sleep(0.15)  # rate limit
    
    def test_connection(self) -> bool:
        """测试 API 连接"""
        import requests
        
        resp = requests.get(f"{self.BASE_URL}/users/me", headers=self.headers)
        if resp.status_code == 200:
            data = resp.json()
            name = data.get("name", "Unknown")
            log.info(f"✅ API 连接成功！Integration: {name}")
            return True
        else:
            log.error(f"❌ API 连接失败: {resp.status_code} - {resp.text}")
            return False


# ============================================================
# 批量处理引擎
# ============================================================

class BatchProcessor:
    """批量处理 Markdown 文件"""
    
    def __init__(self, token: str = None, parent_page_id: str = None):
        self.converter = LatexToNotionConverter()
        self.builder = NotionBlockBuilder()
        self.client = NotionClient(token) if token else None
        self.parent_page_id = parent_page_id
    
    def process_file(self, filepath: Path, upload: bool = True) -> dict:
        """处理单个文件"""
        log.info(f"📄 处理: {filepath.name}")
        
        # 读取
        text = filepath.read_text(encoding='utf-8')
        
        # 转换
        converted = self.converter.convert(text)
        
        # 构建 blocks
        blocks = self.builder.build_blocks(converted)
        
        result = {
            "file": str(filepath),
            "title": self._extract_title(text, filepath),
            "blocks_count": len(blocks),
            "converted_text": converted,
        }
        
        # 上传
        if upload and self.client and self.parent_page_id:
            data = self.client.create_page(result["title"], blocks, self.parent_page_id)
            if data:
                result["notion_url"] = data["url"]
                result["notion_id"] = data["id"]
                log.info(f"  ✅ 已创建: {data['url']}")
            else:
                result["error"] = "上传失败"
                log.error(f"  ❌ 上传失败")
        
        return result
    
    def process_files(self, filepaths: list, upload: bool = True) -> list:
        """批量处理多个文件"""
        results = []
        total = len(filepaths)
        
        for idx, fp in enumerate(filepaths, 1):
            log.info(f"\n[{idx}/{total}] {'='*50}")
            result = self.process_file(fp, upload=upload)
            results.append(result)
            
            # Rate limiting
            if upload and idx < total:
                time.sleep(0.5)
        
        return results
    
    def _extract_title(self, text: str, filepath: Path) -> str:
        """从 Markdown 提取标题，fallback 到文件名"""
        # 尝试找 # 标题
        match = re.search(r'^#\s+(.+)', text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return filepath.stem
    
    def save_converted(self, filepath: Path, output_dir: Path):
        """仅转换并保存（不上传）"""
        text = filepath.read_text(encoding='utf-8')
        converted = self.converter.convert(text)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filepath.name
        output_path.write_text(converted, encoding='utf-8')
        log.info(f"  💾 保存: {output_path}")
        return output_path


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Markdown + LaTeX → Notion 批量导入工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 批量上传到 Notion
  python md_to_notion_batch.py --token ntn_xxx --parent abc123 ch1.md ch2.md ch3.md

  # 上传整个文件夹
  python md_to_notion_batch.py --token ntn_xxx --parent abc123 --dir ./notes/

  # 仅转换（不上传），输出到 converted/ 文件夹
  python md_to_notion_batch.py --convert-only -o converted/ ch1.md ch2.md

  # 使用环境变量
  export NOTION_TOKEN=ntn_your_integration_token_here
  export NOTION_PARENT_PAGE=your_parent_page_id_here
  python md_to_notion_batch.py *.md
        """
    )
    
    parser.add_argument('files', nargs='*', help='Markdown 文件路径')
    parser.add_argument('--dir', help='处理整个目录中的 .md 文件')
    parser.add_argument('--token', help='Notion Integration Token (或设置 NOTION_TOKEN 环境变量)')
    parser.add_argument('--parent', help='目标父页面 ID (或设置 NOTION_PARENT_PAGE 环境变量)')
    parser.add_argument('--convert-only', action='store_true', help='仅转换格式，不上传到 Notion')
    parser.add_argument('-o', '--output', default='./converted', help='转换输出目录 (默认: ./converted)')
    parser.add_argument('--test', action='store_true', help='测试 API 连接')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不实际上传')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细输出')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 获取 token 和 parent
    token = args.token or os.environ.get('NOTION_TOKEN')
    parent = args.parent or os.environ.get('NOTION_PARENT_PAGE')
    
    # 测试连接
    if args.test:
        if not token:
            log.error("❌ 请提供 --token 或设置 NOTION_TOKEN 环境变量")
            sys.exit(1)
        client = NotionClient(token)
        client.test_connection()
        return
    
    # 收集文件
    filepaths = []
    if args.dir:
        dir_path = Path(args.dir)
        filepaths.extend(sorted(dir_path.glob('*.md')))
    if args.files:
        filepaths.extend([Path(f) for f in args.files])
    
    if not filepaths:
        parser.print_help()
        print("\n💡 提示: 请指定 Markdown 文件或使用 --dir 指定目录")
        return
    
    # 验证文件存在
    for fp in filepaths:
        if not fp.exists():
            log.error(f"❌ 文件不存在: {fp}")
            sys.exit(1)
    
    log.info(f"📚 找到 {len(filepaths)} 个文件待处理")
    
    # 仅转换模式
    if args.convert_only:
        processor = BatchProcessor()
        output_dir = Path(args.output)
        for fp in filepaths:
            processor.save_converted(fp, output_dir)
        log.info(f"\n✅ 转换完成！输出目录: {output_dir}")
        return
    
    # 上传模式
    if not token:
        log.error("❌ 请提供 --token 或设置 NOTION_TOKEN 环境变量")
        log.info("💡 创建 Integration: https://www.notion.so/my-integrations")
        sys.exit(1)
    
    if not parent:
        log.error("❌ 请提供 --parent 或设置 NOTION_PARENT_PAGE 环境变量")
        log.info("💡 Parent 是你想把页面创建到的 Notion 页面 ID")
        sys.exit(1)
    
    # 执行
    processor = BatchProcessor(token=token, parent_page_id=parent)
    
    # 先测试连接
    if not processor.client.test_connection():
        sys.exit(1)
    
    upload = not args.dry_run
    if args.dry_run:
        log.info("🔍 模拟运行模式（不会实际上传）")
    
    results = processor.process_files(filepaths, upload=upload)
    
    # 汇总
    print("\n" + "=" * 60)
    print("📊 处理结果汇总")
    print("=" * 60)
    
    success = sum(1 for r in results if 'notion_url' in r)
    failed = sum(1 for r in results if 'error' in r)
    
    for r in results:
        status = "✅" if 'notion_url' in r else ("⏭️" if args.dry_run else "❌")
        url = r.get('notion_url', '')
        print(f"  {status} {r['title']} ({r['blocks_count']} blocks) {url}")
    
    if upload:
        print(f"\n成功: {success} | 失败: {failed} | 总计: {len(results)}")


if __name__ == '__main__':
    main()
