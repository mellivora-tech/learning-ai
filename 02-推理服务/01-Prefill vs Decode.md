---
tags:
  - ai工程/推理服务
stage: 8
status: todo
aliases:
  - prefill
  - decode
  - TTFT
  - TPOT
---
同一个模型、同一张卡，吃输入和吐输出是两种完全不同的活。分不清这两段，性能调优就全在瞎猜。

## 一句话

Prefill 一次并行处理整段输入、卡在算力上；decode 一次只出一个 token、卡在显存带宽上——两段落在 roofline 拐点的两侧，所以优化手段完全不通用。

## 原理

### 两段在做什么

![[Prefill 与 Decode 的分工.excalidraw.md|700]]

**Prefill（预填充）**：把你的整段 prompt 一次性喂进去，并行算出所有位置的 K、V 存进缓存，顺便得到最后一个位置的输出，也就是第一个生成的 token。输入 2000 个 token 就一次处理 2000 个。

**Decode（解码）**：从第二个 token 开始，每次只处理**一个**新 token。算它的 Q、K、V，把 K、V 追加进缓存，读全部历史 K、V 做 attention，出一个新 token，接回去，再来一遍。输出 500 个 token 就要跑 500 次。

差别就在 Q 的长度：prefill 时 Q 是 `[B, h, T, dh]`，decode 时是 `[B, h, 1, dh]`。**一个字之差，整个性能画像就翻转了。**

### 为什么性质相反

在 [[02-算力经常用不满：两种瓶颈]] 里推过算术强度——每搬一字节做多少次运算。H100 的拐点约 590 FLOP/byte。

|         | 每步搬多少        | 每步算多少      | 算术强度                  | 落在拐点哪侧               |
| ------- | ------------ | ---------- | --------------------- | -------------------- |
| Prefill | 权重一遍，$2N$ 字节 | $2NT$ FLOP | $\approx T$（几千）       | 右侧，**compute-bound** |
| Decode  | 权重一遍，$2N$ 字节 | $2NB$ FLOP | $\approx B$（batch 大小） | 左侧，**memory-bound**  |

同一张卡，prefill 时算力吃满、带宽有余；decode 时反过来，算力大量空转，全在等权重从显存搬过来。

**这一条推出了后面几乎所有结论**：

- Decode 想快，靠**减少要搬的字节**——量化，见 [[09-量化]]
- Decode 想提吞吐，靠**加大 batch**——每搬一次权重多服务几个请求，见 [[07-Continuous batching]]
- Prefill 加大 batch 收益有限，它本来就吃满了
- 换一张算力更强但带宽没提升的卡，decode 一点都不会变快

### 两个指标，各管一段

| 指标 | 全称 | 量的是 | 由谁决定 |
| --- | --- | --- | --- |
| **TTFT** | Time To First Token | 从发请求到第一个字 | prefill 耗时，随**输入长度**涨 |
| **TPOT** | Time Per Output Token | 后续每个字的间隔 | decode 单步耗时，随**batch 和上下文**涨 |

用户感知上这两个也是分开的：TTFT 决定「它反应快不快」，TPOT 决定「它说话流畅不流畅」。聊天场景里 TTFT 超过一秒就明显难受，而 TPOT 只要比人的阅读速度快就够了。

一次请求的总耗时大致是：

$$
\text{总时间} \approx \text{TTFT} + \text{TPOT} \times (\text{输出长度} - 1)
$$

指标体系的完整定义见 [[02-指标体系]]。

### 为什么输出比输入贵得多

这是这一篇最该带走的结论。

输入 1000 个 token：**一次** prefill，并行算完。
输出 1000 个 token：**跑 1000 次** decode，每次都要把全部权重读一遍。

所以 API 定价里输出通常是输入的三到五倍，不是厂商想多赚，是成本结构就长这样。

顺带一个实用推论：**想省钱，先想办法让模型少说话。** 让它输出结构化的短结果而不是长篇解释，收益比优化 prompt 长度大得多，见 [[04-成本归因与每次成功任务成本]]。

### 两段抢同一张卡

真实服务里 prefill 和 decode 是混在一起的：新请求要 prefill，老请求在 decode。它们抢同一批计算资源，而且互相干扰。

一个长 prompt 的 prefill 可能占住 GPU 几百毫秒，这期间所有正在 decode 的请求都被卡住——**表现是别人的 TPOT 突然抖一下**。这类抖动很难从单个请求的日志里看出来，得看全局。

工程上有两种应对：

- **Chunked prefill**：把长 prompt 切成小块，和 decode 交错着做，用略高的 TTFT 换平稳的 TPOT
- **PD 分离**：prefill 和 decode 跑在不同的卡甚至不同的机器上，各自按自己的瓶颈配硬件。代价是要把 KV cache 跨节点传过去

选哪个取决于你的业务更在意首字还是更在意流畅。

## 动手做

- [ ] 固定输出长度，把输入从 128 扫到 32k，画 TTFT 曲线——确认它随输入长度增长
- [ ] 固定输入长度，把输出从 16 扫到 2048，画总耗时曲线——斜率就是 TPOT
- [ ] 同一模型 BF16 与 FP8 各测一次，看 TPOT 改善多少、TTFT 改善多少，验证两者受益不同
- [ ] 并发从 1 加到 64，观察 TPOT 怎么变、总吞吐怎么变——这是 batch 的效果
- [ ] 在稳定 decode 的过程中插入一个超长 prompt，看其他请求的 TPOT 抖动多大
- [ ] 开启 chunked prefill 再测一次，对比 TTFT 和 TPOT 的取舍

## 算学会了

- [ ] 能说出 prefill 和 decode 各卡在什么资源上，理由说得出算术强度
- [ ] 有人说「上下文从 8k 提到 128k」，能分开说清对 TTFT、对显存、对并发各意味着什么
- [ ] 能解释为什么输出比输入贵，以及为什么是三到五倍这个量级
- [ ] 看到 TPOT 抖动，第一反应是查有没有长 prompt 在抢 prefill
- [ ] 知道量化和加 batch 分别改善哪一段，不会拿错工具

## 坑

**用一个「延迟」指标概括一切。** TTFT 和 TPOT 由完全不同的因素决定，合成一个平均延迟之后，任何异常都看不出来了。

**拿 prefill 的优化经验去调 decode。** 加大 batch 对 decode 是核心手段，对 prefill 帮助有限还可能拖长 TTFT。

**按算力选卡。** decode 阶段算力大量空转，带宽才是瓶颈。见 [[01-一张卡的四个关键数字]]。

**忽略输出长度对成本的影响。** 很多团队花大力气压缩 prompt，却放任模型输出长篇大论——后者贵得多。

**以为长 prompt 只影响自己。** 它会拖累同一批次里所有正在 decode 的请求，而且不出现在它自己的指标里。

## 关联
- [[02-指标体系]]
- [[07-Continuous batching]]
- [[02-KV cache 为什么存在]]
- [[02-算力经常用不满：两种瓶颈]]
- [[09-量化]]

## 参考
- [Efficient Memory Management for LLM Serving with PagedAttention](https://arxiv.org/abs/2309.06180) — vLLM 论文，两阶段的调度问题
- [Orca: A Distributed Serving System for Transformer-Based Generative Models](https://www.usenix.org/conference/osdi22/presentation/yu) — 迭代级调度的出处，也是最早把两阶段说清楚的系统论文之一
- [DistServe: Disaggregating Prefill and Decoding](https://arxiv.org/abs/2401.09670) — PD 分离的动机与收益分析
