---
tags:
  - ai工程/产品
  - 里程碑
stage: 9
status: todo
---
## 交付物

一条跑通的链路：**线上信号 → 拉回上下文 → 人工判定 → 进 golden set → 卡住 CI**，外加一个可核对的数字。

- 至少三种信号的采集，**必须包含「用户修改了答案」**——这是信息量最高的一种
- 每条信号能一键拉回：完整输入输出、**检索到的片段**、模型与提示词版本
- 一个按优先级排序的人工判定队列
- 判定为真错的样本能一键补进 golden set，带上正确答案与来源标记
- CI 里跑 golden set，分数掉了挡住合并，见 [[02-回归测试与 CI 门禁]]
- **一个数字**：过去 30 天有多少条线上失败变成了测试样本
- 一批**不受反馈影响**的基准样本，用于检测过拟合

![[用户信号流入 eval 集.excalidraw.md|700]]

## 做法

1. 盘点现在采了哪些信号、哪些被扔掉了，见 [[06-用户信号如何变成 eval 与训练数据]]
2. 先实现「用户修改」的采集，记下改前改后——它同时给了「错在哪」和「正确答案是什么」
3. 给每条信号关联 trace id、检索片段、模型与提示词版本，见 [[07-数据版本化]]
4. 把拒绝原因做成**选项**而不是自由文本，否则没法统计
5. 抽 50 条 👎 人工判定，算出真错比例——这个数会让你意识到闸门的必要性
6. 建判定队列，按「重复模式 × 与现有 golden set 的距离」排序
7. 判定通过的补进 golden set，打版本号
8. 划出一个长期不动的稳定核心集，专门看趋势

### 采集与排序骨架

```python
import json, uuid, pathlib

SIGNALS = pathlib.Path("signals.jsonl")

def record(trace_id, kind, payload):
    # kind: edited | rejected | retried | escalated | thumbs_down
    SIGNALS.open("a", encoding="utf-8").write(json.dumps({
        "signal_id": str(uuid.uuid4()),
        "trace_id":  trace_id,        # 关键：能拉回完整调用链
        "kind":      kind,
        **payload,                     # edited 时带 before / after
    }, ensure_ascii=False) + "\n")

def rank(signals, golden_vecs, embed):
    # 重复出现的 × 与现有 golden set 不重合的，优先
    from collections import Counter
    themes = Counter(s.get("theme") for s in signals)
    scored = []
    for s in signals:
        v = embed(s["input"])
        novelty = 1 - max(float(v @ g) for g in golden_vecs)
        scored.append((themes[s.get("theme")] * novelty, s))
    return [s for _, s in sorted(scored, key=lambda x: -x[0])]
```

补进 golden set 时**记下来源是线上信号还是人工构造**——后面统计闭环产出全靠这个字段。

## 结果与数据

| 项 | 数值 |
| --- | --- |
| 采集的信号种类 | |
| 👎 的**真错比例** | |
| 判定队列的积压量 / 周处理量 | |
| 过去 30 天新增 golden 样本数 | |
| **其中来自线上信号的占比** | |
| 稳定核心集规模 | |
| 信号出现到进 CI 的中位时长 | |

## 复盘

- 👎 的真错比例是多少？低于五成的话，「信号直接当标签」这条路就彻底堵死了
- **从信号出现到变成测试样本要几天？** 这个时长决定了闭环有没有实际价值
- 判定队列积压了吗？积压说明排序不够狠或者没人负责
- 来自线上的样本占比多少？太低说明闭环没真正跑起来
- **稳定核心集的分数在动吗？** 它掉了而 golden set 总分没掉，就是在过拟合反馈了

## 常见卡点

**信号采到了但拉不回上下文。** 最常见的返工原因。trace 关联要趁早补，事后没有原始上下文了，见 [[01-Trace 与 Span]]。

**判定队列没人处理。** 队列要有人负责，且必须排优先级——全都判是不现实的。

**样本加得太快，分数不可比。** 每次加样本都要打版本号，并同时报告新旧两个数。

**闭环跑起来之后过拟合。** 只优化有人抱怨的地方，没人抱怨的地方悄悄退步。稳定核心集就是防这个的。

## 关联
- [[06-用户信号如何变成 eval 与训练数据]]
- [[07-数据版本化]]
- [[01-Golden set]]
- [[02-回归测试与 CI 门禁]]
- [[03-HITL 交互设计]]
