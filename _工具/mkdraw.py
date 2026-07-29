#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Obsidian Excalidraw 绘图（.excalidraw.md，插件原生 parsed 格式）。

为什么有这个文件：笔记约定「多以图的形式解释概念」。手摆坐标写一张图要一百多行，
那个成本下没人画得动。这里把重复的部分收掉，一张图剩十几行声明。

用法：

    from mkdraw import Draw

    d = Draw()
    a = d.box("RMSNorm", 80, 68, w=240)
    b = d.circle("⊕", 200, 290)
    d.arrow_between(a, b)
    d.save("我的图")            # 写到 ../_附件/我的图.excalidraw.md

坐标系：x 向右、y 向下，单位是像素。画布不用预先定尺寸，嵌入时按内容裁剪。
"""

import json
import os

VAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(VAULT, "_附件")

# 调色板。改这里就能全库换色，别在单张图里写死颜色。
INK = "#1e1e1e"
PALETTE = {
    "default": ("#1971c2", "#e7f5ff"),   # 蓝：普通步骤、模块
    "accent":  ("#f08c00", "#fff9db"),   # 橙：汇合点、关键节点
    "warn":    ("#e03131", "#ffe3e3"),   # 红：错误路径、代价
    "muted":   ("#5c7cfa", "#f1f3f5"),   # 灰蓝：背景、次要
    "ok":      ("#2f9e44", "#ebfbee"),   # 绿：产出、成功
}
DASH_COLOR = "#e03131"


def _textw(s, size):
    """估算文本宽度。CJK 按一个字宽，拉丁按 0.55。"""
    w = 0.0
    for ch in s:
        w += 1.0 if ord(ch) > 0x2E7F else 0.55
    return w * size


class Draw:
    def __init__(self, font=2, roughness=1):
        # font: 1=手写体(无中文) 2=普通 3=等宽。中文用 2。
        self.font = font
        self.roughness = roughness
        self.els = []
        self.texts = []      # (id, 文本) 供 Text Elements 段
        self._n = 0

    # ---------- 内部 ----------

    def _id(self, pre):
        self._n += 1
        return "%s%03d" % (pre, self._n)

    def _base(self, eid, typ, x, y, w, h, **kw):
        e = {
            "id": eid, "type": typ,
            "x": round(x), "y": round(y), "width": round(w), "height": round(h),
            "angle": 0, "strokeColor": INK, "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
            "roughness": self.roughness, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": None,
            "seed": 1000 + self._n * 7, "version": 10, "versionNonce": 3000 + self._n * 11,
            "isDeleted": False, "boundElements": [], "updated": 1,
            "link": None, "locked": False,
        }
        e.update(kw)
        self.els.append(e)
        return e

    def _label(self, s, cx, cy, color=INK, size=18, group=None):
        """在 (cx, cy) 居中放一行文字。多行用 \n 分隔，自动逐行排。"""
        lines = s.split("\n")
        lh = size * 1.35
        top = cy - lh * len(lines) / 2
        for i, line in enumerate(lines):
            eid = self._id("t")
            self.texts.append((eid, line))
            w = _textw(line, size)
            self._base(eid, "text", cx - w / 2, top + i * lh, w, size * 1.25,
                       strokeColor=color, groupIds=[group] if group else [],
                       fontSize=size, fontFamily=self.font, text=line,
                       textAlign="center", verticalAlign="top", containerId=None,
                       originalText=line, lineHeight=1.25, autoResize=True,
                       baseline=int(size * 0.85))

    # ---------- 图元 ----------

    def box(self, label, x, y, w=220, h=52, tone="default", size=18):
        """左上角在 (x, y) 的圆角矩形，文字居中。返回可供连线的形状描述。"""
        stroke, fill = PALETTE[tone]
        g = self._id("g")
        self._base(self._id("b"), "rectangle", x, y, w, h,
                   strokeColor=stroke, backgroundColor=fill,
                   roundness={"type": 3}, groupIds=[g])
        self._label(label, x + w / 2, y + h / 2, color=INK, size=size, group=g)
        return {"x": x, "y": y, "w": w, "h": h, "cx": x + w / 2, "cy": y + h / 2}

    def circle(self, label, cx, cy, r=22, tone="accent", size=18):
        """圆心在 (cx, cy) 的圆，用于汇合点、编号。"""
        stroke, fill = PALETTE[tone]
        g = self._id("g")
        self._base(self._id("c"), "ellipse", cx - r, cy - r, r * 2, r * 2,
                   strokeColor=stroke, backgroundColor=fill, groupIds=[g])
        self._label(label, cx, cy, color=stroke, size=size, group=g)
        return {"x": cx - r, "y": cy - r, "w": r * 2, "h": r * 2, "cx": cx, "cy": cy}

    def rect(self, x, y, w, h, tone="default", fill=True, round_=False):
        """不带文字的矩形。画网格、色块、分区用。"""
        stroke, bg = PALETTE[tone]
        self._base(self._id("r"), "rectangle", x, y, w, h,
                   strokeColor=stroke, backgroundColor=bg if fill else "transparent",
                   roundness={"type": 3} if round_ else None)
        return {"x": x, "y": y, "w": w, "h": h, "cx": x + w / 2, "cy": y + h / 2}

    def line(self, x, y, pts, dashed=False, color=None):
        """没有箭头的线。画分隔、辅助线、跨度标记用。"""
        allp = [(0, 0)] + list(pts)
        w = max(p[0] for p in allp) - min(p[0] for p in allp)
        h = max(p[1] for p in allp) - min(p[1] for p in allp)
        self._base(self._id("l"), "line", x, y, w, h,
                   strokeColor=color or (DASH_COLOR if dashed else INK),
                   strokeStyle="dashed" if dashed else "solid",
                   roundness={"type": 2}, points=[[p[0], p[1]] for p in allp],
                   lastCommittedPoint=None, startBinding=None, endBinding=None,
                   startArrowhead=None, endArrowhead=None, elbowed=False)

    def hop(self, x1, x2, y, rise=34, color=None, dashed=False, label=None, size=14):
        """从 x1 到 x2 画一条向上拱起的弧线箭头，用于表示「跨过中间直接到达」。"""
        span = x2 - x1
        self.arrow(x1, y, [(span * 0.25, -rise), (span * 0.75, -rise), (span, 0)],
                   dashed=dashed, label=None)
        if color:
            self.els[-1]["strokeColor"] = color
        if label:
            self._label(label, x1 + span / 2, y - rise - 14,
                        color=color or INK, size=size)

    def text(self, s, cx, cy, color=INK, size=18):
        """不带框的裸文字，用于数据、旁注。"""
        self._label(s, cx, cy, color=color, size=size)
        w = max(_textw(l, size) for l in s.split("\n"))
        h = size * 1.35 * len(s.split("\n"))
        return {"x": cx - w / 2, "y": cy - h / 2, "w": w, "h": h, "cx": cx, "cy": cy}

    def arrow(self, x, y, pts, dashed=False, label=None, label_at=None, size=15):
        """从 (x, y) 出发，pts 是相对位移的折点列表 [(dx,dy), ...]。"""
        allp = [(0, 0)] + list(pts)
        w = max(p[0] for p in allp) - min(p[0] for p in allp)
        h = max(p[1] for p in allp) - min(p[1] for p in allp)
        self._base(self._id("a"), "arrow", x, y, w, h,
                   strokeColor=DASH_COLOR if dashed else INK,
                   strokeStyle="dashed" if dashed else "solid",
                   roundness={"type": 2}, points=[[p[0], p[1]] for p in allp],
                   lastCommittedPoint=None, startBinding=None, endBinding=None,
                   startArrowhead=None, endArrowhead="arrow", elbowed=False)
        if label:
            lx, ly = label_at if label_at else (x + w / 2, y + h / 2)
            self._label(label, lx, ly, color=DASH_COLOR if dashed else INK, size=size)

    def arrow_between(self, a, b, gap=4, label=None):
        """两个形状之间画直箭头，自动判断上下还是左右，并留出间隙。"""
        if abs(a["cx"] - b["cx"]) < abs(a["cy"] - b["cy"]):        # 竖直
            if b["cy"] > a["cy"]:
                x, y, ey = a["cx"], a["y"] + a["h"] + gap, b["y"] - gap
            else:
                x, y, ey = a["cx"], a["y"] - gap, b["y"] + b["h"] + gap
            self.arrow(x, y, [(0, ey - y)], label=label,
                       label_at=(x + 26, (y + ey) / 2) if label else None)
        else:                                                       # 水平
            if b["cx"] > a["cx"]:
                x, y, ex = a["x"] + a["w"] + gap, a["cy"], b["x"] - gap
            else:
                x, y, ex = a["x"] - gap, a["cy"], b["x"] + b["w"] + gap
            self.arrow(x, y, [(ex - x, 0)], label=label,
                       label_at=((x + ex) / 2, y - 16) if label else None)

    # ---------- 布局助手 ----------

    def chain_down(self, labels, cx=200, top=0, w=220, h=52, gap=44,
                   tone="default", size=18, arrows=True):
        """竖着串一列方框，相邻之间自动连箭头。返回形状列表。"""
        shapes, y = [], top
        for lb in labels:
            s = self.box(lb, cx - w / 2, y, w=w, h=h, tone=tone, size=size)
            if arrows and shapes:
                self.arrow_between(shapes[-1], s)
            shapes.append(s)
            y += h + gap
        return shapes

    def chain_right(self, labels, left=0, cy=0, w=170, h=52, gap=46,
                    tone="default", size=17, arrows=True):
        """横着串一排方框。"""
        shapes, x = [], left
        for lb in labels:
            s = self.box(lb, x, cy - h / 2, w=w, h=h, tone=tone, size=size)
            if arrows and shapes:
                self.arrow_between(shapes[-1], s)
            shapes.append(s)
            x += w + gap
        return shapes

    # ---------- 输出 ----------

    def save(self, name, outdir=OUTDIR):
        os.makedirs(outdir, exist_ok=True)
        drawing = {
            "type": "excalidraw", "version": 2,
            "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin",
            "elements": self.els,
            "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {},
        }
        te = "\n\n".join("%s ^%s" % (s, i) for i, s in self.texts)
        md = (
            "---\nexcalidraw-plugin: parsed\ntags:\n  - excalidraw\n---\n"
            "==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠==\n\n"
            "# Excalidraw Data\n\n## Text Elements\n%s\n\n%%%%\n## Drawing\n```json\n%s\n```\n%%%%"
            % (te, json.dumps(drawing, ensure_ascii=False, indent=2))
        )
        path = os.path.join(outdir, name + ".excalidraw.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        xs = [e["x"] for e in self.els]
        w = max(e["x"] + e["width"] for e in self.els) - min(xs)
        h = (max(e["y"] + e["height"] for e in self.els)
             - min(e["y"] for e in self.els))
        print("写入 %s  （%d 个元素，画布 %d×%d）" % (path, len(self.els), w, h))
        print("嵌入：![[%s.excalidraw.md|%d]]" % (name, min(int(w) + 40, 700)))
        return path
