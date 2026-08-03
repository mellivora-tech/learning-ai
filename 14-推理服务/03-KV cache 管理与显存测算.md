---
tags:
  - ai工程/推理服务
stage: 8
status: todo
aliases:
  - 显存测算
---
「这张 80G 卡、这个模型、平均 8k 上下文，能扛多少并发？」——这题该在白板上两分钟算出来，而不是压测三天试出来。

## 一句话

权重是固定开销，KV cache 是变动开销；卡的显存减去权重和余量，剩下的除以「每请求每 token 的 KV 字节数」，就是并发上限。

## 原理

### 那个公式，逐项拆开

$$
\text{KV 字节} = 2 \times L \times H_{kv} \times d_h \times S \times B \times \text{dtype}
$$

| 符号       | 是什么       | 从哪儿来                                                |
| -------- | --------- | --------------------------------------------------- |
| 2        | K 一份、V 一份 | 固定                                                  |
| $L$      | 层数        | `num_hidden_layers`                                 |
| $H_{kv}$ | KV 头数     | `num_key_value_heads`（**不是** `num_attention_heads`） |
| $d_h$    | 每个头的维度    | `head_dim`，或 `hidden_size / num_attention_heads`    |
| $S$      | 序列长度      | 你的业务，输入 + 输出                                        |
| $B$      | 并发数       | 你的业务                                                |
| dtype    | 每个数几字节    | BF16 是 2，FP8 是 1                                    |

最容易错的是 $H_{kv}$：**用成 `num_attention_heads` 会把结果放大好几倍**。现在的模型基本都用 GQA，这两个数不一样，见 [[02-KV cache 为什么存在]]。

### 拿 Qwen3-8B 手算一遍

从 `config.json` 抄出：36 层、8 个 KV 头、head_dim 128、BF16。

**单个 token 的 KV 字节数**（这个数最有用，记住它）：

$$
2 \times 36 \times 8 \times 128 \times 2 = 147{,}456 \text{ 字节} \approx 144 \text{ KB}
$$

有了它，剩下全是乘法：

| 场景 | 算式 | KV cache |
| --- | --- | --- |
| 单请求 8k 上下文 | 144 KB × 8192 | 1.13 GB |
| 并发 32、8k | × 32 | 36 GB |
| 并发 32、32k | 再 × 4 | 144 GB |
| 并发 128、8k | 144 KB × 8192 × 128 | 144 GB |

**后两行一张 80 GB 的卡都装不下。** 而且注意：上下文翻四倍和并发翻四倍，结果一模一样——这两个维度在公式里是对称的。

### 反推并发上限

一张 80 GB 的 H100 跑 Qwen3-8B：

```text
总显存                      80 GB
− 权重（82 亿 × 2 字节）      16.4 GB
− 引擎开销与碎片余量（约 15%） 12 GB
──────────────────────────────────
可用于 KV cache             51.6 GB

51.6 GB ÷ 1.13 GB（每请求 8k）≈ 45 并发
```

答案是**四十几**。这个数该是你配 `max_num_seqs` 的起点，而不是拍个 256 上去然后等它 OOM。

> [!tip] 一个更好用的换算
> 记住「每 token 144 KB」，很多问题就变心算了：**上下文每加 1k，每个请求多吃 144 MB。** 并发 32 时上下文从 8k 提到 16k，多吃 4.6 GB。
> 讨论「能不能支持更长上下文」时，这个数字比任何 benchmark 都有说服力。

### 拿实测校验

算完一定要对一次，不然错了自己不知道：

```bash
vllm serve Qwen/Qwen3-8B --max-model-len 8192 --gpu-memory-utilization 0.9
curl localhost:8000/metrics | grep -E 'gpu_cache_usage|num_requests'
```

`gpu_cache_usage_perc` 是 KV cache 用了百分之多少。压到接近 1.0 时的并发数就是实测上限。对不上通常是这四个原因：

- **`gpu_memory_utilization` 没算进去**——默认 0.9，剩下 10% 引擎不碰
- **忘了权重之外还有激活值和 CUDA context**
- **头数用错了**（最常见）
- **引擎开了 KV cache 量化**，实际 dtype 不是你以为的那个

### 分页：为什么实测能装的比手算多

朴素做法是给每个请求预留「最大长度」那么大的连续显存。可绝大多数请求用不满——预留 8k 实际只用 500，剩下全浪费。vLLM 论文里测出这种浪费能到六成以上。

**PagedAttention** 把 KV cache 切成固定大小的块（比如 16 个 token 一块），像操作系统的虚拟内存那样按需分配、不要求连续。浪费于是从「按最大长度预留」降到「最后一块的零头」。展开见 [[04-PagedAttention 与分页显存]]。

所以上面手算给的是**保守下界**，实测通常更高，够用了。

### 显存不够时的四条路

按代价从低到高：

1. **减 `max_model_len`**——多数业务用不到宣称的最大上下文，砍掉立竿见影
2. **KV cache 量化**——FP8 存 KV 直接砍半，质量影响通常比权重量化小
3. **权重量化**——腾出来的空间全给 KV cache，见 [[09-量化]]
4. **上多卡或换大显存卡**——最后才考虑，见 [[06-怎么给任务选卡]]

顺序反了会花冤枉钱：很多「显存不够」的场景，把 `max_model_len` 从 128k 改成实际需要的 8k 就解决了。

## 动手做

- [ ] 从你要跑的模型的 `config.json` 抄出四个数，算出「每 token 多少 KB」
- [ ] 用它反推一张卡上的并发上限，先写在纸上
- [ ] 起 vLLM 压到 `gpu_cache_usage_perc` 接近 1.0，记录实际并发，和手算对比
- [ ] 对不上就逐项排查：`gpu_memory_utilization`、头数、dtype、有没有开 KV 量化
- [ ] 把 `max_model_len` 翻倍再跑一次，验证并发上限大致减半
- [ ] 开 FP8 KV cache 再测一次，看并发提了多少、质量掉了多少

## 算学会了

- [ ] 能在白板上算出「这张卡这个模型这个上下文能扛多少并发」，不用查资料
- [ ] 记得住自己主力模型的「每 token 多少 KB」
- [ ] 知道 $H_{kv}$ 要用 `num_key_value_heads`，用错会放大好几倍
- [ ] 手算和实测对不上时，能列出四个原因逐一排查
- [ ] 显存不够时按代价从低到高选办法，而不是直接想加卡

## 坑

**用 `num_attention_heads` 算。** GQA 下这两个数差好几倍，算出来大幅高估，然后多买卡。

**忘了并发和上下文是乘起来的。** 「支持 128k 上下文」和「支持 128 并发」单独看都没问题，同时要就是 128 倍。

**按最大上下文规划容量。** 实际请求长度分布通常很偏——大量短请求加少量长请求。按最大值配容量会大幅浪费，这正是分页要解决的问题。

**忽略 `gpu_memory_utilization`。** 默认 0.9 意味着 10% 显存引擎根本不用，手算不减掉就会一直对不上。

**以为 KV cache 量化没代价。** 它比权重量化温和，但不是没影响。长上下文召回是最容易掉的一项，要单独测。

## 关联
- [[02-KV cache 为什么存在]]
- [[04-PagedAttention 与分页显存]]
- [[01-GPU 容量规划]]
- [[06-怎么给任务选卡]]
- [[09-量化]]

## 参考
- [Efficient Memory Management for LLM Serving with PagedAttention](https://arxiv.org/abs/2309.06180) — vLLM 论文，KV cache 浪费的量化分析在第 2、3 节
- [vLLM 文档](https://docs.vllm.ai/) — `gpu_memory_utilization`、`max_model_len`、`max_num_seqs` 的确切语义
- [Qwen3-8B config.json](https://huggingface.co/Qwen/Qwen3-8B/blob/main/config.json) — 本篇手算用到的那四个数
