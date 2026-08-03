#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 0.6 里程碑的起步脚本：从卡的规格和模型的 config 推出它能跑什么。

怎么用
------
    python "_练习/03-从一张卡的规格推出它能跑什么.py"

不需要装任何东西，也不需要有卡——这一关全是算术。
现在跑会失败，因为五个函数还是空的。挨个填，填对一个过一个。

每关的裁判都是构造好的极端输入或者能手算验证的常识，不是「和某个参照实现比」：

    第 1 关  权重占多少显存        —— 换精度时体积必须严格成比例
    第 2 关  每 token 的 KV 大小   —— GQA 与 MHA 必须差出 头数比 那么多倍
    第 3 关  并发上限              —— 显存翻倍、上下文翻倍时的单调性
    第 4 关  decode 速度上限       —— 带宽决定，与算力无关
    第 5 关  瓶颈判断              —— prefill 与 decode 落在拐点两侧

五关都过之后，脚本会把 Qwen3-8B 在 H100 上的整页推算打出来，
拿它去和 vllm 实测对照，填进里程碑笔记的「结果与数据」。

对应笔记
--------
    03-读懂一张显卡/01-一张卡的四个关键数字
    03-读懂一张显卡/02-算力经常用不满：两种瓶颈
    03-读懂一张显卡/06-怎么给任务选卡
    03-读懂一张显卡/90-里程碑：从一张卡的规格推出它能跑什么
"""

# 单位一律按厂商标称的十进制口径：NVIDIA 的 3.35 TB/s 指 3.35e12 字节每秒。
# 换成 1024 进制会让拐点从 295 变成 269，和笔记里的数字对不上。
GB = 10 ** 9
TB = 10 ** 12


# ══════════════════════════════════════════════════════════════
# 规格：全部是稠密值。规格页上带 *with sparsity* 的数要先减半。
# ══════════════════════════════════════════════════════════════

H100 = {"名字": "H100 SXM", "显存GB": 80, "带宽TBs": 3.35, "BF16稠密TFLOPS": 989}
H200 = {"名字": "H200 SXM", "显存GB": 141, "带宽TBs": 4.8, "BF16稠密TFLOPS": 989}

# 抄自 https://huggingface.co/Qwen/Qwen3-8B/blob/main/config.json
QWEN3_8B = {"名字": "Qwen3-8B", "参数量": 8.2e9, "层数": 36,
            "KV头数": 8, "注意力头数": 32, "head_dim": 128}


# ══════════════════════════════════════════════════════════════
# 第 1 关：权重占多少显存
# ══════════════════════════════════════════════════════════════

def weight_bytes(params, bytes_per_param):
    """权重占多少字节。

    params 是参数量（个），bytes_per_param 是每个参数几字节
    （BF16=2，FP8=1，INT4=0.5）。

    就是一个乘法。放在这里是因为后面每一关都要用它，
    而且它是那个最容易被当成「显存需求全部」的数——
    真正的大头往往是下一关的 KV cache。
    """
    raise NotImplementedError("第 1 关：一行乘法")


def check_1():
    bf16 = weight_bytes(QWEN3_8B["参数量"], 2)
    fp8 = weight_bytes(QWEN3_8B["参数量"], 1)
    int4 = weight_bytes(QWEN3_8B["参数量"], 0.5)

    assert abs(bf16 / GB - 16.4) < 0.5, "8.2B 的 BF16 权重应该约 16.4 GB，实际 %.1f" % (bf16 / GB)
    # 换精度必须严格成比例——这是「量化为什么能提速」的算术基础
    assert abs(bf16 - 2 * fp8) < 1, "BF16 必须正好是 FP8 的两倍"
    assert abs(fp8 - 2 * int4) < 1, "FP8 必须正好是 INT4 的两倍"
    return "BF16 %.1f GB / FP8 %.1f GB / INT4 %.1f GB" % (bf16 / GB, fp8 / GB, int4 / GB)


# ══════════════════════════════════════════════════════════════
# 第 2 关：每个 token 的 KV cache 有多大
# ══════════════════════════════════════════════════════════════

def kv_bytes_per_token(cfg, bytes_per_elem=2):
    """一个 token 在 KV cache 里占多少字节。

    cfg 是上面那种模型字典。公式：

        2 × 层数 × KV头数 × head_dim × 每元素字节数

    最前面的 2 是 K 和 V 各存一份。

    唯一的坑在第二项：用的是 **KV头数**（num_key_value_heads），
    不是注意力头数（num_attention_heads）。GQA 下这两个数差好几倍，
    用错会把显存需求高估到离谱——这是里程碑笔记里列的第一号常见错误。
    """
    raise NotImplementedError("第 2 关：把那个连乘写出来，注意用哪个头数")


def check_2():
    kv = kv_bytes_per_token(QWEN3_8B)
    assert abs(kv - 147456) < 1, "Qwen3-8B 每 token 应为 147456 字节（144 KB），实际 %d" % kv

    # 构造一个「只有头数不同」的对照：MHA 版本必须正好大 32/8 = 4 倍
    mha = dict(QWEN3_8B, KV头数=QWEN3_8B["注意力头数"])
    ratio = kv_bytes_per_token(mha) / kv
    assert abs(ratio - 4.0) < 1e-6, (
        "把 KV 头数从 8 换成 32，KV cache 应该正好涨 4 倍，实际 %.2f 倍。"
        "差 1 倍说明用错了头数" % ratio)

    # KV cache 量化到 FP8，体积必须减半
    assert abs(kv_bytes_per_token(QWEN3_8B, 1) * 2 - kv) < 1, "换成 1 字节应该正好减半"
    return "%d 字节/token（%.0f KB）；换成 MHA 会涨 %.0f 倍" % (kv, kv / 1024, ratio)


# ══════════════════════════════════════════════════════════════
# 第 3 关：并发上限
# ══════════════════════════════════════════════════════════════

def max_concurrency(gpu, cfg, ctx_len, bytes_per_param=2, reserve=0.15):
    """这张卡上，这个模型开到 ctx_len 上下文时，最多能并发几个请求。

    三笔账：
      1. 卡的总显存        gpu["显存GB"] × GB
      2. 减去权重          weight_bytes(...)
      3. 再减去 reserve 比例的余量（激活值、碎片、CUDA context、引擎开销）
      4. 剩下的除以「一个满长度请求的 KV cache」= kv_bytes_per_token × ctx_len

    返回整数（向下取整）。装不下一个就返回 0。

    reserve 默认 0.15。真跑 vllm 时它对应 gpu_memory_utilization 的补数，
    默认 0.9 意味着引擎自己就先让出 10%——两个余量别重复扣。
    """
    raise NotImplementedError("第 3 关：三笔账减完再做除法")


def check_3():
    c8k = max_concurrency(H100, QWEN3_8B, 8192)
    assert c8k > 0, "H100 上 8k 上下文总该并发得了几个"

    # 上下文翻倍，并发必须减半（单调且成反比）
    c16k = max_concurrency(H100, QWEN3_8B, 16384)
    assert abs(c8k / 2 - c16k) <= 1, "上下文翻倍，并发应该减半：8k=%d 16k=%d" % (c8k, c16k)

    # 换显存更大的卡，并发必须变多
    assert max_concurrency(H200, QWEN3_8B, 8192) > c8k, "H200 显存更大，并发该更多"

    # 量化权重腾出空间，并发必须变多
    assert max_concurrency(H100, QWEN3_8B, 8192, bytes_per_param=1) > c8k, \
        "权重量化到 FP8 腾出约 7.6 GB，并发该变多"

    # 极端输入：上下文长到一个请求都装不下
    assert max_concurrency(H100, QWEN3_8B, 100_000_000) == 0, "装不下时应该返回 0"
    return "8k 上下文并发 %d，16k 并发 %d，FP8 权重后 8k 并发 %d" % (
        c8k, c16k, max_concurrency(H100, QWEN3_8B, 8192, bytes_per_param=1))


# ══════════════════════════════════════════════════════════════
# 第 4 关：decode 速度上限
# ══════════════════════════════════════════════════════════════

def decode_tokens_per_s(gpu, cfg, bytes_per_param=2):
    """单请求（batch=1）时，每秒最多吐几个 token。

        显存带宽 ÷ 每个 token 要搬的字节

    batch=1 时分母约等于「把全部权重读一遍」，KV cache 的那部分可以先忽略
    （长上下文时它会变成不可忽略的一项，那是这个估算偏乐观的原因之一）。

    注意 gpu["带宽TBs"] 的单位是 TB/s，要先乘 TB 换成字节每秒。

    这个函数里 **不应该出现算力**。如果你觉得需要它，回去看
    「算力经常用不满：两种瓶颈」——decode 是 memory-bound 的。
    """
    raise NotImplementedError("第 4 关：一个除法，且用不到算力")


def check_4():
    v = decode_tokens_per_s(H100, QWEN3_8B)
    assert abs(v - 204) < 15, "H100 上 Qwen3-8B BF16 应约 204 token/s，实际 %.0f" % v

    # 量化到 FP8：要搬的字节减半，速度必须翻倍
    assert abs(decode_tokens_per_s(H100, QWEN3_8B, 1) / v - 2) < 0.01, \
        "权重减半，decode 速度该翻倍——这就是量化提速的全部原理"

    # H200 与 H100 算力完全相同，只有带宽不同：加速比必须等于带宽比
    ratio = decode_tokens_per_s(H200, QWEN3_8B) / v
    assert abs(ratio - H200["带宽TBs"] / H100["带宽TBs"]) < 1e-6, (
        "H200 相对 H100 的 decode 加速比必须正好等于带宽比 %.2f，实际 %.2f。"
        "对不上说明算力混进公式里了" % (H200["带宽TBs"] / H100["带宽TBs"], ratio))
    return "H100 %.0f token/s，FP8 后 %.0f，H200 上 %.0f" % (
        v, decode_tokens_per_s(H100, QWEN3_8B, 1), decode_tokens_per_s(H200, QWEN3_8B))


# ══════════════════════════════════════════════════════════════
# 第 5 关：瓶颈落在拐点哪一侧
# ══════════════════════════════════════════════════════════════

def ridge_point(gpu):
    """这张卡的拐点，单位 FLOP/byte：稠密算力 ÷ 显存带宽。

    算术强度高于它 → compute-bound，低于它 → memory-bound。

    两个单位都要换算：TFLOPS 是 1e12 FLOP/s，TB/s 是 1e12 字节/s。

    算出 590 说明用了规格页上含稀疏的 1979 —— 稠密只有一半。
    """
    raise NotImplementedError("第 5 关之一：算力 ÷ 带宽")


def bottleneck(gpu, arithmetic_intensity):
    """给定算术强度，返回 "compute" 或 "memory"。

    高于拐点是 compute，低于是 memory。等于时算哪边都行，返回 "memory" 即可。
    """
    raise NotImplementedError("第 5 关之二：和拐点比一下")


def check_5():
    r = ridge_point(H100)
    assert 280 < r < 310, (
        "H100 拐点应在 295 上下（989 TFLOPS ÷ 3.35 TB/s），实际 %.0f。"
        "算出约 590 说明用了规格页上含稀疏的 1979；算出约 269 说明按 1024 进制换算了带宽" % r)

    # decode 单请求的算术强度约等于 1，必然 memory-bound
    assert bottleneck(H100, 1) == "memory", "batch=1 的 decode 必须是 memory-bound"
    # prefill 吃 2048 token 输入，算术强度约等于序列长度
    assert bottleneck(H100, 2048) == "compute", "prefill 2048 token 必须是 compute-bound"
    # 拐点两侧各一步
    assert bottleneck(H100, r - 1) == "memory" and bottleneck(H100, r + 1) == "compute"
    return "H100 拐点 %.0f FLOP/byte；decode(≈1) 落在 memory，prefill(2048) 落在 compute" % r


# ══════════════════════════════════════════════════════════════

def report():
    """五关都过之后，打印整页推算。拿去和实测对照。"""
    gpu, cfg = H100, QWEN3_8B
    print("\n" + "═" * 62)
    print("推算：%s 上跑 %s（BF16）" % (gpu["名字"], cfg["名字"]))
    print("═" * 62)
    w = weight_bytes(cfg["参数量"], 2)
    kv = kv_bytes_per_token(cfg)
    print("① 权重                    %.1f GB" % (w / GB))
    print("② 每 token KV             %.0f KB" % (kv / 1024))
    print("③ 可用于 KV cache         %.1f GB" % ((gpu["显存GB"] * GB * 0.85 - w) / GB))
    for ctx in (8192, 32768):
        print("④ 并发上限（%2dk 上下文）   %d" % (ctx // 1024, max_concurrency(gpu, cfg, ctx)))
    print("⑤ decode 上限（batch=1）  %.0f token/s" % decode_tokens_per_s(gpu, cfg))
    print("⑥ 拐点                    %.0f FLOP/byte" % ridge_point(gpu))
    print("   prefill(2048) → %s ；decode(batch=1) → %s"
          % (bottleneck(gpu, 2048), bottleneck(gpu, 1)))
    print("═" * 62)
    print("""
接下来去压测，把差距解释掉——这一步才是里程碑的价值所在：

    vllm serve Qwen/Qwen3-8B --max-model-len 8192 --gpu-memory-utilization 0.9
    curl -s localhost:8000/metrics | grep -E 'gpu_cache_usage_perc|num_requests_running'

实测低于推算是正常的。按出现频率排，先查这四条：
  1. KV 头数是不是用成了 num_attention_heads（GQA 下差 4 倍）
  2. gpu_memory_utilization 默认 0.9，和脚本里的 reserve 重复扣了没有
  3. 权重之外的激活值与 CUDA context
  4. 引擎有没有悄悄开 KV cache 量化，实际 dtype 不是你以为的那个

把推算值、实测值、达成率和差距解释填进里程碑笔记的「结果与数据」。""")


def main():
    checks = [("权重显存", check_1), ("每 token KV", check_2), ("并发上限", check_3),
              ("decode 上限", check_4), ("瓶颈判断", check_5)]
    passed = 0
    for i, (name, fn) in enumerate(checks, 1):
        try:
            print("  ✓ 第 %d 关  %-12s %s" % (i, name, fn()))
            passed += 1
        except NotImplementedError as e:
            print("  ○ 第 %d 关  %-12s %s" % (i, name, e))
            break
        except AssertionError as e:
            print("  ✗ 第 %d 关  %-12s %s" % (i, name, e))
            break
    print("\n%d / %d 关" % (passed, len(checks)))
    if passed == len(checks):
        report()


if __name__ == "__main__":
    main()
