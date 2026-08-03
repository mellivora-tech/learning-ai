#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 3 里程碑的起步脚本：状态机、幂等写入、断点续跑。

怎么用
------
    python "_练习/08-可中断可续跑的长任务.py"

不需要装任何东西，也不需要数据库——存储用一个内存里的假 KV。
练的是**崩溃安全的那几条不变式**，它们的共同特点是：
写错了在正常路径上一点问题都没有，只有在「刚好在那一步崩掉」时才暴露。
所以这里的裁判全部是模拟崩溃：在每一个可能的位置各崩一次，看结果对不对。

现在跑会失败，因为五个函数还是空的。挨个填，填对一个过一个。

    第 1 关  状态机       —— 非法转移必须被拒绝，不是被容忍
    第 2 关  幂等写入     —— 同一个 key 写两次，只能生效一次
    第 3 关  检查点       —— 先落盘再执行，还是先执行再落盘
    第 4 关  续跑         —— 从任意一步崩溃后恢复，最终结果必须一致
    第 5 关  重放确定性   —— 重放路径上不能有随机数和当前时间

五关都过之后，脚本会在每一个步骤边界各崩一次并恢复，
断言全部路径最终收敛到同一个结果。

对应笔记
--------
    08-工程基座/02-状态机
    08-工程基座/05-断点续跑
    08-工程基座/07-幂等存储与去重
    08-工程基座/90-里程碑：可中断可续跑、重启不丢状态的长任务系统
"""


# ══════════════════════════════════════════════════════════════
# 状态定义
# ══════════════════════════════════════════════════════════════

# 允许的状态转移。**没列出来的都不允许**——这是本篇的第一条不变式。
TRANSITIONS = {
    "pending": {"running", "cancelled"},
    "running": {"paused", "done", "failed", "cancelled"},
    "paused": {"running", "cancelled"},
    "failed": {"running"},          # 允许重试
    "done": set(),                  # 终态
    "cancelled": set(),             # 终态
}

TERMINAL = {"done", "cancelled"}


class Store:
    """一个假的 KV 存储。真做的时候换成数据库，语义一样。"""

    def __init__(self):
        self.data = {}
        self.writes = 0             # 记录真正落盘的次数，用来验证幂等

    def get(self, key, default=None):
        return self.data.get(key, default)

    def put(self, key, value):
        self.data[key] = value
        self.writes += 1


class Crash(Exception):
    """模拟进程被杀。裁判用它在指定步骤前中断执行。"""


# ══════════════════════════════════════════════════════════════
# 第 1 关：状态机
# ══════════════════════════════════════════════════════════════

def can_transition(src, dst):
    """src 状态能不能转到 dst，返回 True / False。

    查 TRANSITIONS 即可。未知状态一律返回 False。

    **为什么要显式拒绝而不是默默允许**：非法转移几乎总是并发或重试的症状。
    比如一个已经 done 的任务又被转成 running，多半是重复投递，
    此时静默接受会让任务被执行两遍。**让它报错，问题就在第一现场暴露。**
    """
    raise NotImplementedError("第 1 关：查表，未知状态返回 False")


def check_1():
    assert can_transition("pending", "running") is True
    assert can_transition("running", "done") is True
    assert can_transition("failed", "running") is True, "失败后允许重试"

    # 终态不能再动 —— 重复投递的典型症状
    assert can_transition("done", "running") is False, (
        "done 是终态，转回 running 必须拒绝——"
        "这通常意味着任务被重复投递了")
    assert can_transition("cancelled", "running") is False
    # 跳步
    assert can_transition("pending", "done") is False, "不能从 pending 直接跳到 done"
    # 未知状态
    assert can_transition("zzz", "running") is False
    assert can_transition("running", "zzz") is False
    return "合法转移放行，终态与跳步被拒绝"


# ══════════════════════════════════════════════════════════════
# 第 2 关：幂等写入
# ══════════════════════════════════════════════════════════════

def idempotent_put(store, key, value):
    """只在 key 不存在时写入。返回 True 表示这次真的写了，False 表示已存在被跳过。

    **这是「至少一次投递」能变得安全的唯一支点。** 消息队列没法保证恰好一次，
    所以消费端必须能吸收重复——办法就是让重复的那次什么都不做。

    注意不能写成「先 get 判断、再 put」然后当它是原子的：
    真实存储上这里要用条件写（`INSERT ... ON CONFLICT DO NOTHING`、
    `SETNX`、或者带唯一索引的插入）。**这个假 Store 是单线程的，
    但你在真实实现里必须用条件写，否则并发下两个请求会双双通过检查。**
    """
    raise NotImplementedError("第 2 关：存在就跳过，不存在才写")


def check_2():
    s = Store()
    assert idempotent_put(s, "k", "v1") is True, "第一次应该真的写入"
    assert s.writes == 1

    assert idempotent_put(s, "k", "v2") is False, "第二次应该被跳过"
    assert s.writes == 1, "重复写入不能落盘，实际落盘 %d 次" % s.writes
    assert s.get("k") == "v1", "已存在时保留原值，不能被覆盖成 v2"

    # 换个 key 仍然要能写
    assert idempotent_put(s, "k2", "x") is True and s.writes == 2
    return "重复写入被吸收，落盘 %d 次而调用了 3 次" % s.writes


# ══════════════════════════════════════════════════════════════
# 第 3 关：检查点
# ══════════════════════════════════════════════════════════════

def checkpoint(store, task_id, step_index, result):
    """记录「第 step_index 步已完成，结果是 result」。

    存储的 key 用 f"{task_id}:step:{step_index}"，值就是 result。
    用 idempotent_put 写——**同一步被重放时不能覆盖已有结果**。

    返回这一步最终生效的结果值（不管是这次写进去的，还是之前就有的）。

    这个返回值语义很重要：续跑时重放到已完成的步骤，
    **要拿回当初的结果，而不是这次重算出来的**。两者可能不同
    （比如结果里带了时间戳），而下游依赖的是当初那个。
    """
    raise NotImplementedError("第 3 关：幂等写入，然后返回最终生效的值")


def check_3():
    s = Store()
    assert checkpoint(s, "t1", 0, "第一次的结果") == "第一次的结果"

    # 重放同一步：必须拿回当初的值，而不是这次算的
    got = checkpoint(s, "t1", 0, "重算出来的不同结果")
    assert got == "第一次的结果", (
        "重放已完成的步骤必须返回当初的结果，实际返回 %r。"
        "返回新值会让下游看到和第一次不一致的东西" % got)
    assert s.writes == 1, "重放不能产生新的写入"

    # 不同步骤、不同任务互不干扰
    assert checkpoint(s, "t1", 1, "B") == "B"
    assert checkpoint(s, "t2", 0, "C") == "C"
    assert s.writes == 3
    return "重放返回当初的值，落盘 %d 次而调用了 4 次" % s.writes


# ══════════════════════════════════════════════════════════════
# 第 4 关：续跑
# ══════════════════════════════════════════════════════════════

def run_task(store, task_id, steps, crash_before=None):
    """执行一个多步任务，支持从中断处续跑。

    steps        —— 函数列表，每个接收「上一步的结果」返回本步结果，第一个接收 None
    crash_before —— 若不是 None，在执行到第 crash_before 步**之前**抛 Crash

    要点：
      1. 逐步执行。执行第 i 步之前，**先查 checkpoint 有没有已完成的记录**
      2. 有记录 → 跳过执行，直接用记录里的结果当作本步输出
      3. 没记录 → 真的调用 steps[i]，然后 checkpoint 落盘
      4. 到了 crash_before 那一步就抛 Crash（在执行和落盘之前）

    返回最后一步的结果。

    **顺序是「执行完再落盘」**，所以崩在落盘前会导致这一步重做——
    这就是为什么每一步都必须幂等，见第 2 关。反过来「先落盘再执行」
    会更糟：崩在执行前，这一步就被永久跳过了。
    """
    raise NotImplementedError("第 4 关：查检查点 → 跳过或执行 → 落盘")


def check_4():
    calls = []

    def make_steps():
        calls.clear()
        return [
            lambda prev: (calls.append(0), "A")[1],
            lambda prev: (calls.append(1), prev + "B")[1],
            lambda prev: (calls.append(2), prev + "C")[1],
        ]

    # 不崩：正常跑完
    s = Store()
    assert run_task(s, "t", make_steps()) == "ABC"
    assert calls == [0, 1, 2]

    # 在第 1 步前崩，然后续跑
    s2 = Store()
    try:
        run_task(s2, "t", make_steps(), crash_before=1)
        raise AssertionError("应该抛出 Crash")
    except Crash:
        pass
    assert calls == [0], "崩之前只该执行第 0 步，实际 %s" % calls

    result = run_task(s2, "t", make_steps())        # 续跑
    assert result == "ABC", "续跑后结果应为 ABC，实际 %r" % result
    assert calls == [1, 2], (
        "续跑时第 0 步应该走检查点而不重新执行，实际执行了 %s。"
        "重复执行第 0 步意味着副作用会发生两遍" % calls)
    return "正常跑通；第 1 步前崩溃后续跑，已完成的步骤没有重跑"


# ══════════════════════════════════════════════════════════════
# 第 5 关：重放确定性
# ══════════════════════════════════════════════════════════════

FORBIDDEN_IN_REPLAY = ["random", "time.time", "datetime.now", "uuid4"]


def check_replay_safety(source):
    """检查一段「会被重放的代码」的源码文本，返回其中出现的禁用调用列表。

    在 FORBIDDEN_IN_REPLAY 里逐个找，出现了就收集起来（顺序按该列表）。

    **为什么这些东西不能出现在重放路径上**：续跑的正确性依赖
    「同样的输入重放出同样的结果」。随机数、当前时间、随机 UUID
    每次重放都不同，于是重放出来的执行路径和当初不一样，
    检查点就对不上了——**这类 bug 只在崩溃恢复时出现，平时测不出来**。

    正确做法是把这些值在**第一次执行时**算好并写进检查点，
    重放时从检查点读，而不是重新生成。
    """
    raise NotImplementedError("第 5 关：在源码文本里找禁用调用")


def check_5():
    bad = "def step(prev):\n    return {'id': uuid4(), 'at': time.time()}"
    found = check_replay_safety(bad)
    assert "uuid4" in found and "time.time" in found, "应该同时抓到两个，实际 %s" % found

    good = "def step(prev):\n    return {'id': prev['id'], 'at': prev['at']}"
    assert check_replay_safety(good) == [], "干净的代码应返回空列表"

    assert "random" in check_replay_safety("x = random.choice(items)")
    assert check_replay_safety("") == []
    return "抓到 %s；确定性的代码不误报" % found


# ══════════════════════════════════════════════════════════════

def demo():
    print("\n" + "═" * 64)
    print("在每一个步骤边界各崩一次，验证最终结果都一致")
    print("═" * 64)

    def steps_of(log):
        return [
            lambda prev: (log.append("执行 0"), "A")[1],
            lambda prev: (log.append("执行 1"), prev + "B")[1],
            lambda prev: (log.append("执行 2"), prev + "C")[1],
        ]

    for crash_at in [None, 0, 1, 2]:
        store, log = Store(), []
        if crash_at is not None:
            try:
                run_task(store, "task", steps_of(log), crash_before=crash_at)
            except Crash:
                log.append("💥 崩溃")
        result = run_task(store, "task", steps_of(log))
        label = "不崩溃" if crash_at is None else "在第 %d 步前崩溃" % crash_at
        print("  %-16s → %s    执行轨迹 %s" % (label, result, log))
        assert result == "ABC", "所有路径都必须收敛到 ABC"

    print("\n**四条路径结果全部是 ABC，且已完成的步骤没有重复执行。**")
    print("注意崩溃越晚，续跑时重新执行的步骤越少——检查点就是在买这个。")
    print("═" * 64)
    print("""
接下来换成真的存储与真的任务，里程碑才算过：

  1. 把 Store 换成数据库，`idempotent_put` 换成条件写
     （`INSERT ... ON CONFLICT DO NOTHING` 或带唯一索引的插入）
  2. 状态转移也落库，并且**用同一个事务**写状态和检查点
  3. 真的 kill -9 一次进程，重启后确认任务从断点继续
  4. 并发投递同一个任务两次，确认只执行一遍
  5. 跑一次长任务，中途暂停再恢复，确认状态和结果都对

把崩溃点、恢复耗时、重复执行次数填进里程碑笔记的「结果与数据」。""")


def main():
    checks = [("状态机", check_1), ("幂等写入", check_2), ("检查点", check_3),
              ("续跑", check_4), ("重放确定性", check_5)]
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
