#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成高质量的导师汇报 PPT: 双镜_D2Guard_项目汇报.pptx
基于 python-pptx，符合学术与创新大赛标准的高级商务科技风排版
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

def create_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9 宽屏
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]

    # 调色板
    DARK_BG = RGBColor(15, 23, 42)       # #0F172A 深夜蓝 (封面/封底)
    LIGHT_BG = RGBColor(248, 250, 252)   # #F8FAFC 极浅灰蓝 (内页底色)
    TEXT_MAIN = RGBColor(15, 23, 42)     # #0F172A 深色正文
    TEXT_MUTED = RGBColor(100, 116, 139) # #64748B 次级文本
    TEXT_WHITE = RGBColor(255, 255, 255) # 白色
    PRIMARY_BLUE = RGBColor(37, 99, 235) # #2563EB 核心科技蓝
    ACCENT_CYAN = RGBColor(13, 148, 136) # #0D9488 成果青
    ACCENT_RED = RGBColor(225, 29, 72)   # #E11D48 警戒红
    CARD_BG = RGBColor(255, 255, 255)    # 纯白卡片
    CARD_BORDER = RGBColor(226, 232, 240)# 卡片边框浅灰

    def add_background(slide, color):
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, prs.slide_height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background() # 无边框
        return shape

    def add_card(slide, left, top, width, height, bg_color=CARD_BG, border_color=CARD_BORDER):
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = bg_color
        if border_color:
            shape.line.color.rgb = border_color
            shape.line.width = Pt(1.5)
        else:
            shape.line.fill.background()
        return shape

    def add_header(slide, title_text, subtitle_text=""):
        # 页面顶部标题区
        tb = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(1.1))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.name = "黑体"
        p.font.size = Pt(24)
        p.font.bold = True
        p.font.color.rgb = PRIMARY_BLUE
        
        if subtitle_text:
            p2 = tf.add_paragraph()
            p2.text = subtitle_text
            p2.font.name = "宋体"
            p2.font.size = Pt(12)
            p2.font.color.rgb = TEXT_MUTED
            p2.space_before = Pt(4)

    # ==========================================
    # SLIDE 1: 封面
    # ==========================================
    slide1 = prs.slides.add_slide(blank_layout)
    add_background(slide1, DARK_BG)

    # 装饰装饰光带
    accent_bar = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(1.6), Inches(0.12), Inches(4.2))
    accent_bar.fill.solid()
    accent_bar.fill.fore_color.rgb = PRIMARY_BLUE
    accent_bar.line.fill.background()

    tb1 = slide1.shapes.add_textbox(Inches(1.6), Inches(1.5), Inches(10.5), Inches(4.5))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    
    p = tf1.paragraphs[0]
    p.text = "“华为杯”第五届中国研究生网络安全创新大赛 · 揭榜赛题 5"
    p.font.name = "黑体"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = ACCENT_CYAN
    p.space_after = Pt(14)

    p = tf1.add_paragraph()
    p.text = "双镜 D²Guard"
    p.font.name = "黑体"
    p.font.size = Pt(38)
    p.font.bold = True
    p.font.color.rgb = TEXT_WHITE
    p.space_after = Pt(8)

    p = tf1.add_paragraph()
    p.text = "基于快慢双系统与增量安全状态流的大模型智能体防御系统"
    p.font.name = "宋体"
    p.font.size = Pt(20)
    p.font.bold = False
    p.font.color.rgb = RGBColor(148, 163, 184)
    p.space_after = Pt(36)

    p = tf1.add_paragraph()
    p.text = "• 出题单位：安天科技集团 (Antiy Labs)\n• 核心特色：快慢双系统分流决策 | 8字节滑动窗口分片熔断 | 跨MCP因果DAG溯源 | 2×A100真机实测 91.7% 阻断"
    p.font.name = "宋体"
    p.font.size = Pt(13)
    p.font.color.rgb = RGBColor(203, 213, 225)
    p.line_spacing = 1.3

    # ==========================================
    # SLIDE 2: 赛题背景与核心安全痛点
    # ==========================================
    slide2 = prs.slides.add_slide(blank_layout)
    add_background(slide2, LIGHT_BG)
    add_header(slide2, "一、 课题背景：自主智能体面临的致命安全困局", "Agent 进化带来攻击面指数级爆发，传统安全设施陷入完全的“语义盲区”")

    # 3张卡片布局
    col_w = 3.65
    gap = 0.38
    left_m = 0.8
    card_h = 5.0
    top_pos = 1.8

    cards_s2 = [
        ("1. Agent与MCP生态泛化", "头号高危风险 (OWASP LLM01)", [
            "智能体(Claude Code, Devin, AVL)已具备文件读写、命令执行、MCP总线调用能力；",
            "提示词与数据边界彻底模糊，外部网页、源码注释、工单均可成为攻击载荷源；",
            "CVE-2024-49035 等越权漏洞已在工业级 Agent 工具链上真实爆发。"
        ], PRIMARY_BLUE),
        ("2. 现有安全设施的“失能”", "传统WAF与全量模型检测失效", [
            "传统 WAF / EDR 处在报文与系统调用层，无法理解“意图-规划-工具调用”高维语义；",
            "全量大模型二次检验引发延迟雪崩(数秒级)与高昂成本，严重摧毁 Agent 响应体验；",
            "面对万字文档时，安全约束极易被“长上下文稀释攻击”彻底淹没。"
        ], ACCENT_RED),
        ("3. 状态断裂与分片外泄", "“只看增量”的致命失忆死穴", [
            "为轻量化而“仅看当前增量”，无法追踪跨多轮的长间隔因果关系(第1轮读取，第7轮外发)；",
            "攻击者将32字节私钥切为8字节多次渗漏时，单次请求极小，传统与无状态模型完全漏报；",
            "必须构建具备“跨多轮状态锁定与毫秒级决策”的专用智能体防御系统。"
        ], ACCENT_CYAN)
    ]

    for idx, (title, sub, bullets, color) in enumerate(cards_s2):
        c_left = left_m + idx * (col_w + gap)
        add_card(slide2, c_left, top_pos, col_w, card_h)
        tb = slide2.shapes.add_textbox(Inches(c_left + 0.25), Inches(top_pos + 0.25), Inches(col_w - 0.5), Inches(card_h - 0.5))
        tf = tb.text_frame
        tf.word_wrap = True
        
        p = tf.paragraphs[0]
        p.text = title
        p.font.name = "黑体"
        p.font.size = Pt(17)
        p.font.bold = True
        p.font.color.rgb = color
        
        p = tf.add_paragraph()
        p.text = sub
        p.font.name = "宋体"
        p.font.size = Pt(11)
        p.font.color.rgb = TEXT_MUTED
        p.space_after = Pt(14)

        for b in bullets:
            p = tf.add_paragraph()
            p.text = "• " + b
            p.font.name = "宋体"
            p.font.size = Pt(12)
            p.font.color.rgb = TEXT_MAIN
            p.space_before = Pt(6)
            p.line_spacing = 1.25

    # ==========================================
    # SLIDE 3: 系统总体架构：前线双探针与中央大脑
    # ==========================================
    slide3 = prs.slides.add_slide(blank_layout)
    add_background(slide3, LIGHT_BG)
    add_header(slide3, "二、 系统架构：前线双探针与中央决策中枢", "解耦为【工具侧 Hook】+【API 侧网关】↔【共享防护内核】，贯穿三大极简接口")

    # 左右两栏布局：左侧三大部件，右侧三大接口
    add_card(slide3, 0.8, 1.8, 5.7, 5.0)
    tb_l = slide3.shapes.add_textbox(Inches(1.05), Inches(2.0), Inches(5.2), Inches(4.5))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    
    p = tf_l.paragraphs[0]
    p.text = "三大部件：全链路物理受控闭环"
    p.font.name = "黑体"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_BLUE
    p.space_after = Pt(12)

    parts = [
        ("【部件 1: 工具侧 Hook】(执行刹车闸)", "挂接在 Agent 工具执行最底层(fs/net/exec/git/mcp)，在发包或写入前掐断物理调用，严格执行 ALLOW / ASK / BLOCK。"),
        ("【部件 2: API 侧网关】(模型进出观测哨)", "部署在 Agent 与 LLM 间充当中继代理，双向捕获输入 Prompt 与模型候选调用，防止敏感凭据出境，提取增量事件。"),
        ("【部件 3: 共享防护内核】(中央决策大脑)", "集中维护增量 JSON 事件流，维护安全状态聚合机，运行快慢双系统与策略 DSL 2.0，输出裁决控制参数。")
    ]
    for p_title, p_desc in parts:
        p = tf_l.add_paragraph()
        p.text = p_title
        p.font.name = "黑体"
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = TEXT_MAIN
        p.space_before = Pt(8)
        
        p = tf_l.add_paragraph()
        p.text = p_desc
        p.font.name = "宋体"
        p.font.size = Pt(11.5)
        p.font.color.rgb = RGBColor(71, 85, 105)
        p.line_spacing = 1.2

    # 右侧三大核心接口
    add_card(slide3, 6.8, 1.8, 5.7, 5.0)
    tb_r = slide3.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.5))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True

    p = tf_r.paragraphs[0]
    p.text = "三大核心接口：极简标准化数据流"
    p.font.name = "黑体"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = ACCENT_CYAN
    p.space_after = Pt(12)

    interfaces = [
        ("1. extract(event) -> ExtractedData", "代码确定性抽取(绝对路径、网络域名、Shell AST 语法树解析、Canary 扫描) + 快镜轻量模型主观语义初筛。"),
        ("2. update_state(state, extracted) -> SecurityState", "安全状态聚合机：更新初始任务授权锚点、已读敏感数据登记薄(Secret Ledger: 明文/Base64/8字节分片)、因果调用拓扑。"),
        ("3. decide(state, proposed_action) -> ActionVerdict", "策略 DSL 规则引擎快速阻断 + 疑点按需唤醒慢镜深度因果裁判，向 Hook 回传三态控制参数。")
    ]
    for i_title, i_desc in interfaces:
        p = tf_r.add_paragraph()
        p.text = i_title
        p.font.name = "Consolas"
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = PRIMARY_BLUE
        p.space_before = Pt(8)

        p = tf_r.add_paragraph()
        p.text = i_desc
        p.font.name = "宋体"
        p.font.size = Pt(11.5)
        p.font.color.rgb = RGBColor(71, 85, 105)
        p.line_spacing = 1.2

    # ==========================================
    # SLIDE 4: 机制一：快慢双系统（Dual-System）
    # ==========================================
    slide4 = prs.slides.add_slide(blank_layout)
    add_background(slide4, LIGHT_BG)
    add_header(slide4, "三、 核心机制一：快慢双系统协同决策范式", "认知科学双系统理论落地：毫秒级极速初筛与按需唤醒深度因果裁判完美平衡")

    add_card(slide4, 0.8, 1.8, 5.7, 5.0)
    tb_fast = slide4.shapes.add_textbox(Inches(1.05), Inches(2.0), Inches(5.2), Inches(4.5))
    tf_fast = tb_fast.text_frame
    tf_fast.word_wrap = True

    p = tf_fast.paragraphs[0]
    p.text = "【快镜】System 1 · 极速毫秒初筛"
    p.font.name = "黑体"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_BLUE
    p.space_after = Pt(8)

    fast_items = [
        "模型选型：本地轻量 Laya (421M 双向编码器) / 规则校准引擎；",
        "极速响应：实测中位额外延迟仅 3.74 ms (远优于赛题 <20ms 要求)；",
        "定型初筛：将文本与动作映射为标准化风险得分 (0.0~1.0) 与合规分类；",
        "分流过滤：过滤 95%+ 以上常规良性操作，保障 Agent 高速运行流水线无任何卡顿感知。"
    ]
    for it in fast_items:
        p = tf_fast.add_paragraph()
        p.text = "• " + it
        p.font.name = "宋体"
        p.font.size = Pt(12)
        p.font.color.rgb = TEXT_MAIN
        p.space_before = Pt(6)
        p.line_spacing = 1.25

    add_card(slide4, 6.8, 1.8, 5.7, 5.0)
    tb_slow = slide4.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.5))
    tf_slow = tb_slow.text_frame
    tf_slow.word_wrap = True

    p = tf_slow.paragraphs[0]
    p.text = "【慢镜】System 2 · 深度因果裁判"
    p.font.name = "黑体"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = ACCENT_CYAN
    p.space_after = Pt(8)

    slow_items = [
        "按需唤醒：仅在快镜评分临界或触碰高危敏感边界时按需唤醒 (<5%)；",
        "精选证据包 (Evidence Pack)：拒绝塞入巨量历史，仅提取用户原始意图、关键已读敏感数据与当前环境动作增量；",
        "结构化中文判词：输出包含违规规则、风险等级与因果链依据的严谨分析；",
        "双通道架构：支持商用云端 API (DeepSeek-v3.2) 与算力机 GPU1 自部署服务 (Qwen-27B on vLLM) 一键热切换。"
    ]
    for it in slow_items:
        p = tf_slow.add_paragraph()
        p.text = "• " + it
        p.font.name = "宋体"
        p.font.size = Pt(12)
        p.font.color.rgb = TEXT_MAIN
        p.space_before = Pt(6)
        p.line_spacing = 1.25

    # ==========================================
    # SLIDE 5: 机制二：增量安全状态聚合机与滑动窗口
    # ==========================================
    slide5 = prs.slides.add_slide(blank_layout)
    add_background(slide5, LIGHT_BG)
    add_header(slide5, "四、 核心机制二：安全状态聚合机与滑动窗口熔断", "彻底攻克“单看增量导致多轮分片外发漏报”与“长文本规则稀释”两大行业痛点")

    add_card(slide5, 0.8, 1.8, 11.7, 5.0)
    tb_s5 = slide5.shapes.add_textbox(Inches(1.1), Inches(2.0), Inches(11.1), Inches(4.5))
    tf_s5 = tb_s5.text_frame
    tf_s5.word_wrap = True

    p = tf_s5.paragraphs[0]
    p.text = "三大核心状态治理创新"
    p.font.name = "黑体"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_BLUE
    p.space_after = Pt(12)

    innovations = [
        ("1. 不可变任务授权锚点 (Task Anchor)", "会话启动即锁定初始用户任务意图，任凭后续对话输入 20,000+ 字无害文档，初始授权始终具有最高决策优先级，天然免疫长上下文稀释攻击。"),
        ("2. 敏感数据登记薄 (Secret Ledger)", "实时维护会话内已读敏感凭据的全量登记。一旦 fs.read 访问 .env 或私钥，登记薄自动登记明文及其预派生的 Base64、Hex、URL 编码变体。"),
        ("3. 8字节滑动窗口与分片覆盖率累积熔断算法", "针对将 32 字节私钥拆分为 3 轮微小请求外发的高级逃逸手法，聚合机自动将敏感凭据切为 8 字节子片段滑动窗口。当检测到跨请求累计命中 >2 个分片或单域名覆盖率达 35% 时，立即硬阻断，实测将分片部分泄露率从 100% 降至 0.0%！"),
        ("4. 轻量无状态开销设计", "状态机仅驻留元数据特征与 UUID 索引，百轮长程任务内存消耗严格控制在 < 100 KB，彻底杜绝状态爆炸。")
    ]
    for in_t, in_d in innovations:
        p = tf_s5.add_paragraph()
        p.text = in_t
        p.font.name = "黑体"
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = ACCENT_CYAN
        p.space_before = Pt(6)
        
        p = tf_s5.add_paragraph()
        p.text = in_d
        p.font.name = "宋体"
        p.font.size = Pt(12)
        p.font.color.rgb = TEXT_MAIN
        p.line_spacing = 1.25

    # ==========================================
    # SLIDE 6: 机制三：策略 DSL 2.0 与因果 DAG 溯源
    # ==========================================
    slide6 = prs.slides.add_slide(blank_layout)
    add_background(slide6, LIGHT_BG)
    add_header(slide6, "五、 核心机制三：策略 DSL 2.0 与因果拓扑 DAG", "细粒度声明式策略管控 + 跨 MCP、跨子 Agent 全链路交互式因果溯源")

    add_card(slide6, 0.8, 1.8, 5.7, 5.0)
    tb_dsl = slide6.shapes.add_textbox(Inches(1.05), Inches(2.0), Inches(5.2), Inches(4.5))
    tf_dsl = tb_dsl.text_frame
    tf_dsl.word_wrap = True

    p = tf_dsl.paragraphs[0]
    p.text = "策略 DSL 2.0 与三态决策模型"
    p.font.name = "黑体"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_BLUE
    p.space_after = Pt(8)

    dsl_rules = [
        "三态决策：ALLOW (合规放行) / ASK (人工授权) / BLOCK (物理阻断)；",
        "RULE_CRITICAL_WRITE：禁止写入 ~/.ssh, ~/.aws, /etc/cron.* 等敏感路径；",
        "RULE_DATA_EXFILTRATION：禁止将 Secret Ledger 登记凭据发往非信任域名；",
        "RULE_EXEC_SUSPICIOUS：基于 Shell AST 语法树拦截管道逃逸 (curl|bash)；",
        "RULE_CODE_REVIEW_PUSH：代码走查任务中禁止触发 git.push 越权提交；",
        "RULE_SUBAGENT_CREDENTIAL：严禁向子 Agent 传递环境变量密钥与敏感凭证。"
    ]
    for r in dsl_rules:
        p = tf_dsl.add_paragraph()
        p.text = "• " + r
        p.font.name = "宋体"
        p.font.size = Pt(12)
        p.font.color.rgb = TEXT_MAIN
        p.space_before = Pt(5)
        p.line_spacing = 1.2

    add_card(slide6, 6.8, 1.8, 5.7, 5.0)
    tb_dag = slide6.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.5))
    tf_dag = tb_dag.text_frame
    tf_dag.word_wrap = True

    p = tf_dag.paragraphs[0]
    p.text = "跨 MCP 与子 Agent 因果 DAG 溯源"
    p.font.name = "黑体"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = ACCENT_CYAN
    p.space_after = Pt(8)

    dag_items = [
        "全生命周期事件追踪：每个增量事件自动携带 event_id, parent_id 与 causal_depth；",
        "网状拓扑节点建模：区分 USER_INPUT, EXTERNAL_RESOURCE, TOOL_CALL, SUBAGENT；",
        "逆向 DFS 根因回溯：自阻断叶子节点逆流而上，秒级锁定引爆攻击的始作俑者；",
        "原生导出交互大屏：内核内置 provenance_dag.py，可一键生成交互式 HTML 大屏，清晰呈现攻击路径与影响范围。"
    ]
    for d in dag_items:
        p = tf_dag.add_paragraph()
        p.text = "• " + d
        p.font.name = "宋体"
        p.font.size = Pt(12)
        p.font.color.rgb = TEXT_MAIN
        p.space_before = Pt(5)
        p.line_spacing = 1.2

    # ==========================================
    # SLIDE 7: 实验验证与消融对比
    # ==========================================
    slide7 = prs.slides.add_slide(blank_layout)
    add_background(slide7, LIGHT_BG)
    add_header(slide7, "六、 实验验证与核心消融对比（真机实测数据）", "2×A100 80GB 真实环境，物理文件 MD5 与独立 Canary 监听客观核验，拒绝对齐欺骗")

    # 放置实测表格
    rows, cols = 8, 5
    tbl_shape = slide7.shapes.add_table(rows, cols, Inches(0.8), Inches(1.8), Inches(11.73), Inches(4.8))
    tbl = tbl_shape.table
    tbl.columns[0].width = Inches(3.2)
    tbl.columns[1].width = Inches(2.1)
    tbl.columns[2].width = Inches(2.1)
    tbl.columns[3].width = Inches(2.1)
    tbl.columns[4].width = Inches(2.23)

    table_data = [
        ["评测维度", "无防护裸 Agent", "仅规则 (Rule-Only)", "仅看增量 (Delta-Only)", "D²Guard 完整系统"],
        ["12 类典型场景完全阻断率", "0.0% (全部失守)", "16.7% (仅防正则)", "58.3% (状态断裂)", "91.7% (全面防御)"],
        ["跨多轮长间隔外发拦截率", "0.0%", "0.0%", "42.9% (多轮漏报)", "100.0% (状态强锁定)"],
        ["多轮分片外发完全阻断率", "0.0%", "0.0%", "0.0% (分片漏报)", "100.0% (滑动窗口熔断)"],
        ["分片外发部分泄露率", "100.0%", "100.0%", "100.0%", "0.0% (彻底阻断)"],
        ["7 类对抗样本防御率", "0.0%", "14.3%", "42.9%", "71.4% (快慢双镜)"],
        ["良性任务误拦截率 (FPR)", "0.0%", "0.0%", "0.0%", "0.0% (零误报)"],
        ["单次调用额外延迟 (p50)", "0.25 ms", "0.01 ms", "5.76 ms", "3.74 ms (远优于<20ms)"]
    ]

    for r_i, row in enumerate(table_data):
        for c_i, val in enumerate(row):
            cell = tbl.cell(r_i, c_i)
            cell.text = val
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if c_i > 0 else PP_ALIGN.LEFT
            p.font.name = "黑体" if r_i == 0 or c_i == 4 else "宋体"
            p.font.size = Pt(11.5 if r_i == 0 else 11)
            p.font.bold = (r_i == 0 or c_i == 4)
            if r_i == 0:
                p.font.color.rgb = TEXT_WHITE
                cell.fill.solid()
                cell.fill.fore_color.rgb = PRIMARY_BLUE
            elif c_i == 4:
                p.font.color.rgb = PRIMARY_BLUE
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(239, 246, 255)
            else:
                p.font.color.rgb = TEXT_MAIN
                cell.fill.solid()
                cell.fill.fore_color.rgb = CARD_BG

    # ==========================================
    # SLIDE 8: 工程化落地与在线公网演练舱
    # ==========================================
    slide8 = prs.slides.add_slide(blank_layout)
    add_background(slide8, LIGHT_BG)
    add_header(slide8, "七、 工程化落地与在线公网演练大屏", "已上线公网高保真交互演练舱，支持同屏 ReAct 循环对比、因果 DAG 展开与双 LLM 切换")

    add_card(slide8, 0.8, 1.8, 5.7, 5.0)
    tb_demo = slide8.shapes.add_textbox(Inches(1.05), Inches(2.0), Inches(5.2), Inches(4.5))
    tf_demo = tb_demo.text_frame
    tf_demo.word_wrap = True

    p = tf_demo.paragraphs[0]
    p.text = "公网实时交互演练舱 (Live Demo)"
    p.font.name = "黑体"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_BLUE
    p.space_after = Pt(8)

    demo_features = [
        "公网在线体验：https://agent.li33.art/safe (反代直连 2×A100 算力机)；",
        "同屏攻防对比：左侧【未防护裸跑】vs 右侧【D²Guard 护航】，真实触发与拦截一目了然；",
        "动态因果 DAG 展开：每次攻击触发时，交互拓扑实时高亮标红根因节点与外泄阻断点；",
        "双模型动态热切换：大屏提供下拉胶囊，支持实时切换 DeepSeek-v3.2 与本地 Qwen-27B；",
        "一键热更脚本：./deploy.sh update 实现代码与算力机秒级平滑热更。"
    ]
    for df in demo_features:
        p = tf_demo.add_paragraph()
        p.text = "• " + df
        p.font.name = "宋体"
        p.font.size = Pt(12)
        p.font.color.rgb = TEXT_MAIN
        p.space_before = Pt(6)
        p.line_spacing = 1.25

    add_card(slide8, 6.8, 1.8, 5.7, 5.0)
    tb_deliv = slide8.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.5))
    tf_deliv = tb_deliv.text_frame
    tf_deliv.word_wrap = True

    p = tf_deliv.paragraphs[0]
    p.text = "初赛申报材料与工程资产就绪"
    p.font.name = "黑体"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = ACCENT_CYAN
    p.space_after = Pt(8)

    deliv_items = [
        "《作品报告》Word 终稿：严格对齐大赛排版规范(宋体小四1.5倍行距)，规范三线表，匿名合规；",
        "完整开源代码仓库：https://github.com/ZXFqwert/D2Guard (私有仓库，版本管理完备)；",
        "自动化评测套件：run_eval.py 一键复现全部 12 类场景与消融指标；",
        "官方加分项 1:1 物理复现：真实复现并彻底防御 GitHub Copilot CVE-2025-53773 间接注入篡改配置免审查致 RCE 漏洞，达成 0.05ms 物理阻断与 0 字节外发；",
        "原生 MCP 安全网关与国际标准：实现 MCP JSON-RPC 2.0 中间人代理，全面对齐 MITRE ATLAS 2026.09 矩阵并生成 Agent-SOC 态势大屏。"
    ]
    for di in deliv_items:
        p = tf_deliv.add_paragraph()
        p.text = "• " + di
        p.font.name = "宋体"
        p.font.size = Pt(12)
        p.font.color.rgb = TEXT_MAIN
        p.space_before = Pt(6)
        p.line_spacing = 1.25

    # ==========================================
    # SLIDE 9: 总结与下一步冲刺
    # ==========================================
    slide9 = prs.slides.add_slide(blank_layout)
    add_background(slide9, DARK_BG)

    tb9 = slide9.shapes.add_textbox(Inches(1.5), Inches(1.5), Inches(10.33), Inches(4.8))
    tf9 = tb9.text_frame
    tf9.word_wrap = True

    p = tf9.paragraphs[0]
    p.text = "八、 总结与冲刺规划 (距 10.22 截止)"
    p.font.name = "黑体"
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = TEXT_WHITE
    p.space_after = Pt(20)

    milestones = [
        ("【已完成】架构与核心接口跑通", "D²Guard 三大接口、快慢双镜决策、安全状态聚合机与滑动窗口算法全部真机验证通过。"),
        ("【已完成】客观评测与材料就绪", "消融实验真实数据出炉(阻断率 91.7%, 跨轮分片 100%, FPR 0.0%)，作品报告终稿就绪，公网演示舱平稳运行。"),
        ("【冲刺中】答辩演示视频录制 (10.15-10.18)", "基于公网大屏录制 5 分钟高冲击力攻防实操对比与 DAG 展开视频，突出真实外发对比与熔断特性。"),
        ("【待提交】初赛材料终审与系统提交 (10.20-10.22)", "完成原创性声明签名盖章扫描，提交作品报告、源码包与部署说明文档，冲刺全国一等奖！")
    ]

    for m_t, m_d in milestones:
        p = tf9.add_paragraph()
        p.text = m_t + "：" + m_d
        p.font.name = "宋体"
        p.font.size = Pt(13)
        p.font.color.rgb = RGBColor(226, 232, 240)
        p.space_before = Pt(8)
        p.line_spacing = 1.3

    prs.save("双镜_D2Guard_项目汇报.pptx")
    print("[SUCCESS] PPT 已生成: 双镜_D2Guard_项目汇报.pptx")

if __name__ == "__main__":
    create_deck()
