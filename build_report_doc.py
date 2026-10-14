#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将《中国研究生网络安全创新大赛作品报告_终稿.md》编译生成符合大赛规范的 Word 文档 (.docx)
大赛排版规范：
- A4 纸
- 正文：宋体 (中) / Times New Roman (英), 小四号字 (12pt), 1.5 倍行距
- 标题体系：黑体加粗
- 表格：规范三线表
- 匿名要求：严格去除学校、院系、导师
"""

import os
import re
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls

def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>'))

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def set_run_font(run, font_name="宋体", size_pt=12, bold=False, italic=False, color_rgb=(0,0,0)):
    run.font.name = font_name
    run._r.get_or_add_rPr().append(parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="Times New Roman" w:eastAsia="{font_name}" w:hAnsi="Times New Roman"/>'))
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = RGBColor(*color_rgb)

def add_styled_paragraph(doc, text="", font_name="宋体", size_pt=12, bold=False, italic=False, 
                         color_rgb=(0,0,0), align=WD_ALIGN_PARAGRAPH.JUSTIFY, 
                         line_spacing=1.5, space_before_pt=0, space_after_pt=4, indent_chars=0):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.line_spacing = line_spacing
    p.paragraph_format.space_before = Pt(space_before_pt)
    p.paragraph_format.space_after = Pt(space_after_pt)
    if indent_chars > 0:
        p.paragraph_format.first_line_indent = Pt(indent_chars * size_pt)
    
    if text:
        # 处理粗体标记 **text**
        parts = re.split(r'(\*\*.*?\*\*)', text)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                r = p.add_run(part[2:-2])
                set_run_font(r, font_name=font_name, size_pt=size_pt, bold=True, italic=italic, color_rgb=color_rgb)
            elif part.startswith('*') and part.endswith('*'):
                r = p.add_run(part[1:-1])
                set_run_font(r, font_name=font_name, size_pt=size_pt, bold=bold, italic=True, color_rgb=color_rgb)
            elif part.startswith('`') and part.endswith('`'):
                r = p.add_run(part[1:-1])
                set_run_font(r, font_name="Consolas", size_pt=size_pt*0.95, bold=False, color_rgb=(180, 40, 40))
            else:
                r = p.add_run(part)
                set_run_font(r, font_name=font_name, size_pt=size_pt, bold=bold, italic=italic, color_rgb=color_rgb)
    return p

def main():
    md_file = "中国研究生网络安全创新大赛作品报告_终稿.md"
    docx_file = "中国研究生网络安全创新大赛作品报告_终稿.docx"
    
    if not os.path.exists(md_file):
        print(f"Error: {md_file} not found")
        return
        
    with open(md_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    doc = docx.Document()
    
    # 页面设置 A4
    for section in doc.sections:
        section.page_width = Inches(8.27)
        section.page_height = Inches(11.69)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # 封面
    p_title1 = add_styled_paragraph(doc, "第五届中国研究生网络安全创新大赛", font_name="黑体", size_pt=22, bold=True, 
                                    align=WD_ALIGN_PARAGRAPH.CENTER, space_before_pt=40, space_after_pt=10, color_rgb=(31, 78, 121))
    p_title2 = add_styled_paragraph(doc, "作 品 报 告", font_name="黑体", size_pt=28, bold=True, 
                                    align=WD_ALIGN_PARAGRAPH.CENTER, space_before_pt=10, space_after_pt=60, color_rgb=(16, 40, 80))
    
    p_name = add_styled_paragraph(doc, "作品名称：双镜 D²Guard：基于快慢双系统与增量安全状态流的大模型智能体防御系统", 
                                  font_name="黑体", size_pt=14, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_before_pt=20, space_after_pt=10)
    p_track = add_styled_paragraph(doc, "参赛赛道：揭榜挑战赛（赛题 5：面向大模型智能体与 MCP 工具链的提示注入与工具滥用检测防御）", 
                                   font_name="宋体", size_pt=12, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, space_before_pt=10, space_after_pt=8)
    p_unit = add_styled_paragraph(doc, "赛题出题单位：安天科技集团", 
                                  font_name="宋体", size_pt=12, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, space_before_pt=4, space_after_pt=8)
    p_date = add_styled_paragraph(doc, "提交日期：2026 年 10 月", 
                                  font_name="宋体", size_pt=12, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, space_before_pt=30, space_after_pt=100)
    
    doc.add_page_break()

    # 填写说明页
    add_styled_paragraph(doc, "填 写 说 明", font_name="黑体", size_pt=16, bold=True, 
                         align=WD_ALIGN_PARAGRAPH.CENTER, space_before_pt=10, space_after_pt=20)
    
    notes = [
        "1. 所有参赛项目必须为一个基本完整的设计。作品报告书旨在能够清晰准确地阐述（或图示）该参赛队的参赛项目（或方案）。",
        "2. 作品报告采用 A4 纸撰写。除标题外，所有内容必需为宋体、小四号字、1.5 倍行距。",
        "3. 作品报告中各项目说明文字部分仅供参考，作品报告书撰写完毕后，请删除所有说明文字。(本页不删除)",
        "4. 作品报告模板里已经列的内容仅供参考，作者可以在此基础上增加内容或对文档结构进行微调。",
        "5. 为保证网评的公平、公正，作品报告中应避免出现作者所在学校、院系和指导教师等泄露身份的信息。一经发现，取消作品参赛资格。"
    ]
    for note in notes:
        add_styled_paragraph(doc, note, font_name="宋体", size_pt=11, bold=False, line_spacing=1.5, space_before_pt=4, space_after_pt=6)

    doc.add_page_break()

    # 正文逐行解析与生成
    lines = md_text.split('\n')
    i = 0
    in_code = False
    in_table = False
    table_lines = []
    
    while i < len(lines):
        line = lines[i].rstrip()
        
        # 跳过顶部元信息与填写说明（前面已单独生成封面）
        if line.startswith("# 第五届中国研究生网络安全创新大赛作品报告"):
            i += 1
            while i < len(lines) and not lines[i].startswith("## 目     录"):
                i += 1
            continue

        # 代码块开始/结束
        if line.startswith("```"):
            if not in_code:
                in_code = True
            else:
                in_code = False
            i += 1
            continue
            
        if in_code:
            # 缩进代码块
            add_styled_paragraph(doc, line, font_name="Consolas", size_pt=10, bold=False, 
                                 align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing=1.1, space_before_pt=1, space_after_pt=1, 
                                 color_rgb=(50, 50, 50))
            i += 1
            continue

        # Markdown 表格行收集
        if line.startswith("|") and line.endswith("|"):
            table_lines.append(line)
            i += 1
            # 检查是否还有下一行表格
            if i < len(lines) and lines[i].startswith("|") and lines[i].endswith("|"):
                continue
            else:
                # 解析并输出表格
                if len(table_lines) >= 2:
                    rows_data = []
                    for tline in table_lines:
                        # 忽略分隔行 | :--- | :--- |
                        if re.match(r'^\|[\s\-:]+(\|[\s\-:]+)+\|$', tline.strip()):
                            continue
                        cells = [c.strip() for c in tline.strip('|').split('|')]
                        rows_data.append(cells)
                    
                    if rows_data:
                        cols_num = max(len(r) for r in rows_data)
                        tbl = doc.add_table(rows=len(rows_data), cols=cols_num)
                        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                        tbl.autofit = True
                        
                        for r_idx, r_data in enumerate(rows_data):
                            is_header = (r_idx == 0)
                            for c_idx in range(cols_num):
                                cell = tbl.cell(r_idx, c_idx)
                                cell_text = r_data[c_idx] if c_idx < len(r_data) else ""
                                cell.text = ""
                                cp = cell.paragraphs[0]
                                cp.alignment = WD_ALIGN_PARAGRAPH.CENTER if (is_header or c_idx == 0) else WD_ALIGN_PARAGRAPH.LEFT
                                cp.paragraph_format.line_spacing = 1.1
                                cp.paragraph_format.space_before = Pt(3)
                                cp.paragraph_format.space_after = Pt(3)
                                run = cp.add_run(cell_text.replace('**', ''))
                                set_run_font(run, font_name="黑体" if is_header else "宋体", 
                                             size_pt=10 if not is_header else 10.5, 
                                             bold=is_header)
                                if is_header:
                                    set_cell_background(cell, "EBF1F5")
                                set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
                        doc.add_paragraph() # 空行缓冲
                table_lines = []
                continue

        # 一级标题：## 第一章 ...
        if line.startswith("## "):
            h_text = line[3:].strip()
            add_styled_paragraph(doc, h_text, font_name="黑体", size_pt=16, bold=True, 
                                 align=WD_ALIGN_PARAGRAPH.LEFT, space_before_pt=18, space_after_pt=8, color_rgb=(20, 50, 100))
            i += 1
            continue

        # 二级标题：### 1.1 ...
        if line.startswith("### "):
            h_text = line[4:].strip()
            add_styled_paragraph(doc, h_text, font_name="黑体", size_pt=14, bold=True, 
                                 align=WD_ALIGN_PARAGRAPH.LEFT, space_before_pt=12, space_after_pt=6, color_rgb=(40, 70, 120))
            i += 1
            continue

        # 三级标题：#### 1. ...
        if line.startswith("#### "):
            h_text = line[5:].strip()
            add_styled_paragraph(doc, h_text, font_name="黑体", size_pt=12.5, bold=True, 
                                 align=WD_ALIGN_PARAGRAPH.LEFT, space_before_pt=8, space_after_pt=4)
            i += 1
            continue

        # 引用块：> ...
        if line.startswith("> "):
            q_text = line[2:].strip()
            add_styled_paragraph(doc, q_text, font_name="楷体", size_pt=11, bold=False, italic=False, 
                                 align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing=1.3, space_before_pt=4, space_after_pt=4, 
                                 indent_chars=2, color_rgb=(80, 80, 80))
            i += 1
            continue

        # 列表条目：* ... 或 1. ...
        if line.startswith("* ") or line.startswith("- "):
            l_text = line[2:].strip()
            add_styled_paragraph(doc, "•  " + l_text, font_name="宋体", size_pt=12, bold=False, 
                                 align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing=1.5, space_before_pt=2, space_after_pt=3, 
                                 indent_chars=1)
            i += 1
            continue

        if re.match(r'^\d+\.\s+', line):
            add_styled_paragraph(doc, line, font_name="宋体", size_pt=12, bold=False, 
                                 align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing=1.5, space_before_pt=2, space_after_pt=3, 
                                 indent_chars=1)
            i += 1
            continue

        # 分割线 ---
        if line.strip() == "---":
            # doc.add_paragraph()
            i += 1
            continue

        # 普通正文
        if line.strip():
            add_styled_paragraph(doc, line.strip(), font_name="宋体", size_pt=12, bold=False, 
                                 align=WD_ALIGN_PARAGRAPH.JUSTIFY, line_spacing=1.5, space_before_pt=0, space_after_pt=4, 
                                 indent_chars=2)
        
        i += 1

    doc.save(docx_file)
    print(f"[SUCCESS] 作品报告 Word 版已生成: {docx_file}")

if __name__ == "__main__":
    main()
