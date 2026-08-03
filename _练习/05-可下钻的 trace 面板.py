#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 1 里程碑的起步脚本：span 树、尾部采样、每次成功任务成本。

怎么用
------
    python "_练习/05-可下钻的 trace 面板.py"

不需要装任何东西，也不需要接 OTel——span 用固定的假数据喂进来。
练的是**聚合口径**，因为这几处算错了以后，面板会一直显示一个
好看且错误的数字，而且没有任何东西会提醒你：
成本分母用调用次数而不是成功任务数，会让越来越不可靠的系统显得越来越便宜；
头部采样会把错误请求按比例丢掉，于是「错误率下降了」。

现在跑会失败，因为五个函数还是空的。挨个填，填对一个过一个。

    第 1 关  span 树         —— 父子关系要能还原，孤儿不能丢
    第 2 关  成本归因        —— 子 span 的成本要能汇总到父，且不重复计
    第 3 关  每次成功任务成本 —— 分母是成功数，不是调用数
    第 4 关  尾部采样        —— 错误与慢请求必须全留
    第 5 关  高基数守门      —— 高基数字段不许进指标维度

五关都过之后，脚本会拿一组「成功率下降但单次调用成本没变」的数据
跑一遍面板：按调用算成本纹丝不动，按成功任务算立刻涨了六成。

对应笔记
--------
    05-可观测性与成本/01-Trace 与 Span
    05-可观测性与成本/02-必打字段清单
    05-可观测性与成本/04-成本归因与每次成功任务成本
    05-可观测性与成本/90-里程碑：可下钻的 trace 面板
"""

import collections


# 一次请求的假 span 列表。真做的时候这些字段跟 OTel GenAI 语义约定命名。
SPANS = [
    {"id": "s1", "parent": None, "name": "请求", "ms": 4200, "cost": 0.0, "error": False},
    {"id": "s2", "parent": "s1", "name": "检索", "ms": 320, "cost": 0.0002, "error": False},
    {"id": "s3", "parent": "s2", "name": "embedding", "ms": 90, "cost": 0.0001, "error": False},
    {"id": "s4", "parent": "s1", "name": "模型调用", "ms": 3400, "cost": 0.0180, "error": False},
    {"id": "s5", "parent": "s1", "name": "工具调用", "ms": 400, "cost": 0.0, "error": True},
]

# 高基数字段：能进 span 属性，**不能**进指标维度
HIGH_CARDINALITY = {"user_id", "trace_id", "prompt_text", "session_id", "request_id"}


# ══════════════════════════════════════════════════════════════
# 第 1 关：还原 span 树
# ══════════════════════════════════════════════════════════════

def build_tree(spans):
    """把扁平的 span 列表还原成 {span_id: [子 span_id, ...]}。

    根节点（parent 为 None）挂在 key `None` 下。
    子节点顺序保持输入顺序。

    **孤儿 span 不能丢**：parent 指向一个不在列表里的 id 时
    （采样把父 span 丢了、或者跨服务传播断了），
    仍然要出现在结果里——挂在它自己的 parent id 下即可。
    悄悄丢掉孤儿，面板上就会少一整棵子树，而你不会收到任何提示。
    """
    raise NotImplementedError("第 1 关：按 parent 分组")


def check_1():
    t = build_tree(SPANS)
    assert t[None] == ["s1"], "根节点应挂在 None 下"
    assert t["s1"] == ["s2", "s4", "s5"], "s1 的三个子节点，顺序保持：%s" % t["s1"]
    assert t["s2"] == ["s3"], "两层嵌套要能还原"

    # 孤儿：父 span 不在列表里
    orphan = SPANS + [{"id": "s9", "parent": "missing", "name": "掉队的",
                       "ms": 10, "cost": 0.0, "error": False}]
    t2 = build_tree(orphan)
    assert "missing" in t2 and t2["missing"] == ["s9"], (
        "父 span 不在列表里时，孤儿仍要出现在树里——"
        "丢掉它面板上会少一整棵子树，且没有任何提示")
    return "三层树还原正确，孤儿 span 没丢"


# ══════════════════════════════════════════════════════════════
# 第 2 关：成本归因
# ══════════════════════════════════════════════════════════════

def subtree_cost(spans, root_id):
    """root_id 这棵子树的总成本 = 它自己 + 所有后代。

    **每个 span 只能算一次**。最常见的错误是既加了子 span 的成本，
    又把父 span 上「已经含了子节点」的那份也加进来，于是重复计。
    这里的约定是：每个 span 的 cost 字段只表示**它自己**产生的成本，
    父节点不预先包含子节点的。

    root_id 不存在时返回 0.0。
    """
    raise NotImplementedError("第 2 关：递归累加自己与后代")


def check_2():
    total = subtree_cost(SPANS, "s1")
    expect = 0.0 + 0.0002 + 0.0001 + 0.0180 + 0.0
    assert abs(total - expect) < 1e-9, "整棵树应为 %.4f，实际 %.4f" % (expect, total)

    # 子树独立可算 —— 这是「能下钻」的意思
    assert abs(subtree_cost(SPANS, "s2") - 0.0003) < 1e-9, "检索子树含 embedding"
    assert abs(subtree_cost(SPANS, "s3") - 0.0001) < 1e-9, "叶子节点就是它自己"

    # 各子树之和必须等于整棵树 —— 没有重复计
    parts = sum(subtree_cost(SPANS, i) for i in ["s2", "s4", "s5"])
    assert abs(parts - total) < 1e-9, (
        "三棵子树之和 %.4f 应等于整树 %.4f。不等说明有 span 被算了两次"
        % (parts, total))
    assert subtree_cost(SPANS, "nope") == 0.0
    return "整树 %.4f；模型调用一项就占 %.1f%%" % (total, subtree_cost(SPANS, "s4") / total * 100)


# ══════════════════════════════════════════════════════════════
# 第 3 关：每次成功任务成本
# ══════════════════════════════════════════════════════════════

def cost_per_success(runs):
    """runs 是若干次任务，每项 {"cost": float, "success": bool}。

    返回 (每次调用成本, 每次成功任务成本)。

        每次调用成本     = 总成本 / 调用次数
        每次成功任务成本 = 总成本 / **成功次数**

    **分母的差别就是这个指标存在的全部理由**：失败的调用照样烧钱。
    用调用次数当分母，一个成功率从 100% 掉到 60% 的系统，
    单次调用成本纹丝不动——报表上看不出任何异常。

    没有成功的任务时，第二项返回 float("inf")：
    花了钱、一件事没办成，这个事实不该被显示成 0 或者报错崩掉。
    """
    raise NotImplementedError("第 3 关：两个除法，注意第二个的分母")


def check_3():
    # 全部成功
    a = cost_per_success([{"cost": 0.1, "success": True}] * 10)
    assert abs(a[0] - 0.1) < 1e-9 and abs(a[1] - 0.1) < 1e-9, "全成功时两者相等"

    # 关键用例：成功率掉到 60%，单次调用成本完全没变
    runs = [{"cost": 0.1, "success": i < 6} for i in range(10)]
    per_call, per_success = cost_per_success(runs)
    assert abs(per_call - 0.1) < 1e-9, (
        "单次调用成本仍是 0.10——报表上什么都看不出来")
    assert abs(per_success - 0.1 / 0.6) < 1e-9, "每次成功任务成本应为 0.167"
    assert per_success > per_call * 1.6, (
        "成功率掉到 60%% 时，真实成本涨了六成而单次调用成本不动。"
        "这就是必须用成功数当分母的理由")

    inf = cost_per_success([{"cost": 1.0, "success": False}])[1]
    assert inf == float("inf"), "零成功时应返回 inf，不能返回 0 或崩掉"
    return "成功率 60%% 时：按调用 %.3f（没变）/ 按成功任务 %.3f（涨了六成）" % (
        per_call, per_success)


# ══════════════════════════════════════════════════════════════
# 第 4 关：尾部采样
# ══════════════════════════════════════════════════════════════

def should_keep(trace, slow_ms=3000, sample_rate=0.1, index=0):
    """判断一条 trace 保不保留。返回 True / False。

    trace 是 {"error": bool, "ms": int}。规则：
      1. 有错误        → **必留**
      2. 耗时 ≥ slow_ms → **必留**
      3. 其余          → 按 sample_rate 抽样

    第 3 条不要用随机数——重放和测试都需要确定性。
    用 index 做确定性抽样：`index % round(1/sample_rate) == 0` 即可。

    **前两条是这一关的全部要点。** 头部采样（请求刚进来就掷骰子）
    会把错误和慢请求按同样的比例丢掉，于是你的面板上错误率变低了、
    P99 变好看了——而系统一点没变。**必须等请求结束、知道结果了再决定留不留**，
    这就是「尾部」的意思。
    """
    raise NotImplementedError("第 4 关：错误必留、慢必留，其余确定性抽样")


def check_4():
    # 错误必留，哪怕它又快又「不该被抽中」
    assert should_keep({"error": True, "ms": 5}, index=7) is True, "错误请求必须留"
    # 慢必留
    assert should_keep({"error": False, "ms": 9999}, index=7) is True, "慢请求必须留"
    # 正常请求按比例
    assert should_keep({"error": False, "ms": 100}, index=0) is True
    assert should_keep({"error": False, "ms": 100}, index=1) is False

    # 全局验证：100 条里 5 条是错误，全部必须留下
    traces = [{"error": i % 20 == 3, "ms": 100} for i in range(100)]
    kept = [t for i, t in enumerate(traces) if should_keep(t, index=i)]
    errs_total = sum(1 for t in traces if t["error"])
    errs_kept = sum(1 for t in kept if t["error"])
    assert errs_kept == errs_total, (
        "%d 条错误只留下 %d 条——头部采样就是这样把错误率「优化」掉的"
        % (errs_total, errs_kept))
    return "错误 %d/%d 全留，正常请求抽样后共留 %d 条" % (errs_kept, errs_total, len(kept))


# ══════════════════════════════════════════════════════════════
# 第 5 关：高基数守门
# ══════════════════════════════════════════════════════════════

def check_metric_labels(labels):
    """检查一组要打进**指标维度**的标签名，返回其中的高基数字段列表。

    在 HIGH_CARDINALITY 里的就是。返回顺序按传入顺序。

    **这个区分不是洁癖**：span 属性是查一次翻一次，高基数无所谓；
    指标维度是持续聚合，每多一个取值就多一条时间序列。
    把 user_id 打进指标维度，时间序列数会等于用户数——时序库会被打爆。
    """
    raise NotImplementedError("第 5 关：挑出高基数字段")


def check_5():
    bad = check_metric_labels(["model", "user_id", "tenant_tier", "trace_id"])
    assert bad == ["user_id", "trace_id"], "应挑出两个，实际 %s" % bad
    assert check_metric_labels(["model", "tenant_tier", "feature"]) == [], "干净时返回空"
    assert check_metric_labels([]) == []
    # 顺序要保持
    assert check_metric_labels(["trace_id", "user_id"]) == ["trace_id", "user_id"]
    return "挑出 %s —— 这两个只能进 span 属性，不能进指标维度" % bad


# ══════════════════════════════════════════════════════════════

def demo():
    print("\n" + "═" * 64)
    print("一条请求的 span 树与成本下钻")
    print("═" * 64)
    tree = build_tree(SPANS)
    by_id = {s["id"]: s for s in SPANS}
    total = subtree_cost(SPANS, "s1")

    def show(sid, depth=0):
        s = by_id[sid]
        c = subtree_cost(SPANS, sid)
        flag = "  ← 出错" if s["error"] else ""
        print("  %s%-14s %6d ms  $%.4f  %5.1f%%%s"
              % ("　" * depth, s["name"], s["ms"], c, c / total * 100 if total else 0, flag))
        for kid in tree.get(sid, []):
            show(kid, depth + 1)

    show("s1")

    print("\n" + "─" * 64)
    print("成本口径对照：成功率从 100% 掉到 60%，单次调用成本一动不动")
    print("─" * 64)
    for rate in [1.0, 0.8, 0.6]:
        n = 10
        runs = [{"cost": 0.1, "success": i < int(n * rate)} for i in range(n)]
        pc, ps = cost_per_success(runs)
        print("  成功率 %3.0f%%   按调用 $%.4f   按成功任务 $%.4f" % (rate * 100, pc, ps))
    print("\n**左边那一列是多数成本看板的主指标，而它对质量下降完全无感。**")

    print("\n" + "─" * 64)
    traces = [{"error": i % 20 == 3, "ms": 5000 if i % 33 == 0 else 100} for i in range(100)]
    kept = [(i, t) for i, t in enumerate(traces) if should_keep(t, index=i)]
    print("尾部采样：100 条留下 %d 条" % len(kept))
    print("  其中错误 %d 条（共 %d）、慢请求 %d 条（共 %d）—— 两类都是全留"
          % (sum(1 for _, t in kept if t["error"]), sum(1 for t in traces if t["error"]),
             sum(1 for _, t in kept if t["ms"] >= 3000), sum(1 for t in traces if t["ms"] >= 3000)))

    bad = check_metric_labels(["model", "tenant_tier", "user_id", "feature", "trace_id"])
    print("\n指标维度守门：拦下 %s" % bad)
    print("═" * 64)
    print("""
接下来接上真的 OTel，里程碑才算过：

  1. 四类 span 打通，字段跟 GenAI 语义约定命名，见 02-必打字段清单
  2. prompt_version 用提示词内容的哈希，避免忘记更新
  3. 配尾部采样，**确认错误请求不会被随机丢掉**
  4. 三条漂移曲线全部按 feature 和 tenant 拆开
  5. 计时演练：随便挑一条历史坏输出，从零定位到那次 trace，记下用时
  6. 注入实验：故意往索引里少灌一批文档，看哪条曲线先动、多久看得出来

第 5 项是唯一能证明这个面板真的有用的证据。把用时填进里程碑笔记。""")


def main():
    checks = [("span 树", check_1), ("成本归因", check_2), ("成功任务成本", check_3),
              ("尾部采样", check_4), ("高基数守门", check_5)]
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
        demo()


if __name__ == "__main__":
    main()
