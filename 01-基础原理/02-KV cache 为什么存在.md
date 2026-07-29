---
tags:
  - ai工程/基础原理
stage: 0
status: todo
aliases:
  - KV cache
---
生成第 100 个字的时候，前面 99 个字的 key 和 value 一模一样，没必要再算一遍。就这么简单的一个想法，撑起了整个推理服务的成本结构。

## 一句话

K 和 V 只取决于历史 token、不随新 query 改变，所以能缓存；缓存把重复计算从 $O(T^2)$ 压到 $O(T)$，代价是一块随「上下文 × 并发」线性增长的显存。

## 原理

### 先看不缓存有多亏

生成是一个字一个字来的：算出第 5 个字，把它接到输入末尾，再算第 6 个。每一步都要跑一遍完整的模型。

问题在于，跑第 5 步时模型要用到前面 4 个 token 的 key 和 value，而这 4 份 K、V 在第 4 步、第 3 步就已经算过了——**而且算出来一模一样**。

![[有没有 KV cache 的差别.excalidraw.md|700]]

不缓存的话，生成 $T$ 个 token 要做 $1+2+\cdots+T = O(T^2)$ 次 K/V 计算；缓存之后每步只算新来的那一个，总共 $O(T)$。**省下 $T$ 倍**——上下文 8000 个 token 时，这是八千倍的差距。

所以 KV cache 不是一个优化选项，是让自回归生成在工程上可行的前提。

### 为什么 K、V 能缓存，Q 不能

回到 attention 的定义（见 [[01-Transformer 与 attention]]）：每个 token 从自己的表示投影出 query、key、value 三样东西。关键在于**三样东西的生命周期不同**：

| | 是谁的函数 | 会不会变 | 能不能缓存 |
| --- | --- | --- | --- |
| K、V | 只取决于**它自己那个 token** | 算出来就不再变 | **能** |
| Q | 只取决于**当前正在生成的位置** | 每步都是新的 | 不需要，用完就扔 |
| attention 权重 | 取决于 Q 和全部 K | 每步都变 | 不能 |

第 3 个 token 的 key，是在第 3 个 token 进来时算出来的。第 100 步再用它，值还是那个值——因为**没有任何东西会回头改写它**。causal mask 保证了位置 3 看不见位置 4 之后的内容，所以它的表示不会因为后面来了新 token 而变化。

Q 则相反：第 100 步的 query 来自第 100 个位置，第 101 步就换成第 101 个位置的了。它天生是一次性的。

> [!info] 一句话记住
> **K、V 是「我能提供什么」，写好了挂在那儿等人来查；Q 是「我现在要找什么」，每次问的问题都不一样。** 挂着的可以存，问题不用存。

### 缓存里到底存了什么

每一层、每个 KV 头、每个已处理过的 token，都有一份 K 和一份 V。所以大小是：

$$
2 \times L \times H_{kv} \times d_h \times S \times B \times \text{dtype}
$$

层数 × KV 头数 × 头维度 × 序列长度 × 并发数 × 每个数的字节数；最前面的 2 是 K 和 V 各一份。

注意两个乘数：**序列长度**和**并发数**。KV cache 不是固定开销，而是随「上下文开多长 × 同时服务多少人」两个维度同时增长。手算和实测校验见 [[03-KV cache 管理与显存测算]]。

### 顺手推出 GQA 为什么有效

上面公式里有个 $H_{kv}$——KV 头的数量。

标准多头注意力（MHA）里每个 query 头配一个自己的 KV 头，$H_{kv}$ 等于头数。**GQA** 让多个 query 头共享同一组 KV：比如 32 个 query 头只配 8 组 KV，$H_{kv}$ 从 32 降到 8，**KV cache 直接小 4 倍**。MQA 更极端，全部 query 头共享 1 组。

代价是表达力略有损失，但显存收益太划算，所以现在的模型基本都用 GQA。看 `config.json` 里 `num_key_value_heads` 比 `num_attention_heads` 小多少，就知道省了几倍，见 [[02-开源权重包里有什么]]。

### 它把成本结构变成了什么样

有了缓存之后，生成分成性质完全不同的两段：

- **吃输入**：一次性把整段 prompt 的 K、V 全算出来存好
- **吐输出**：每步只算一个新 token 的 K、V 追加进去，然后读**全部**历史 K、V 做 attention

第二段每一步都要把整个缓存读一遍。所以随着生成变长，每步要搬的数据越来越多——这是长回答后半段会变慢的直接原因。两阶段的完整对比见 [[01-Prefill vs Decode]]。

## 动手做

- [ ] 用 numpy 写一个不带缓存的朴素生成循环，逐步打印每步算了多少次 K/V，画出累计曲线
- [ ] 加上 KV cache，让第 $t$ 步只算 1 个 token 的 K、V，与不带缓存的版本**逐 token 比对输出**，确认完全一致
- [ ] 记录两版生成 512 个 token 的耗时，看比值是否接近理论上的 $T$ 倍
- [ ] 从某个模型的 `config.json` 读出 `num_attention_heads` 和 `num_key_value_heads`，算出 GQA 省了几倍
- [ ] 故意往缓存里塞错误的历史 K、V，观察输出怎么崩——体会缓存一致性为什么重要

## 算学会了

- [ ] 能解释为什么 K、V 可以缓存而 Q 不行，理由说得出「因为它是谁的函数」
- [ ] 能说出不缓存与缓存后的复杂度，以及差几倍
- [ ] 能凭 `config.json` 里那两个头数，当场说出 GQA 省了多少 KV cache
- [ ] 知道 KV cache 随「上下文 × 并发」两个维度增长，不是固定开销
- [ ] 能解释为什么长回答的后半段会变慢

## 坑

**以为 KV cache 是可选优化。** 关掉它自回归生成在工程上根本不可行。所有关于推理性能的讨论都默认它开着。

**忘了它随并发涨。** 单人测试时 KV cache 微不足道，一上生产并发就成了显存的大头，然后 OOM。这是最常见的一次性翻车。

**以为缓存的是 attention 结果。** 缓存的是 K 和 V 这两个中间量；注意力权重每步都得重算，因为 Q 变了。

**跨请求乱复用缓存。** 只有前缀**完全相同**的请求才能共享，差一个 token 都不行。带上租户和权限维度还有安全问题，见 [[05-缓存安全与跨租户命中]]。

## 关联
- [[01-Transformer 与 attention]]
- [[03-KV cache 管理与显存测算]]
- [[01-Prefill vs Decode]]
- [[05-Prefix caching]]
- [[07-位置编码与长度外推]]

## 参考
- [Fast Transformer Decoding: One Write-Head is All You Need](https://arxiv.org/abs/1911.02150) — Shazeer，2019。MQA 的出处，也是把 KV cache 当成核心瓶颈来处理的开端
- [GQA: Training Generalized Multi-Query Transformer Models](https://arxiv.org/abs/2305.13245) — Ainslie 等，2023。MHA 与 MQA 之间的折中
- [Efficient Memory Management for LLM Serving with PagedAttention](https://arxiv.org/abs/2309.06180) — vLLM 论文，第 2 节把 KV cache 的增长特性讲得很清楚
