#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 5 里程碑的起步脚本：两段式检索评估的指标，加一个幽灵文档探针。

怎么用
------
    python "_练习/11-检索评估两段式.py"

不需要装任何东西，也不需要真的建索引——检索结果用固定的假数据喂进来。
练的是**指标本身**，因为这些指标算错的方式非常隐蔽：
recall 分母取错、nDCG 不归一化、把 precision 当成 recall，
算出来都是个像模像样的小数，你看不出它是错的。

现在跑会失败，因为六个函数还是空的。挨个填，填对一个过一个。

    第 1 关  recall@k        —— 分母是相关文档总数，不是 k
    第 2 关  nDCG@k          —— 顺序变了它必须变，而 recall 不变
    第 3 关  RRF 融合        —— 只用排名不用分数，两路都靠前的必须升上来
    第 4 关  诊断表          —— 从三个指标定位该修哪一段
    第 5 关  citation 指标   —— precision 与 recall 分开，两者会反向动
    第 6 关  幽灵文档探针     —— 删掉的文档还能被搜到就必须报警

六关都过之后，脚本会跑一遍完整的两段式面板与一次幽灵文档巡检。

对应笔记
--------
    11-检索增强/06-幽灵文档测试
    04-评估/06-检索评估两段式
    11-检索增强/03-Hybrid search（dense + BM25 + RRF）
    11-检索增强/90-里程碑：recall@k 与 groundedness 面板 + 幽灵文档自动化测试
"""

import math


# ══════════════════════════════════════════════════════════════
# 第 1 关：recall@k
# ══════════════════════════════════════════════════════════════

def recall_at_k(retrieved, relevant, k):
    """前 k 个检索结果里，命中了多少比例的**相关文档**。

    retrieved 是排好序的文档 id 列表，relevant 是相关文档 id 的集合。

        recall@k = |前 k 个 ∩ relevant| / |relevant|

    **分母是相关文档的总数，不是 k。** 这是这个指标最常见的错误：
    用 k 当分母算出来的是 precision@k，两者在 |relevant| == k 时恰好相等，
    所以拿一个刚好凑巧的用例测是测不出来的。

    relevant 为空时返回 0.0（没有正确答案，谈不上召回）。
    """
    raise NotImplementedError("第 1 关：交集大小 ÷ 相关文档总数")


def check_1():
    # 3 个相关文档，前 10 个里命中 2 个 → 2/3
    r = recall_at_k(["a", "x", "b", "y", "z"], {"a", "b", "c"}, 10)
    assert abs(r - 2 / 3) < 1e-9, "应为 2/3，实际 %.3f。用 k 当分母会得到 0.2" % r

    # 关键用例：分母取错时才会露馅——相关文档数与 k 不相等
    r2 = recall_at_k(["a"], {"a", "b", "c", "d"}, 1)
    assert abs(r2 - 0.25) < 1e-9, (
        "1 个相关文档命中、共 4 个相关 → 0.25，实际 %.3f。"
        "得到 1.0 说明分母用了 k" % r2)

    # k 截断必须生效
    assert recall_at_k(["x", "y", "a"], {"a"}, 2) == 0.0, "a 在第 3 位，recall@2 应为 0"
    assert recall_at_k(["x", "y", "a"], {"a"}, 3) == 1.0
    assert recall_at_k(["a"], set(), 5) == 0.0, "没有相关文档时返回 0.0，不能除零"
    return "recall@10=%.3f，分母取错的用例也过了" % r


# ══════════════════════════════════════════════════════════════
# 第 2 关：nDCG@k
# ══════════════════════════════════════════════════════════════

def ndcg_at_k(retrieved, relevant, k):
    """归一化折损累积增益，返回 0~1。

        DCG@k  = Σ  rel_i / log2(i + 1)        i 从 1 开始
        IDCG@k = 理想排序下的 DCG（相关文档全排在最前面）
        nDCG@k = DCG / IDCG

    rel_i 是二值的：第 i 个结果在 relevant 里就是 1，否则 0。

    **为什么需要它**：recall 只关心「有没有召回到」，
    把相关文档排在第 1 位还是第 10 位，recall@10 完全一样。
    重排改变的正是顺序而不是集合，所以**衡量重排收益只能用 nDCG**。

    IDCG 为 0 时（没有相关文档）返回 0.0。
    """
    raise NotImplementedError("第 2 关：先算 DCG，再算理想排序的 IDCG，相除")


def check_2():
    perfect = ndcg_at_k(["a", "b", "x", "y"], {"a", "b"}, 4)
    assert abs(perfect - 1.0) < 1e-9, "相关文档已在最前，nDCG 应为 1，实际 %.3f" % perfect

    # 核心用例：同一批文档、不同顺序 —— recall 一样，nDCG 必须不一样
    good, bad = ["a", "b", "x", "y"], ["x", "y", "a", "b"]
    rel = {"a", "b"}
    assert recall_at_k(good, rel, 4) == recall_at_k(bad, rel, 4) == 1.0, "构造前提：两种排序 recall 都是 1"
    n_good, n_bad = ndcg_at_k(good, rel, 4), ndcg_at_k(bad, rel, 4)
    assert n_good > n_bad, (
        "recall 相同但排序不同时，nDCG 必须能区分：好序 %.3f vs 差序 %.3f。"
        "两者相等说明没有用上位置折损" % (n_good, n_bad))
    assert 0 < n_bad < 1, "差序应严格落在 (0,1)，实际 %.3f" % n_bad
    assert ndcg_at_k(["x"], set(), 3) == 0.0, "没有相关文档时返回 0.0"
    return "理想排序 1.000，同集合差排序 %.3f —— 顺序变化被捕捉到了" % n_bad


# ══════════════════════════════════════════════════════════════
# 第 3 关：RRF 融合
# ══════════════════════════════════════════════════════════════

def rrf(rankings, k=60):
    """把多路检索结果按 Reciprocal Rank Fusion 融合成一个排序。

    rankings 是若干个「文档 id 列表」，每个列表已按各自的相关度排好序。

        score(d) = Σ  1 / (k + rank_d_in_that_list)      rank 从 1 开始
                  各路

    某路没有召回到 d，那一路就不贡献分数。
    返回按总分降序排列的文档 id 列表；同分时用 id 排序保证结果稳定。

    **RRF 只用排名不用分数**，这是它的全部要点：
    余弦相似度和 BM25 得分量纲完全不可比，任何加权求和都要先解决归一化，
    而排名天然可比。k=60 是原论文的经验值。
    """
    raise NotImplementedError("第 3 关：按 1/(k+rank) 累加，再降序排")


def check_3():
    dense = ["a", "b", "c"]      # b 在这一路排第 2
    bm25 = ["d", "b", "e"]       # b 在这一路也排第 2
    out = rrf([dense, bm25])

    # a 和 d 各自在一路排第 1，b 两路都只排第 2 —— 但 b 应该胜出
    assert out[0] == "b", (
        "b 在两路都排第 2，a 与 d 各自只在一路排第 1，融合后应该是 b 第一；"
        "实际第一是 %s。这正是 RRF 的意义：两路都认可 > 一路极端认可" % out[0])
    assert set(out) == {"a", "b", "c", "d", "e"}, "所有召回到的文档都要出现"

    # 同分时按 id 排序，结果必须稳定可复现
    assert out[1:3] == ["a", "d"], "a 与 d 同分，应按 id 排序，实际 %s" % out[1:3]

    # 只有一路时，顺序必须原样保留
    assert rrf([dense]) == dense, "单路融合应保持原序"

    # 只召回到一个文档的路也要参与
    assert rrf([["z"], ["z"]]) == ["z"]
    return "融合结果 %s —— 两路都排第 2 的 b 压过了两个「单路第一」" % out


# ══════════════════════════════════════════════════════════════
# 第 4 关：诊断表
# ══════════════════════════════════════════════════════════════

def diagnose(recall10, recall50, groundedness):
    """从三个指标判断该修哪一段，返回一个短字符串。

    判定顺序很重要，因为**下游指标在上游坏掉时没有意义**：

      1. recall@50 低（< 0.6）        → "检索召回"
         材料根本没捞出来，重排和 prompt 都救不了
      2. recall@50 高但 recall@10 低（< 0.6） → "重排"
         捞出来了但排得靠后，加 cross-encoder
      3. 检索都好，但 groundedness 低（< 0.8） → "生成"
         材料给对了模型却不照着说，改 prompt 与引用约束
      4. 都好                          → "都正常"

    **顺序不能反**：recall@50 只有 0.2 时 groundedness 再低也不该去改 prompt，
    因为材料里压根没有答案。
    """
    raise NotImplementedError("第 4 关：按上面的顺序逐条判断")


def check_4():
    assert diagnose(0.2, 0.3, 0.9) == "检索召回"
    assert diagnose(0.4, 0.9, 0.9) == "重排", "召回得到但排得靠后 → 重排"
    assert diagnose(0.9, 0.95, 0.5) == "生成"
    assert diagnose(0.9, 0.95, 0.9) == "都正常"
    # 关键：检索烂 + 生成也烂时，必须先报检索
    assert diagnose(0.1, 0.2, 0.1) == "检索召回", (
        "两段都差时必须先报检索——材料没捞出来的情况下，"
        "改 prompt 是白费力气")
    return "四种情形判定正确，且两段都差时优先报检索"


# ══════════════════════════════════════════════════════════════
# 第 5 关：citation precision 与 recall
# ══════════════════════════════════════════════════════════════

def citation_scores(cited, supporting):
    """返回 (precision, recall)。

    cited      —— 模型实际引用的文档 id 集合
    supporting —— 真正支撑了答案的文档 id 集合

        precision = |cited ∩ supporting| / |cited|        引的准不准
        recall    = |cited ∩ supporting| / |supporting|   该引的引全了没有

    **必须分开报，因为它们会反向动**：模型把所有检索到的文档都列进引用，
    recall 能到 1.0 而 precision 很低——看起来「引用很完整」，
    实际上等于没引，读者仍然不知道哪句话来自哪里。

    分母为 0 时那一项返回 0.0。
    """
    raise NotImplementedError("第 5 关：两个除法，注意分母各是谁")


def check_5():
    p, r = citation_scores({"a", "b"}, {"a", "b"})
    assert (p, r) == (1.0, 1.0)

    # 核心用例：全都引上 —— recall 满分，precision 塌掉
    p2, r2 = citation_scores({"a", "b", "c", "d", "e"}, {"a"})
    assert abs(r2 - 1.0) < 1e-9, "该引的都引了，recall 应为 1"
    assert p2 < 0.3, (
        "把检索到的全列上时 precision 必须很低，实际 %.2f。"
        "两个数相等说明分母用错了" % p2)

    # 反过来：只引一个但引对了 —— precision 满分，recall 塌掉
    p3, r3 = citation_scores({"a"}, {"a", "b", "c"})
    assert abs(p3 - 1.0) < 1e-9 and abs(r3 - 1 / 3) < 1e-9

    assert citation_scores(set(), {"a"}) == (0.0, 0.0), "没引用时两项都是 0"
    return "全引上 precision %.2f / recall %.2f；只引一条 %.2f / %.2f" % (p2, r2, p3, r3)


# ══════════════════════════════════════════════════════════════
# 第 6 关：幽灵文档探针
# ══════════════════════════════════════════════════════════════

def ghost_probe(deleted_ids, search_fn, probes):
    """删除传播的巡检。返回仍然能被搜到的文档 id 列表（顺序不限）。

    deleted_ids —— 已经执行过删除的文档 id 集合
    search_fn   —— 一个函数，给它一个查询字符串，返回文档 id 列表
    probes      —— 探针查询列表，每条都应该能命中某个已删文档（如果它还在的话）

    做法：对每条探针跑一次 search_fn，看返回结果里有没有 deleted_ids 里的东西。
    有就是幽灵，收集起来。

    **这个测试测的是「不该发生的事」**，所以它的正常输出是空列表。
    正因为如此，它必须自己会报警——没有任何自然信号会提醒你删除没生效。
    """
    raise NotImplementedError("第 6 关：逐条跑探针，挑出仍能被搜到的已删文档")


def check_6():
    # 一个假索引：doc3 明明删了却还在
    index = {"退款政策": ["doc1", "doc3"], "配送时效": ["doc2"], "旧价目表": ["doc3"]}
    search = lambda q: index.get(q, [])

    ghosts = ghost_probe({"doc3"}, search, ["退款政策", "配送时效", "旧价目表"])
    assert sorted(set(ghosts)) == ["doc3"], "应该抓到 doc3，实际 %s" % ghosts

    # 删干净了就该是空
    clean = {"退款政策": ["doc1"], "配送时效": ["doc2"], "旧价目表": []}
    assert ghost_probe({"doc3"}, lambda q: clean.get(q, []),
                       ["退款政策", "配送时效", "旧价目表"]) == [], "删干净时应返回空列表"

    # 没删过任何东西时，探针不该误报
    assert ghost_probe(set(), search, ["退款政策"]) == [], "没有已删文档时不该报警"
    return "抓到幽灵 %s；删干净的情形不误报" % sorted(set(ghosts))


# ══════════════════════════════════════════════════════════════

def demo():
    print("\n" + "═" * 64)
    print("两段式面板：三种配置的对照")
    print("═" * 64)
    rel = {"d1", "d2", "d3"}
    configs = {
        "基线（纯向量）": ["x", "d1", "y", "z", "d2", "w", "v", "u", "t", "s", "d3"],
        "⊕ BM25 融合": rrf([["x", "d1", "y", "z", "d2"], ["d2", "d3", "x", "d1", "q"]]),
        "⊕ 重排": ["d1", "d2", "d3", "x", "y"],
    }
    print("%-16s %10s %10s %10s" % ("配置", "recall@10", "recall@50", "nDCG@10"))
    for name, docs in configs.items():
        print("%-16s %10.3f %10.3f %10.3f" % (
            name, recall_at_k(docs, rel, 10), recall_at_k(docs, rel, 50), ndcg_at_k(docs, rel, 10)))

    print("\n注意最后一行：recall@50 从基线起就没变过，nDCG 却明显涨了。")
    print("**这正是重排的作用——它不改变召回集合，只改变顺序。**")
    print("所以用 recall 去衡量重排，会得出「毫无收益」的错误结论。")

    print("\n" + "─" * 64)
    print("诊断表")
    for r10, r50, g in [(0.2, 0.3, 0.9), (0.4, 0.9, 0.9), (0.9, 0.95, 0.5), (0.9, 0.95, 0.9)]:
        print("  recall@10=%.2f recall@50=%.2f groundedness=%.2f  →  %s"
              % (r10, r50, g, diagnose(r10, r50, g)))

    print("\n" + "─" * 64)
    index = {"退款政策": ["doc1", "doc3"], "配送时效": ["doc2"]}
    ghosts = ghost_probe({"doc3"}, lambda q: index.get(q, []), list(index))
    print("幽灵文档巡检：%s" % ("发现幽灵 " + str(ghosts) + " —— 应当告警到人" if ghosts else "干净"))
    print("═" * 64)
    print("""
接下来换成你自己的数据，里程碑才算过：

  1. 攒 50 条真实查询并标注相关文档，替换掉上面的假数据
  2. 从基线开始，每加一样东西（BM25 融合、重排）记一次增量
  3. 构造 20 条「材料里没有答案」的查询，测拒答率
  4. 把幽灵文档探针接进 CI，并在线上定时巡检、失败告警到人
  5. 记录索引延迟：文档进系统到能被搜到要多久

把三种配置的 recall / nDCG / 延迟填进里程碑笔记的「结果与数据」。""")


def main():
    checks = [("recall@k", check_1), ("nDCG@k", check_2), ("RRF 融合", check_3),
              ("诊断表", check_4), ("citation", check_5), ("幽灵探针", check_6)]
    passed = 0
    for i, (name, fn) in enumerate(checks, 1):
        try:
            print("  ✓ 第 %d 关  %-10s %s" % (i, name, fn()))
            passed += 1
        except NotImplementedError as e:
            print("  ○ 第 %d 关  %-10s %s" % (i, name, e))
            break
        except AssertionError as e:
            print("  ✗ 第 %d 关  %-10s %s" % (i, name, e))
            break
    print("\n%d / %d 关" % (passed, len(checks)))
    if passed == len(checks):
        demo()


if __name__ == "__main__":
    main()
