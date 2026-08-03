#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 1 里程碑的起步脚本：把 eval 做成 CI 里真会拦人的门禁。

怎么用
------
    python "_练习/04-CI 里的 eval 门禁.py"

不需要装任何东西，也不需要调模型——这一关练的是**门禁的判定逻辑**，
模型输出用固定的假数据喂进来。判定逻辑写错的代价比模型差更大：
一个永远不会红的门禁，比没有门禁更糟，因为它让人以为有人在看。

现在跑会失败，因为五个函数还是空的。挨个填，填对一个过一个。

    第 1 关  打分与聚合        —— 空集不能崩，也不能算成满分
    第 2 关  回归检测          —— 总分没掉但个别样本掉了，必须能抓出来
    第 3 关  judge 与人工的一致性 —— 全同意但都是同一个标签时，kappa 必须接近 0
    第 4 关  分层统计          —— 小分组不能被大分组的平均值淹掉
    第 5 关  门禁判定          —— 样本太少时必须拒绝放行，而不是默认通过

五关都过之后，脚本会拿一组「整体持平但某一层塌了」的数据跑一遍完整门禁，
它必须红。那正是这个里程碑要防住的东西。

对应笔记
--------
    04-评估/01-Golden set
    04-评估/02-回归测试与 CI 门禁
    04-评估/04-Judge 校准
    04-评估/90-里程碑：CI 里的 eval 门禁
"""


# ══════════════════════════════════════════════════════════════
# 假数据：每条是 golden set 里的一个样本
#   id / 分层标签 / 上一版是否通过 / 这一版是否通过
# ══════════════════════════════════════════════════════════════

BASELINE = [
    {"id": "q1", "层": "常见问法", "通过": True},
    {"id": "q2", "层": "常见问法", "通过": True},
    {"id": "q3", "层": "常见问法", "通过": True},
    {"id": "q4", "层": "常见问法", "通过": True},
    {"id": "q5", "层": "长尾", "通过": True},
    {"id": "q6", "层": "长尾", "通过": True},
    {"id": "q7", "层": "对抗", "通过": True},
    {"id": "q8", "层": "对抗", "通过": True},
]

# 这一版：总通过率只掉了一点，但「对抗」这一层全塌了
CANDIDATE = [
    {"id": "q1", "层": "常见问法", "通过": True},
    {"id": "q2", "层": "常见问法", "通过": True},
    {"id": "q3", "层": "常见问法", "通过": True},
    {"id": "q4", "层": "常见问法", "通过": True},
    {"id": "q5", "层": "长尾", "通过": True},
    {"id": "q6", "层": "长尾", "通过": True},
    {"id": "q7", "层": "对抗", "通过": False},
    {"id": "q8", "层": "对抗", "通过": False},
]


# ══════════════════════════════════════════════════════════════
# 第 1 关：打分与聚合
# ══════════════════════════════════════════════════════════════

def pass_rate(samples):
    """通过率：通过的条数 ÷ 总条数，返回 0~1 的浮点数。

    唯一要想清楚的是**空列表怎么办**。

    返回 1.0 是最危险的选择——「一条样本都没跑」会被读成「全过了」，
    而 CI 里最常见的故障恰恰是数据集加载失败导致跑了 0 条。
    这里约定：空集返回 0.0，让它显式地不及格。
    """
    raise NotImplementedError("第 1 关：一个除法，外加想清楚空集")


def check_1():
    assert pass_rate(BASELINE) == 1.0, "基线应该全过"
    assert abs(pass_rate(CANDIDATE) - 0.75) < 1e-9, "候选版 8 条过 6 条"
    assert pass_rate([]) == 0.0, (
        "空集必须返回 0.0 而不是 1.0——"
        "数据集加载失败时返回满分，门禁就永远不会红")
    assert pass_rate([{"通过": False}]) == 0.0
    return "基线 %.0f%%，候选 %.0f%%，空集 %.0f%%" % (
        pass_rate(BASELINE) * 100, pass_rate(CANDIDATE) * 100, pass_rate([]) * 100)


# ══════════════════════════════════════════════════════════════
# 第 2 关：逐样本回归检测
# ══════════════════════════════════════════════════════════════

def regressions(baseline, candidate):
    """找出「上一版过、这一版不过」的样本，返回它们的 id 列表（顺序不限）。

    为什么不能只看总分：两条样本一好一坏，总通过率纹丝不动，
    但你的系统在这两条上的行为都变了——其中一条现在是坏的。
    **总分是聚合量，它天然会掩盖同等数量的一好一坏。**

    按 id 对齐两份结果，不要按下标——两次跑的顺序未必一样。
    candidate 里没有的 id 当作没跑过，先忽略（第 5 关会专门管样本数）。
    """
    raise NotImplementedError("第 2 关：按 id 对齐，挑出 True → False 的")


def check_2():
    r = regressions(BASELINE, CANDIDATE)
    assert sorted(r) == ["q7", "q8"], "应该抓到 q7、q8，实际 %s" % sorted(r)

    # 关键用例：一好一坏，总通过率完全不变，但必须报出那条坏的
    base = [{"id": "a", "通过": True}, {"id": "b", "通过": False}]
    cand = [{"id": "a", "通过": False}, {"id": "b", "通过": True}]
    assert pass_rate(base) == pass_rate(cand), "构造前提：两版总分相同"
    assert sorted(regressions(base, cand)) == ["a"], (
        "总通过率一样，但 a 从过变成不过，必须被抓出来——"
        "这正是「只看总分」会漏掉的情况")

    # 顺序打乱不能影响结果
    assert sorted(regressions(BASELINE, list(reversed(CANDIDATE)))) == ["q7", "q8"], \
        "按 id 对齐，不能依赖顺序"
    assert regressions(BASELINE, BASELINE) == [], "没变化时应该是空列表"
    return "抓到 %s；总分不变的一好一坏也能抓到" % sorted(r)


# ══════════════════════════════════════════════════════════════
# 第 3 关：judge 和人工到底一致不一致
# ══════════════════════════════════════════════════════════════

def cohens_kappa(a, b):
    """两组二值标签的 Cohen's kappa，返回一个浮点数。

    a、b 是等长的 True/False 列表，分别是人工标注和 judge 的判定。

        p_o = 实际一致的比例
        p_e = 偶然一致的期望比例
            = P(两边都判 True) + P(两边都判 False)
            = (a中True率 × b中True率) + (a中False率 × b中False率)
        kappa = (p_o − p_e) / (1 − p_e)

    为什么不能直接用一致率 p_o：如果 95% 的样本都是「通过」，
    一个永远回答「通过」的 judge 也能拿到 95% 一致率，但它没有任何判别力。
    kappa 把这份「蒙也能蒙对」的部分扣掉了。

    分母为 0 的情况要处理：p_e == 1 意味着两边都是清一色同一个标签，
    此时「超出偶然的一致」无从谈起，返回 0.0。
    """
    raise NotImplementedError("第 3 关：先算 p_o 和 p_e，再套公式")


def check_3():
    assert abs(cohens_kappa([True, False, True, False],
                            [True, False, True, False]) - 1.0) < 1e-9, "完全一致应为 1"

    # 核心用例：judge 永远说「通过」，而人工里 90% 也是通过
    human = [True] * 9 + [False]
    lazy = [True] * 10
    naive_agreement = sum(h == j for h, j in zip(human, lazy)) / len(human)
    assert abs(naive_agreement - 0.9) < 1e-9, "构造前提：朴素一致率高达 90%"
    k = cohens_kappa(human, lazy)
    assert abs(k) < 0.05, (
        "一个永远说「通过」的 judge，朴素一致率 90%% 但 kappa 必须≈0，实际 %.3f。"
        "这就是不能用一致率验收 judge 的原因" % k)

    # 完全反着来，kappa 应该是负的
    assert cohens_kappa([True, False, True, False],
                        [False, True, False, True]) < 0, "系统性相反应为负值"
    # 清一色同一标签：分母为 0，按约定返回 0
    assert cohens_kappa([True] * 5, [True] * 5) == 0.0, "两边全 True 时应返回 0.0，不能除零崩掉"
    return "完全一致 1.00；懒 judge 朴素一致率 90%% 但 kappa %.2f" % k


# ══════════════════════════════════════════════════════════════
# 第 4 关：分层统计
# ══════════════════════════════════════════════════════════════

def by_stratum(samples):
    """按「层」分组算通过率，返回 {层名: 通过率}。

    分层是这个里程碑的核心。总通过率是各层的加权平均，
    **权重就是各层的样本数**——所以样本少的那一层，哪怕全塌了，
    对总分的影响也可能小到看不出来。而「对抗」这类层恰恰样本最少。
    """
    raise NotImplementedError("第 4 关：分组，每组各算一次通过率")


def check_4():
    s = by_stratum(CANDIDATE)
    assert set(s) == {"常见问法", "长尾", "对抗"}, "三层都要出现，实际 %s" % set(s)
    assert s["常见问法"] == 1.0 and s["长尾"] == 1.0
    assert s["对抗"] == 0.0, "对抗层应该是 0%%，实际 %.2f" % s["对抗"]

    # 说明「为什么必须分层」：某一层归零，总分只掉 25%
    assert pass_rate(CANDIDATE) == 0.75, "总分只掉到 75%，看起来像正常波动"
    return "常见问法 %.0f%% / 长尾 %.0f%% / 对抗 %.0f%%（总分却有 %.0f%%）" % (
        s["常见问法"] * 100, s["长尾"] * 100, s["对抗"] * 100, pass_rate(CANDIDATE) * 100)


# ══════════════════════════════════════════════════════════════
# 第 5 关：门禁判定
# ══════════════════════════════════════════════════════════════

def gate(baseline, candidate, min_samples=8, max_drop=0.05):
    """门禁总判定。返回 (是否放行, 原因列表)。

    四条独立的规则，**任何一条不满足就拦下**，且原因要全部收集齐
    （只报第一条会让人修一条跑一次，来回好几轮）：

      1. 样本数不足 min_samples          → "样本不足"
      2. 总通过率比基线掉超过 max_drop     → "总通过率下降"
      3. 有逐样本回归                     → "回归"
      4. 任何一层的通过率比基线掉超过 max_drop → "分层下降"

    第 1 条最容易被写反。「样本太少」时正确的行为是**拒绝放行**：
    数据集没加载出来和「测过了没问题」是两回事，而门禁分不清，
    所以只能按最坏的那种处理。

    原因字符串的具体措辞不限，包含上面括号里那几个关键词即可。
    """
    raise NotImplementedError("第 5 关：四条规则，逐条检查，原因收集齐")


def check_5():
    ok, why = gate(BASELINE, CANDIDATE)
    assert ok is False, "对抗层全塌了，必须拦下"
    joined = " ".join(why)
    assert "分层" in joined, "必须报出分层下降，实际原因：%s" % why
    assert "回归" in joined, "必须报出逐样本回归，实际原因：%s" % why

    # 没有变化时应当放行
    ok2, why2 = gate(BASELINE, BASELINE)
    assert ok2 is True, "基线和自己比应该放行，却报了 %s" % why2

    # 样本不足必须拦，而不是放行
    ok3, why3 = gate(BASELINE, CANDIDATE[:2])
    assert ok3 is False and "样本不足" in " ".join(why3), (
        "只跑了 2 条就该拦下并说明原因，实际 %s / %s" % (ok3, why3))

    # 一好一坏、总分不变，仍然要因为回归被拦
    base = [{"id": str(i), "层": "x", "通过": True} for i in range(8)]
    cand = [dict(s, 通过=(s["id"] != "0")) for s in base]
    cand[1]["通过"] = True
    ok4, why4 = gate(base, cand, max_drop=0.2)
    assert ok4 is False and "回归" in " ".join(why4), \
        "总分掉幅在容忍范围内，但有一条真回归，必须拦：%s / %s" % (ok4, why4)
    return "对抗层塌陷被拦（%s）；样本不足也被拦" % "、".join(why)


# ══════════════════════════════════════════════════════════════

def demo():
    print("\n" + "═" * 62)
    print("完整门禁跑一遍：总分持平，但某一层塌了")
    print("═" * 62)
    print("总通过率      基线 %.0f%%  →  候选 %.0f%%" % (
        pass_rate(BASELINE) * 100, pass_rate(CANDIDATE) * 100))
    b, c = by_stratum(BASELINE), by_stratum(CANDIDATE)
    for k in sorted(b):
        flag = "  ← 塌了" if c[k] < b[k] else ""
        print("  %-6s      %.0f%%  →  %.0f%%%s" % (k, b[k] * 100, c[k] * 100, flag))
    ok, why = gate(BASELINE, CANDIDATE)
    print("\n逐样本回归    %s" % (sorted(regressions(BASELINE, CANDIDATE)) or "无"))
    print("门禁判定      %s" % ("放行" if ok else "拦下"))
    for w in why:
        print("              · %s" % w)
    print("═" * 62)
    print("""
只看总通过率的话，75% 很容易被当成正常波动放过去。
分层之后「对抗」那一层从 100% 掉到 0%，才是真正发生的事。

接下来把它接进真的 CI，里程碑才算过：
  1. 把假数据换成你自己的 golden set，至少分「常见 / 长尾 / 对抗」三层
  2. 门禁挂到 pull request 上，让它真的能拦住合并
  3. 故意提一个会退化的改动，确认它变红——**没验证过会红的门禁不算数**
  4. 用 cohens_kappa 校准你的 judge，kappa 上不去就别用它当门禁

把 kappa 值、各层通过率、拦截演练的截图填进里程碑笔记的「结果与数据」。""")


def main():
    checks = [("打分聚合", check_1), ("回归检测", check_2), ("kappa", check_3),
              ("分层统计", check_4), ("门禁判定", check_5)]
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
