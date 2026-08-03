#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 4 里程碑的起步脚本：硬预算、终止条件、升级载荷。

怎么用
------
    python "_练习/10-跑 100 次不失控的 agent.py"

不需要装任何东西，也不需要调模型——agent 的每一步用固定的假轨迹喂进来。
练的是**刹车**，因为刹车失灵的方式全都是「平时看不出来」：
预算不累加时单看每个子任务都合规，无进展检测只看步数时振荡永远抓不到，
而这两种情况都要跑到线上、烧掉真金白银才暴露。

现在跑会失败，因为六个函数还是空的。挨个填，填对一个过一个。

    第 1 关  预算累加      —— 子预算之和不能超过父预算
    第 2 关  五类独立计数  —— 任何一类先到顶都要停
    第 3 关  无进展检测    —— 一直在动但没往前走，也要停
    第 4 关  振荡检测      —— A→B→A→B 这种来回不算进展
    第 5 关  升级载荷      —— 停下来之后交出去的东西要能接手
    第 6 关  终止判定      —— 「完成」必须是状态转换，不是模型说完成了

六关都过之后，脚本会跑三条会失控的轨迹（烧钱、死循环、振荡），
断言每一条都被对应的刹车拦住，且都交出了可续接的载荷。

对应笔记
--------
    10-Agent 与编排/01-五类硬预算
    10-Agent 与编排/02-终止条件
    10-Agent 与编排/03-升级到人与结构化中间状态
    10-Agent 与编排/90-里程碑：跑 100 次不失控的 agent
"""


# 五类硬预算。**每一类都要独立计数**——最容易漏的是 tool_calls：
# 一个在循环里反复调只读接口的 agent，token 涨得不快、时间也不长，
# 却可能把下游打挂。
BUDGET_KEYS = ["tokens", "seconds", "tool_calls", "steps", "cost"]


class BudgetExceeded(Exception):
    def __init__(self, key, used, limit):
        self.key, self.used, self.limit = key, used, limit
        super().__init__("%s 超预算：%s > %s" % (key, used, limit))


# ══════════════════════════════════════════════════════════════
# 第 1 关：预算沿调用链累加
# ══════════════════════════════════════════════════════════════

def split_budget(parent_remaining, requests):
    """把父任务的剩余预算分给若干子任务。

    parent_remaining —— {类别: 剩余量}
    requests         —— 子任务申请量的列表，每项是 {类别: 申请量}

    返回批准列表，每项是 {类别: 批准量}：
      - 按顺序处理，能全给就全给
      - 剩余不够时只给剩下的那些（可以是 0）
      - **总和绝不能超过 parent_remaining**

    这一关防的是多 agent 最常见的失控形态：每个子 agent 各自限 $0.2，
    但子 agent 的数量是动态的，乘起来等于没有上限。
    """
    raise NotImplementedError("第 1 关：顺序扣减，扣完为止")


def check_1():
    parent = {"cost": 0.50, "tokens": 10000}
    got = split_budget(parent, [{"cost": 0.20, "tokens": 4000},
                                {"cost": 0.20, "tokens": 4000},
                                {"cost": 0.20, "tokens": 4000}])
    total_cost = sum(g["cost"] for g in got)
    assert total_cost <= parent["cost"] + 1e-9, (
        "三个子任务各申请 0.20，父预算只有 0.50，批准总额不能超——"
        "实际批了 %.2f。这正是「每个都限 0.2 等于没限」的那个 bug" % total_cost)
    assert abs(got[0]["cost"] - 0.20) < 1e-9 and abs(got[1]["cost"] - 0.20) < 1e-9
    assert abs(got[2]["cost"] - 0.10) < 1e-9, "第三个只该拿到剩下的 0.10，实际 %.2f" % got[2]["cost"]

    # 预算耗尽后申请，应该批 0 而不是负数
    got2 = split_budget({"cost": 0.0}, [{"cost": 0.1}])
    assert got2[0]["cost"] == 0.0, "没有余额时应批 0，实际 %s" % got2[0]["cost"]
    return "父预算 0.50 分给三个各申请 0.20 的子任务 → 0.20/0.20/0.10"


# ══════════════════════════════════════════════════════════════
# 第 2 关：五类独立计数
# ══════════════════════════════════════════════════════════════

class Budget:
    """五类预算的计数器。"""

    def __init__(self, **limits):
        self.limits = {k: limits.get(k, float("inf")) for k in BUDGET_KEYS}
        self.used = {k: 0 for k in BUDGET_KEYS}

    def charge(self, **amounts):
        """记账。任何一类**记账后**超过上限就抛 BudgetExceeded。

        要求：
          - 只认 BUDGET_KEYS 里的类别，其余忽略
          - 先全部累加，再逐类检查（按 BUDGET_KEYS 的顺序报第一个超的）
          - 超了也要把账记上——**已经花掉的钱不会因为报错而退回来**，
            报表上得看得见

        「先记账再检查」这个顺序不是细节：反过来写的话，
        超预算的那一次消耗就从统计里消失了，事后复盘会少算。
        """
        raise NotImplementedError("第 2 关：累加，然后逐类检查")


def check_2():
    b = Budget(tokens=1000, tool_calls=3, cost=1.0)
    b.charge(tokens=400, tool_calls=1, cost=0.3)
    b.charge(tokens=400, tool_calls=1, cost=0.3)
    assert b.used["tokens"] == 800

    # tool_calls 先到顶——token 和 cost 都还有余量
    try:
        b.charge(tokens=10, tool_calls=2, cost=0.01)
        raise AssertionError("tool_calls 3 已用满，第 4 次必须抛")
    except BudgetExceeded as e:
        assert e.key == "tool_calls", "该报 tool_calls，实际报了 %s" % e.key
    assert b.used["tool_calls"] == 4, (
        "超预算的那次消耗也要记上账，实际 %d。"
        "不记的话事后复盘会少算已经花掉的钱" % b.used["tool_calls"])

    # 没设上限的类别不该拦
    b2 = Budget(tokens=100)
    b2.charge(tokens=10, seconds=99999, cost=1e9)
    assert b2.used["seconds"] == 99999
    return "tool_calls 先到顶（token 和 cost 尚有余量），且超支被记进账"


# ══════════════════════════════════════════════════════════════
# 第 3 关：无进展检测
# ══════════════════════════════════════════════════════════════

def no_progress(states, window=3):
    """连续 window 步状态没有变化，判为无进展，返回 True。

    states 是按时间排列的状态快照列表（可比较的值，比如字符串）。
    步数不足 window 时返回 False。

    **为什么不能只看步数**：一个 agent 可以在步数上限之内反复做同一件事——
    读同一个文件、发同一个查询——每一步都「合法」，但任务一动不动。
    步数上限只保证它会停，不保证它没白烧钱。
    """
    raise NotImplementedError("第 3 关：看末尾 window 个状态是不是全一样")


def check_3():
    assert no_progress(["a", "a", "a"]) is True
    assert no_progress(["a", "b", "c"]) is False
    assert no_progress(["a", "a"]) is False, "不足 window 时不判"
    # 前面卡住但最后动了 —— 不算无进展
    assert no_progress(["a", "a", "a", "b"]) is False, "只看末尾 window 个"
    # 长时间卡住
    assert no_progress(["x", "y", "y", "y", "y"]) is True
    assert no_progress([]) is False
    return "连续 3 步同状态判停；末尾动了就不判"


# ══════════════════════════════════════════════════════════════
# 第 4 关：振荡检测
# ══════════════════════════════════════════════════════════════

def oscillating(states, cycles=2):
    """检测 A→B→A→B 这类来回，返回 True。

    判据：末尾出现了长度为 2 的重复循环，且重复了 cycles 次。
    也就是末尾 2*cycles 个状态形如 [A,B,A,B,...] 且 A != B。

    **振荡是无进展检测抓不到的那一类**：状态每一步都在变，
    所以第 3 关判 False，但整体一步没往前走。
    典型场景是两个工具互相把对方的结果推翻。
    """
    raise NotImplementedError("第 4 关：看末尾是不是 A,B 的重复")


def check_4():
    assert oscillating(["a", "b", "a", "b"]) is True
    # 关键：振荡状态下第 3 关是抓不到的
    assert no_progress(["a", "b", "a", "b"]) is False, (
        "构造前提：振荡时状态一直在变，无进展检测判 False——"
        "所以必须有独立的振荡检测")

    assert oscillating(["a", "b", "c", "d"]) is False
    assert oscillating(["a", "a", "a", "a"]) is False, "全同是无进展，不是振荡"
    assert oscillating(["x", "a", "b", "a", "b"]) is True, "前面有别的也算"
    assert oscillating(["a", "b"]) is False, "只来回一次还不够"
    return "A→B→A→B 判停，而无进展检测对它无效——两个检测缺一不可"


# ══════════════════════════════════════════════════════════════
# 第 5 关：升级载荷
# ══════════════════════════════════════════════════════════════

REQUIRED_FIELDS = ["已完成", "卡在哪", "试过什么", "当前假设", "下一步建议"]


def escalation_payload(done, blocked_at, attempts, hypothesis, suggestion):
    """构造交给人的结构化中间状态，返回 dict。

    五个字段一个都不能少，且**都不能是空的**——
    空字段等于把整个任务原样退回，人只能从头重做。

    任一参数为空（空字符串、空列表、None）时抛 ValueError，
    并在消息里点名是哪个字段。

    「我失败了」这四个字是最没用的升级：它没有减少人的工作量。
    有用的升级要让人**接着做**，而不是**重新做**。
    """
    raise NotImplementedError("第 5 关：校验五个字段都非空，然后组装")


def check_5():
    p = escalation_payload("拉取了 12 份文档", "第 3 份 PDF 解析失败",
                           ["换了 OCR 引擎", "试了降分辨率"],
                           "这份 PDF 是扫描件且有水印", "人工转录第 3 份后重跑")
    assert set(REQUIRED_FIELDS) <= set(p), "五个字段都要在，实际 %s" % sorted(p)
    assert p["卡在哪"] == "第 3 份 PDF 解析失败"

    # 任一字段为空都要拒绝，并点名
    for i, args in enumerate([("", "b", ["c"], "d", "e"),
                              ("a", "", ["c"], "d", "e"),
                              ("a", "b", [], "d", "e"),
                              ("a", "b", ["c"], "", "e"),
                              ("a", "b", ["c"], "d", "")]):
        try:
            escalation_payload(*args)
            raise AssertionError("第 %d 个字段为空时应该抛 ValueError" % (i + 1))
        except ValueError as e:
            assert REQUIRED_FIELDS[i] in str(e), (
                "报错要点名哪个字段，实际 %r" % str(e))
    return "五段齐全才放行；缺任何一段都点名拒绝"


# ══════════════════════════════════════════════════════════════
# 第 6 关：终止判定
# ══════════════════════════════════════════════════════════════

def should_stop(states, budget, goal_reached):
    """综合判定该不该停。返回 (是否停止, 原因)。

    按这个顺序检查，返回第一个命中的：
      1. goal_reached 为 True                    → "完成"
      2. 任一类预算已达上限（used >= limit）      → "预算：<类别>"
      3. no_progress(states)                     → "无进展"
      4. oscillating(states)                     → "振荡"
      5. 都没有                                  → (False, "继续")

    **goal_reached 必须由外部的状态检查得出，不能是模型自称完成。**
    「模型说做完了但实际没做完」是这类系统最常见的静默失败——
    它不报错、不超预算、看起来一切正常。
    """
    raise NotImplementedError("第 6 关：按顺序判，返回第一个命中的")


def check_6():
    b = Budget(steps=10)
    assert should_stop(["a", "b"], b, True) == (True, "完成")

    full = Budget(steps=3)
    full.used["steps"] = 3
    stop, why = should_stop(["a", "b"], full, False)
    assert stop is True and "预算" in why and "steps" in why, "应报 steps 预算：%s" % why

    assert should_stop(["a", "a", "a"], b, False) == (True, "无进展")
    assert should_stop(["a", "b", "a", "b"], b, False) == (True, "振荡")
    assert should_stop(["a", "b", "c"], b, False) == (False, "继续")

    # 完成优先于其他 —— 卡住但确实做完了，不该报无进展
    assert should_stop(["a", "a", "a"], b, True) == (True, "完成")
    return "四种停止原因都能区分，且「完成」优先"


# ══════════════════════════════════════════════════════════════

def _drive(name, trace, limits, goal_at=None):
    """跑一条假轨迹，返回 (停止原因, 走了几步)。"""
    b, states = Budget(**limits), []
    for i, (state, cost) in enumerate(trace, 1):
        states.append(state)
        try:
            b.charge(steps=1, cost=cost, tokens=cost * 1000)
        except BudgetExceeded as e:
            return "预算：%s" % e.key, i
        stop, why = should_stop(states, b, goal_at is not None and i >= goal_at)
        if stop:
            return why, i
    return "跑完未触发", len(trace)


def demo():
    print("\n" + "═" * 64)
    print("三条会失控的轨迹，各自被哪道刹车拦住")
    print("═" * 64)

    cases = [
        ("烧钱型：每步都很贵", [("s%d" % i, 0.3) for i in range(20)], {"cost": 1.0}),
        ("死循环型：一直读同一个文件", [("读 config", 0.01)] * 20, {"cost": 99}),
        ("振荡型：两个工具互相推翻", [("A", 0.01), ("B", 0.01)] * 10, {"cost": 99}),
    ]
    for name, trace, limits in cases:
        why, steps = _drive(name, trace, limits)
        print("  %-24s 第 %2d 步停下 —— %s" % (name, steps, why))
        assert why != "跑完未触发", "%s 必须被拦住" % name

    ok_why, ok_steps = _drive("正常", [("s%d" % i, 0.01) for i in range(8)],
                              {"cost": 99}, goal_at=8)
    print("  %-24s 第 %2d 步停下 —— %s" % ("正常完成", ok_steps, ok_why))

    print("\n**三种失控形态需要三道不同的刹车**：")
    print("  · 预算只拦住第一种，死循环和振荡都在预算之内")
    print("  · 无进展检测拦住第二种，但对振荡无效（状态一直在变）")
    print("  · 振荡检测才拦得住第三种")

    print("\n" + "─" * 64)
    p = escalation_payload("拉取了 12 份文档", "第 3 份 PDF 解析失败",
                           ["换了 OCR 引擎", "试了降分辨率"],
                           "这份 PDF 是扫描件且有水印", "人工转录第 3 份后重跑")
    print("停下来之后交给人的载荷：")
    for k in REQUIRED_FIELDS:
        v = p[k]
        print("  %-8s %s" % (k, "、".join(v) if isinstance(v, list) else v))
    print("\n**判据：拿着这份东西，人能接着做，而不是重新做。**")
    print("═" * 64)
    print("""
接下来接上真的 agent，里程碑才算过：

  1. 把假轨迹换成真调用，五道预算都用故意死循环的任务验证一遍
  2. 把「完成」实现成外部可观测的状态转换——**不能是模型自称完成**
  3. 找同事拿着升级载荷实际接手一次，问他还缺什么
  4. 做混沌测试：杀检索、杀工具、杀主模型，逐项对照预期降级级别
  5. 跑 100 次真实任务，逐次记录

把 100 次的统计表、三种检测各自触发过几次、混沌测试结果
填进里程碑笔记的「结果与数据」。""")


def main():
    checks = [("预算累加", check_1), ("五类计数", check_2), ("无进展", check_3),
              ("振荡", check_4), ("升级载荷", check_5), ("终止判定", check_6)]
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
