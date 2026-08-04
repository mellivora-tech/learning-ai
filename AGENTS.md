# AGENTS.md

给在这个库里干活的 AI agent 看的操作说明。

内容与文体规范在 [00-总索引](00-总索引.md) 的「写作约定」一节，那里是唯一权威，本文件不重复。这里只讲 agent 特有的事：动笔前必须做什么、用什么工具、交付前查什么。

## 动笔前必须联网核实

**凡是涉及会变的事实，先搜再写。** 不许凭训练时的记忆下笔——模型的知识有截止日期，写下的那一刻就已经落后，而读者看不出来。

**举例统一用中国开源模型**：架构与权重包看 Qwen3-8B（最朴素的 dense 结构，配置干净），训练算力看 DeepSeek-V3（业内极少数公布完整训练账本的）。需要中外对照时才引 Llama 系。

必须搜的清单：

- 模型规格：参数量、层数、上下文窗口、价格、发布时间
- 榜单：还活着吗、最后更新是什么时候、当前怎么排
- 基准：哪些饱和了、当前推荐用哪些变体
- 框架与工具：还在维护吗、当前推荐用法、有没有被取代
- 硬件：显存、带宽、代际
- 任何带「目前」「最新」「主流」语气的判断

反面教材（本库真实踩过的）：

| 写下时 | 实际情况 |
| --- | --- |
| 拿 128k 当「长上下文」的代表 | 2026 年前沿模型标称已到 100 万–1000 万 token |
| 把 Open LLM Leaderboard 列为推荐榜单 | 2025 年 3 月已退役，只剩存档 |
| 用 MMLU、HumanEval 当区分度基准 | 都已饱和，2026 年该看 MMLU-Pro / GPQA-Diamond / SWE-bench Verified |

三条都不是笔误，是把某个时间点的行业现状当成了永久事实。

搜完之后按 [00-总索引](00-总索引.md) 里「会过期的数字要带时间戳」那条写：能写成规律就别绑数字，必须给数字就标明「谁 + 什么时候」。

## 画图用 `_工具/mkdraw.py`

概念优先用图解释。别手摆 Excalidraw 坐标，十几行声明就够：

```python
import sys; sys.path.insert(0, "_工具")
from mkdraw import Draw

d = Draw()
a, b, c = d.chain_down(["切词", "过 N 层", "挑一个"], cx=200)
d.arrow(320, c["cy"], [(90, 0), (90, a["cy"] - c["cy"]), (4, a["cy"] - c["cy"])],
        dashed=True, label="重来一遍")
d.save("我的图")     # 写到 _附件/，并打印该用的嵌入语法
```

图元：`box` `circle` `text` `rect` `line` `arrow` `arrow_between` `hop`，布局助手 `chain_down` `chain_right`。颜色只用 `PALETTE` 里那五档 tone，别在单张图里写死色值。

**状态机和时序图手写 SVG**，放 `_附件/`，用 `![[名字.svg|宽度]]` 嵌入。**这个库不再用 Mermaid**——它的箭头只有一种样式，而状态机上最该被一眼看出来的正是「主链路 / 故障 / 重试 / 恢复」的区别。

写 SVG 时：颜色用 `mkdraw` 的五档 tone；**实线主链路、虚线旁路**；整图铺一层 `#ffffff` 底（否则深色主题下文字不可读）；只写 `viewBox` 不写死宽高；带上 `<title>` 与 `<desc>`。样例见 `_附件/长任务状态机.svg` 与 `_附件/熔断器三态.svg`。

## 交付前的检查

```bash
# 断链：wikilink 指向不存在的笔记
# 会先剥掉代码块与行内代码——写作约定里举语法例子时会出现 [[名字.excalidraw.md]] 这类
# 不该被当成真链接的东西，不剥就是常驻误报。
python3 - <<'EOF'
import os, re
def strip_code(s):
    return re.sub(r'`[^`\n]*`', '', re.sub(r'```.*?```', '', s, flags=re.S))
notes, alias, files = set(), set(), []
for r, ds, fs in os.walk("."):
    ds[:] = [d for d in ds if d not in (".obsidian", ".git")]
    for f in fs:
        if not f.endswith(".md"): continue
        p = os.path.join(r, f)
        files.append(p)
        notes |= {f[:-3], f}
        m = re.search(r'^---\n(.*?)\n---', open(p, encoding="utf-8").read(), re.S)
        if m:
            am = re.search(r'^aliases:\n((?:  - .*\n)+)', m.group(1) + "\n", re.M)
            if am: alias |= {a.strip() for a in re.findall(r'  - (.*)', am.group(1))}
bad = {(os.path.basename(p), l.strip()) for p in files
       for l in re.findall(r'\[\[([^\]|#]+)', strip_code(open(p, encoding="utf-8").read()))
       if l.strip() not in notes and l.strip() not in alias}
print(sorted(bad) or "断链: 无")
EOF

# 附件：有没有生成了却没人引用的图，或者引用了不存在的图
python3 - <<'EOF'
import os, re
strip_code = lambda s: re.sub(r'`[^`\n]*`', '', re.sub(r'```.*?```', '', s, flags=re.S))
used = set()
for r, ds, fs in os.walk("."):
    ds[:] = [d for d in ds if not d.startswith(".") and d != "_附件"]
    for f in fs:
        if f.endswith(".md"):
            body = strip_code(open(os.path.join(r, f), encoding="utf-8").read())
            used |= {m.split("|")[0] for m in re.findall(r'!\[\[([^\]]+)\]\]', body)}
have = {f for f in os.listdir("_附件") if f.endswith((".md", ".svg"))}
print("未被引用的图:", sorted(have - used) or "无")
print("引用了不存在的图:", sorted(used - have) or "无")
EOF

# 无时间戳的现状断言
# 「目前/当前/现在 + 最/主流」的各种组合都要盖住——只写 现在主流 会漏掉 目前主流。
grep -rn --include='*.md' --exclude=AGENTS.md --exclude=00-总索引.md --exclude-dir=_附件 \
  -E '(目前|当前|现在|眼下|时下)(工程上|的)?(最|主流|用得最多)|最新的模型|如今最|已经成为主流|事实标准' .

# 参考段是不是还停在裸列表（约定要求四列时间线表）
grep -rlz --include='*.md' -P '## 参考\n(?!\n*\|)' . | tr '\0' '\n' | grep -v _模板

# json / jsonl 代码块：能不能解析，以及有没有挤成一行
# 规则很硬：标了 ```json 就必须是合法 JSON。演示「截断的输出」「好坏对照」这类
# 本来就不合法的东西，用 ```text，别用 ```json 骗自己。
python3 - <<'EOF'
import os, re, json
bad = []
for r, ds, fs in os.walk("."):
    ds[:] = [d for d in ds if not d.startswith(".")]
    for f in fs:
        if not f.endswith(".md"): continue
        p = os.path.join(r, f); src = open(p, encoding="utf-8").read()
        for m in re.finditer(r'```json\n(.*?)```', src, re.S):
            body = m.group(1).rstrip("\n")
            try:
                obj = json.loads(body)
            except Exception as e:
                bad.append((p, "解析失败", str(e)[:60])); continue
            # 挤成一行的：键多于行数，说明是手工折行或压成一行
            if isinstance(obj, dict) and len(obj) >= 3 and len(body.split("\n")) < len(obj):
                bad.append((p, "没展开", f"{len(obj)} 个键挤在 {len(body.splitlines())} 行"))
        for m in re.finditer(r'```jsonl\n(.*?)```', src, re.S):
            for i, line in enumerate(m.group(1).strip().split("\n"), 1):
                if not line.strip(): continue
                try: json.loads(line)
                except Exception as e: bad.append((p, f"jsonl 第 {i} 行", str(e)[:60]))
print("json 块问题:", "无" if not bad else "")
for p, k, d in bad: print(f"  [{k}] {p}\n      {d}")
EOF
```

还要过一遍 [00-总索引](00-总索引.md) 里「按读者的视野写」那三条自检，尤其是搜 `这篇` `本文` `这个库` `后面会讲`。

## 别做的事

- **别改目录编号。** 编号即学习顺序（01→19 是依赖关系）。改编号要连带改总索引的路线表、目录边界表、「全部笔记」小标题和 README，代价很大。
- **别把「这个库有几个目录」写进正文。** 读者只有这一页。
- **别新建目录**放不进现有分类的零散概念——前置概念（RNN、感受野这类）用 `> [!info] X 是什么` 就地解释。
- **别提交 `.obsidian/plugins/*/main.js`**，`.gitignore` 已排除；插件的 `data.json` 要留。
- **别公开 `_roadmap.html`**，外部来源、授权不明，已在 `.gitignore` 里。

## 目录布局

```
00-总索引.md            入口，含学习路线、目录边界、写作约定
00-主线项目：….md        贯穿全部主题的项目
01-…19-                 19 个主题目录，按学习顺序编号，每篇七段骨架
  90-/91-               里程碑笔记，各阶段的交付物
_工具/mkdraw.py         Excalidraw 生成器
_练习/                  里程碑的起步脚本（留空待填 + 自带裁判）
_附件/                  绘图文件（.excalidraw.md，另有手写的 .svg）
_模板/                  Templater 模板
```
