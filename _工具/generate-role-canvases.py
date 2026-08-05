#!/usr/bin/env python3
"""
生成岗位专用思维导图（Obsidian Canvas）

用法：
    python3 _工具/generate-role-canvases.py

输出：_岗位图谱/ 目录下的一组 .canvas 文件 + 索引
"""

import json
import os

OUT_DIR = "_岗位图谱"

ROLES = [
    {
        "id": "harness-agent",
        "title": "Harness Agent Engineer",
        "subtitle": "单 Agent 提示工程 · 上下文管理 · 工具合约",
        "color": "1",
        "skills": [
            {
                "name": "Prompt Harnessing",
                "subs": [
                    {"name": "system prompt 设计", "notes": ["01-Harness engineering"]},
                    {"name": "few-shot / in-context learning", "notes": ["01-Harness engineering"]},
                    {"name": "instruction following", "notes": ["01-Harness engineering"]},
                ],
            },
            {
                "name": "Context Engineering",
                "subs": [
                    {"name": "上下文预算分配", "notes": ["02-Context engineering：上下文即预算"]},
                    {"name": "compaction", "notes": ["03-Compaction 与外部记忆文件"]},
                    {"name": "prompt caching", "notes": ["04-Prompt caching"]},
                    {"name": "semantic caching", "notes": ["05-Semantic caching 与假命中"]},
                ],
            },
            {
                "name": "Agent 控制面",
                "subs": [
                    {"name": "五类硬预算", "notes": ["01-五类硬预算"]},
                    {"name": "终止条件", "notes": ["02-终止条件"]},
                    {"name": "模型路由与级联", "notes": ["04-模型路由与级联"]},
                    {"name": "降级链", "notes": ["04-降级链"]},
                ],
            },
            {
                "name": "结构化输出",
                "subs": [
                    {"name": "三档方案", "notes": ["01-结构化输出三档"]},
                    {"name": "修复循环", "notes": ["02-修复循环（报错回灌）"]},
                    {"name": "截断处理", "notes": ["03-截断处理与 finish_reason"]},
                ],
            },
            {
                "name": "工具合约",
                "subs": [
                    {"name": "五段式模板", "notes": ["05-工具合约五段式模板"]},
                    {"name": "四层参数校验", "notes": ["06-四层参数校验"]},
                    {"name": "幂等性与故障注入", "notes": ["07-幂等性与故障注入"]},
                ],
            },
            {
                "name": "Agent 评估",
                "subs": [
                    {"name": "golden set", "notes": ["01-Golden set"]},
                    {"name": "回归测试与 CI 门禁", "notes": ["02-回归测试与 CI 门禁"]},
                    {"name": "judge 校准", "notes": ["04-Judge 校准"]},
                ],
            },
        ],
    },
    {
        "id": "multi-agent",
        "title": "Multi-Agent Engineer",
        "subtitle": "多 Agent 编排 · MCP · 上下文隔离",
        "color": "2",
        "skills": [
            {
                "name": "编排模式",
                "subs": [
                    {"name": "supervisor 模式", "notes": ["09-多 Agent 编排模式"]},
                    {"name": "swarm 模式", "notes": ["09-多 Agent 编排模式"]},
                    {"name": "handoff 模式", "notes": ["09-多 Agent 编排模式"]},
                ],
            },
            {
                "name": "MCP",
                "subs": [
                    {"name": "设计动机与协议", "notes": ["08-MCP"]},
                    {"name": "server / client 边界", "notes": ["08-MCP"]},
                    {"name": "工具描述注入面", "notes": ["08-MCP"]},
                ],
            },
            {
                "name": "上下文隔离",
                "subs": [
                    {"name": "supervisor + sub-agent 隔离", "notes": ["91-里程碑：supervisor + sub-agent 上下文隔离系统"]},
                    {"name": "消息传递边界", "notes": ["09-多 Agent 编排模式"]},
                    {"name": "共享与私有上下文", "notes": ["09-多 Agent 编排模式"]},
                ],
            },
            {
                "name": "沙箱化执行",
                "subs": [
                    {"name": "代码执行沙箱", "notes": ["10-沙箱化代码执行"]},
                    {"name": "computer use", "notes": ["11-Computer use"]},
                ],
            },
            {
                "name": "任务分解",
                "subs": [
                    {"name": "任务分解策略", "notes": ["12-任务分解策略"]},
                    {"name": "子任务分配", "notes": ["12-任务分解策略"]},
                ],
            },
            {
                "name": "协调与容错",
                "subs": [
                    {"name": "分布式锁", "notes": ["06-分布式锁"]},
                    {"name": "超时与背压", "notes": ["03-超时与背压"]},
                    {"name": "故障降级", "notes": ["05-故障降级与混沌测试"]},
                ],
            },
        ],
    },
    {
        "id": "workflow",
        "title": "Workflow Engineer",
        "subtitle": "确定性工作流 · 状态机 · 断点续跑",
        "color": "3",
        "skills": [
            {
                "name": "状态机",
                "subs": [
                    {"name": "显式状态设计", "notes": ["02-状态机"]},
                    {"name": "持久化", "notes": ["02-状态机", "05-断点续跑"]},
                    {"name": "转换日志", "notes": ["02-状态机"]},
                    {"name": "非法转换拒绝", "notes": ["02-状态机"]},
                ],
            },
            {
                "name": "异步队列",
                "subs": [
                    {"name": "任务队列", "notes": ["01-异步任务队列"]},
                    {"name": "超时", "notes": ["03-超时与背压"]},
                    {"name": "背压", "notes": ["03-超时与背压"]},
                ],
            },
            {
                "name": "断点续跑",
                "subs": [
                    {"name": "checkpoint", "notes": ["05-断点续跑"]},
                    {"name": "幂等存储", "notes": ["07-幂等存储与去重"]},
                    {"name": "replay 确定性", "notes": ["05-断点续跑"]},
                ],
            },
            {
                "name": "流式与中断",
                "subs": [
                    {"name": "流式输出", "notes": ["04-流式与可中断 UX"]},
                    {"name": "可中断 UX", "notes": ["04-流式与可中断 UX"]},
                ],
            },
            {
                "name": "韧性",
                "subs": [
                    {"name": "降级链", "notes": ["04-降级链"]},
                    {"name": "韧性组件", "notes": ["07-韧性组件"]},
                    {"name": "故障降级", "notes": ["05-故障降级与混沌测试"]},
                ],
            },
        ],
    },
    {
        "id": "rag-engineer",
        "title": "RAG Engineer",
        "subtitle": "检索增强生成 · chunking · embedding · rerank",
        "color": "4",
        "skills": [
            {
                "name": "Chunking",
                "subs": [
                    {"name": "四种策略", "notes": ["01-Chunking 四种策略"]},
                    {"name": "按文档类型选择", "notes": ["01-Chunking 四种策略"]},
                ],
            },
            {
                "name": "Embedding",
                "subs": [
                    {"name": "模型选型", "notes": ["02-Embedding 模型选型与评估"]},
                    {"name": "评估", "notes": ["02-Embedding 模型选型与评估"]},
                    {"name": "向量空间", "notes": ["06-Embedding 与向量空间"]},
                ],
            },
            {
                "name": "检索",
                "subs": [
                    {"name": "Hybrid search", "notes": ["03-Hybrid search（dense + BM25 + RRF）"]},
                    {"name": "BM25 + dense", "notes": ["03-Hybrid search（dense + BM25 + RRF）"]},
                    {"name": "RRF 合并", "notes": ["03-Hybrid search（dense + BM25 + RRF）"]},
                ],
            },
            {
                "name": "Rerank",
                "subs": [
                    {"name": "cross-encoder 精排", "notes": ["04-Rerank（cross-encoder 精排）"]},
                ],
            },
            {
                "name": "Freshness",
                "subs": [
                    {"name": "tombstone 删除传播", "notes": ["05-Freshness 与 tombstone 删除传播"]},
                    {"name": "幽灵文档测试", "notes": ["06-幽灵文档测试"]},
                ],
            },
            {
                "name": "检索评估",
                "subs": [
                    {"name": "两段式评估", "notes": ["06-检索评估两段式"]},
                    {"name": "recall@k", "notes": ["06-检索评估两段式"]},
                    {"name": "groundedness", "notes": ["06-检索评估两段式"]},
                ],
            },
            {
                "name": "多模态 RAG",
                "subs": [
                    {"name": "接入点", "notes": ["07-多模态 RAG 的接入点", "03-多模态 RAG"]},
                ],
            },
        ],
    },
    {
        "id": "inference-engineer",
        "title": "推理服务工程师",
        "subtitle": "模型部署 · 推理引擎 · 性能优化 · 容量规划",
        "color": "5",
        "skills": [
            {
                "name": "GPU 基础",
                "subs": [
                    {"name": "四个关键数字", "notes": ["01-一张卡的四个关键数字"]},
                    {"name": "瓶颈诊断", "notes": ["02-算力经常用不满：两种瓶颈"]},
                    {"name": "多卡互联", "notes": ["04-多卡怎么连"]},
                ],
            },
            {
                "name": "推理引擎",
                "subs": [
                    {"name": "Prefill vs Decode", "notes": ["01-Prefill vs Decode"]},
                    {"name": "PagedAttention", "notes": ["04-PagedAttention 与分页显存"]},
                    {"name": "Continuous batching", "notes": ["07-Continuous batching"]},
                    {"name": "Prefix caching", "notes": ["05-Prefix caching"]},
                ],
            },
            {
                "name": "KV Cache",
                "subs": [
                    {"name": "为什么存在", "notes": ["02-KV cache 为什么存在"]},
                    {"name": "显存测算", "notes": ["03-KV cache 管理与显存测算"]},
                ],
            },
            {
                "name": "优化手段",
                "subs": [
                    {"name": "量化", "notes": ["09-量化"]},
                    {"name": "投机解码", "notes": ["08-投机解码"]},
                    {"name": "驱逐与内存压力", "notes": ["06-驱逐与内存压力"]},
                ],
            },
            {
                "name": "指标与调优",
                "subs": [
                    {"name": "指标体系", "notes": ["02-指标体系"]},
                    {"name": "吞吐-延迟帕累托", "notes": ["10-吞吐-延迟帕累托前沿"]},
                ],
            },
            {
                "name": "容量与成本",
                "subs": [
                    {"name": "GPU 容量规划", "notes": ["01-GPU 容量规划"]},
                    {"name": "成本预测", "notes": ["05-成本预测"]},
                ],
            },
        ],
    },
    {
        "id": "ai-security",
        "title": "AI 安全工程师",
        "subtitle": "提示注入 · 纵深防御 · 多租户隔离",
        "color": "6",
        "skills": [
            {
                "name": "提示注入",
                "subs": [
                    {"name": "直接 vs 间接注入", "notes": ["01-间接提示注入与 20 条攻击载荷"]},
                    {"name": "六个入口", "notes": ["01-间接提示注入与 20 条攻击载荷"]},
                    {"name": "20 条攻击载荷", "notes": ["01-间接提示注入与 20 条攻击载荷"]},
                ],
            },
            {
                "name": "纵深防御",
                "subs": [
                    {"name": "五层防御", "notes": ["02-纵深防御"]},
                    {"name": "结构化分隔", "notes": ["02-纵深防御"]},
                    {"name": "监督 agent", "notes": ["02-纵深防御"]},
                ],
            },
            {
                "name": "隔离模式",
                "subs": [
                    {"name": "dual-LLM", "notes": ["03-隔离模式（dual-LLM）"]},
                    {"name": "三种隔离模式", "notes": ["06-多租户隔离"]},
                    {"name": "最小权限", "notes": ["02-纵深防御"]},
                ],
            },
            {
                "name": "权限与缓存",
                "subs": [
                    {"name": "权限过滤时机", "notes": ["04-权限过滤时机"]},
                    {"name": "缓存跨租户命中", "notes": ["05-缓存安全与跨租户命中"]},
                ],
            },
            {
                "name": "对抗评估",
                "subs": [
                    {"name": "对抗测试集", "notes": ["03-对抗测试集"]},
                    {"name": "穿透率报告", "notes": ["90-里程碑：20 条攻击载荷 + 穿透率报告"]},
                ],
            },
        ],
    },
    {
        "id": "ai-platform",
        "title": "AI 平台工程师",
        "subtitle": "多租户平台 · 可观测性 · 容量 · 运维",
        "color": "1",
        "skills": [
            {
                "name": "多租户",
                "subs": [
                    {"name": "隔离模式", "notes": ["06-多租户隔离"]},
                    {"name": "成本按租户归因", "notes": ["04-成本归因与每次成功任务成本"]},
                    {"name": "缓存安全", "notes": ["05-缓存安全与跨租户命中"]},
                ],
            },
            {
                "name": "可观测性",
                "subs": [
                    {"name": "Trace 与 Span", "notes": ["01-Trace 与 Span"]},
                    {"name": "必打字段清单", "notes": ["02-必打字段清单"]},
                    {"name": "漂移监控", "notes": ["03-漂移监控三条线"]},
                ],
            },
            {
                "name": "评估平台",
                "subs": [
                    {"name": "CI 门禁", "notes": ["02-回归测试与 CI 门禁"]},
                    {"name": "golden set", "notes": ["01-Golden set"]},
                    {"name": "judge 校准", "notes": ["04-Judge 校准"]},
                ],
            },
            {
                "name": "Infra 与扩缩容",
                "subs": [
                    {"name": "自动扩缩容", "notes": ["02-自动扩缩容"]},
                    {"name": "冷启动", "notes": ["03-冷启动"]},
                    {"name": "多区域部署", "notes": ["04-多区域部署"]},
                ],
            },
            {
                "name": "容量与成本",
                "subs": [
                    {"name": "GPU 容量规划", "notes": ["01-GPU 容量规划"]},
                    {"name": "成本预测", "notes": ["05-成本预测"]},
                ],
            },
            {
                "name": "运维",
                "subs": [
                    {"name": "On-call 手册", "notes": ["06-On-call 手册"]},
                ],
            },
        ],
    },
]


def build_canvas(role):
    nodes = []
    edges = []
    color = role["color"]

    # 中心节点
    center_y = 100 + len(role["skills"]) * 90
    nodes.append({
        "id": "center",
        "type": "text",
        "x": 0,
        "y": center_y,
        "width": 340,
        "height": 120,
        "color": color,
        "text": f"# 🎯 {role['title']}\n\n{role['subtitle']}\n\n→ [[知识体系|总能力地图]]"
    })

    # 技能区
    group_y = 0
    for si, skill in enumerate(role["skills"]):
        n_subs = len(skill["subs"])
        group_height = max(120, n_subs * 70 + 40)

        # 分组
        group_id = f"group-{si}"
        nodes.append({
            "id": group_id,
            "type": "group",
            "x": 380,
            "y": group_y,
            "width": 1120,
            "height": group_height,
            "color": color,
            "label": skill["name"],
            "background": "transparent",
        })

        # 技能标题节点
        skill_id = f"skill-{si}"
        nodes.append({
            "id": skill_id,
            "type": "text",
            "x": 420,
            "y": group_y + 20,
            "width": 220,
            "height": 60,
            "color": color,
            "text": f"## {skill['name']}"
        })
        edges.append({
            "id": f"e-center-{si}",
            "fromNode": "center",
            "toNode": skill_id,
            "fromSide": "right",
            "toSide": "left"
        })

        # 子技能与笔记
        for ni, sub in enumerate(skill["subs"]):
            sub_y = group_y + 20 + ni * 70
            sub_id = f"sub-{si}-{ni}"
            nodes.append({
                "id": sub_id,
                "type": "text",
                "x": 720,
                "y": sub_y,
                "width": 320,
                "height": 50,
                "color": color,
                "text": f"**{sub['name']}**"
            })
            edges.append({
                "id": f"e-skill-{si}-{ni}",
                "fromNode": skill_id,
                "toNode": sub_id,
                "fromSide": "right",
                "toSide": "left"
            })

            notes_id = f"notes-{si}-{ni}"
            notes_text = "  ".join([f"[[{n}]]" for n in sub["notes"]])
            nodes.append({
                "id": notes_id,
                "type": "text",
                "x": 1100,
                "y": sub_y,
                "width": 360,
                "height": 50,
                "text": notes_text
            })
            edges.append({
                "id": f"e-sub-{si}-{ni}",
                "fromNode": sub_id,
                "toNode": notes_id,
                "fromSide": "right",
                "toSide": "left"
            })

        group_y += group_height + 30

    return {"nodes": nodes, "edges": edges}


def build_index_canvas():
    nodes = []
    edges = []
    n = len(ROLES)
    total_height = max(600, n * 130)

    nodes.append({
        "id": "center",
        "type": "text",
        "x": 0,
        "y": total_height // 2 - 60,
        "width": 340,
        "height": 120,
        "color": "1",
        "text": "# 🧭 AI Engineer\n# 岗位图谱索引\n\n按岗位定位的思维导图\n→ [[知识体系|总能力地图]]"
    })

    for i, role in enumerate(ROLES):
        y = 60 + i * 130
        node_id = f"role-{i}"
        nodes.append({
            "id": node_id,
            "type": "file",
            "x": 420,
            "y": y,
            "width": 360,
            "height": 90,
            "color": role["color"],
            "file": f"_岗位图谱/{role['id']}.canvas"
        })
        edges.append({
            "id": f"e-role-{i}",
            "fromNode": "center",
            "toNode": node_id,
            "fromSide": "right",
            "toSide": "left"
        })

    return {"nodes": nodes, "edges": edges}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    for role in ROLES:
        canvas = build_canvas(role)
        path = os.path.join(OUT_DIR, f"{role['id']}.canvas")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(canvas, f, ensure_ascii=False, indent="\t")
        print(f"Generated {path} ({len(canvas['nodes'])} nodes, {len(canvas['edges'])} edges)")

    index = build_index_canvas()
    index_path = os.path.join(OUT_DIR, "岗位图谱索引.canvas")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent="\t")
    print(f"Generated {index_path} ({len(index['nodes'])} nodes, {len(index['edges'])} edges)")


if __name__ == "__main__":
    main()
