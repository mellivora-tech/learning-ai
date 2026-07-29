#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 0 里程碑的起步脚本：手写 attention、加 KV cache、用 logprobs 做置信度过滤。

怎么用
------
    pip install torch
    python "_练习/00-极简 attention 与 KV cache.py"

现在跑会失败，因为三个函数还是空的。挨个填，填对一个过一个。
每关都有 PyTorch 自带实现或者朴素实现当参照，不用自己判断对错。

    第 1 关  causal attention        —— 和 F.scaled_dot_product_attention 对齐
    第 2 关  KV cache                —— 和不带 cache 的全量重算逐 token 对齐
    第 3 关  logprobs 置信度过滤器     —— 低置信度的输出要能被拦下来

对应笔记
--------
    01-基础原理/01-Transformer 与 attention
    01-基础原理/02-KV cache 为什么存在
    01-基础原理/05-logprobs 与置信度
    01-基础原理/90-里程碑：极简 attention + KV cache + logprobs 置信度过滤器
"""

import math
import torch
import torch.nn.functional as F

torch.manual_seed(0)


# ══════════════════════════════════════════════════════════════
# 第 1 关：手写 causal attention
# ══════════════════════════════════════════════════════════════

def my_attention(q, k, v):
    """单头 causal attention。

    输入形状都是 [B, H, T, Dh]，输出同形状。

    要做四步：
      1. 打分：q 和 k 的最后两维做矩阵乘，得到 [B, H, T, T]
      2. 缩放：除以 sqrt(Dh)。想想为什么是这个数——见笔记「为什么要除 √d_k」
      3. 遮罩：位置 i 只能看 <= i，把上三角填成 -inf
              提示 torch.triu(torch.ones(T, T), diagonal=1).bool()
      4. 归一并加权：最后一维 softmax，再和 v 相乘

    容易错的两处：
      - 除的是 Dh（每个头的维度），不是 D（hidden_size）
      - mask 的方向：要挡住的是「未来」，也就是上三角
    """
    raise NotImplementedError("第 1 关：把这四步写出来")


def check_1():
    q, k, v = (torch.randn(2, 4, 64, 32) for _ in range(3))
    ref = F.scaled_dot_product_attention(q, k, v, is_causal=True)
    mine = my_attention(q, k, v)
    err = (ref - mine).abs().max().item()
    assert torch.allclose(ref, mine, atol=1e-5), "最大误差 %.2e，对不上" % err
    return "最大误差 %.2e" % err


# ══════════════════════════════════════════════════════════════
# 第 2 关：加上 KV cache
# ══════════════════════════════════════════════════════════════

class ToyLayer:
    """一个极简的注意力层，权重固定，只为验证 cache 逻辑是否等价。"""

    def __init__(self, d=32, h=4):
        self.d, self.h, self.dh = d, h, d // h
        self.wq, self.wk, self.wv = (torch.randn(d, d) / math.sqrt(d) for _ in range(3))

    def _split(self, x):                      # [B,T,D] -> [B,H,T,Dh]
        B, T, _ = x.shape
        return x.view(B, T, self.h, self.dh).transpose(1, 2)

    def forward_full(self, x):
        """不带 cache：每次把整段序列从头算一遍。这是参照答案。"""
        q, k, v = self._split(x @ self.wq), self._split(x @ self.wk), self._split(x @ self.wv)
        o = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        B, H, T, Dh = o.shape
        return o.transpose(1, 2).reshape(B, T, H * Dh)

    def forward_cached(self, x_new, cache):
        """带 cache：x_new 只有 1 个 token，形状 [B, 1, D]。

        cache 是 {"k": 张量或 None, "v": 张量或 None}，形状 [B, H, S, Dh]。

        要做三步：
          1. 只为 x_new 算 q、k、v（注意：只算这一个 token，不碰历史）
          2. 把新的 k、v 沿着序列维（dim=2）拼到 cache 后面，写回 cache
          3. 用「新的 q」对「拼接后的全部 k、v」做 attention

        第 3 步不需要 causal mask——想清楚为什么。
        （提示：新 token 在序列末尾，它本来就该看见前面所有的。）

        返回 [B, 1, D]。
        """
        raise NotImplementedError("第 2 关：把这三步写出来")


def check_2():
    layer, B, T, D = ToyLayer(), 2, 24, 32
    x = torch.randn(B, T, D)

    full = layer.forward_full(x)                       # 参照：一次性全量算

    cache = {"k": None, "v": None}                     # 逐 token 喂进去
    steps = [layer.forward_cached(x[:, t:t + 1, :], cache) for t in range(T)]
    cached = torch.cat(steps, dim=1)

    err = (full - cached).abs().max().item()
    assert torch.allclose(full, cached, atol=1e-5), "最大误差 %.2e，cache 版和全量版对不上" % err
    assert cache["k"].shape == (B, layer.h, T, layer.dh), "cache 形状不对：%s" % (cache["k"].shape,)
    return "逐 token 全部对齐，最大误差 %.2e；cache 形状 %s" % (err, tuple(cache["k"].shape))


# ══════════════════════════════════════════════════════════════
# 第 3 关：用 logprobs 做置信度过滤
# ══════════════════════════════════════════════════════════════

def confidence(logits):
    """从一串 logits 算出这次生成的置信度，返回 0~1 之间的一个数。

    logits 形状 [T, V]：T 个生成步，每步 V 个词的分数。

    一个够用的做法：
      1. 每一步做 log_softmax，取被选中那个 token 的 logprob
         （这里就用 argmax 当作被选中的）
      2. 把 T 步的 logprob 求平均
      3. exp 回到概率空间

    也就是所谓的「平均 token 概率」。
    想想它和「整句话的联合概率」有什么区别，以及为什么长句子不该用后者。
    """
    raise NotImplementedError("第 3 关：把这三步写出来")


def check_3():
    V, T = 100, 8

    sure = torch.full((T, V), -10.0)                   # 每步都有一个压倒性的赢家
    sure[:, 7] = 10.0
    unsure = torch.zeros(T, V)                         # 每步都是均匀分布

    c_sure, c_unsure = confidence(sure), confidence(unsure)
    assert 0.0 <= c_unsure <= c_sure <= 1.0, "置信度要落在 [0,1] 且笃定的那个更高"
    assert c_sure > 0.9, "压倒性赢家时置信度应该接近 1，实际 %.3f" % c_sure
    assert c_unsure < 0.1, "均匀分布时置信度应该接近 1/V，实际 %.3f" % c_unsure

    threshold = 0.5                                    # 拿它当过滤器用
    assert confidence(sure) >= threshold and confidence(unsure) < threshold
    return "笃定 %.3f / 犹豫 %.3f，阈值 %.1f 能把两者分开" % (c_sure, c_unsure, threshold)


# ══════════════════════════════════════════════════════════════

def main():
    checks = [("causal attention", check_1),
              ("KV cache", check_2),
              ("logprobs 置信度", check_3)]
    passed = 0
    for i, (name, fn) in enumerate(checks, 1):
        try:
            detail = fn()
            print("  ✓ 第 %d 关  %-16s %s" % (i, name, detail))
            passed += 1
        except NotImplementedError as e:
            print("  ○ 第 %d 关  %-16s %s" % (i, name, e))
            break
        except AssertionError as e:
            print("  ✗ 第 %d 关  %-16s %s" % (i, name, e))
            print("      —— 逐步打印中间张量的形状，多半错在 mask 方向或维度上")
            break
    print("\n%d / %d 关" % (passed, len(checks)))
    if passed == len(checks):
        print("三关都过了。回到里程碑笔记，把「结果与数据」填上：\n"
              "  · 带 cache 与不带 cache 生成 512 token 的耗时比\n"
              "  · 去掉 √d_k 之后 softmax 权重的熵怎么塌\n"
              "  · 置信度阈值定在多少，能拦下多少低质量输出")


if __name__ == "__main__":
    main()
