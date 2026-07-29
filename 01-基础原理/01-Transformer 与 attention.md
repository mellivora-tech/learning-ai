---
tags:
  - ai工程/基础原理
stage: 0
status: todo
aliases:
  - attention
  - self-attention
---
Attention 把每个 token 的表示，重算成「它和序列里所有 token 的相关度」对那些 token 内容的加权和；Transformer 就是把这件事堆很多层，中间夹上前馈网络和残差。

举个例子。「苹果」在下面两句话里是同一个 token，查 embedding 表拿到的初始向量**一模一样**：

> A：我把**苹果**削了皮
> B：**苹果**发布了新手机

可读完整句，你脑子里这两个「苹果」显然不是一回事。attention 做的就是这件事：让「苹果」所在的位置去看句中其他所有词，按相关度分配权重，再把那些词的内容按权重取过来，掺进自己的表示里。

| 句子  | 「苹果」这个位置把注意力主要给了谁       |
| --- | ----------------------- |
| A   | 削 0.35、自己 0.30、皮 0.25   |
| B   | 发布 0.34、手机 0.30、自己 0.28 |

数字是示意，只表达相对大小。A 句的权重压在「削」「皮」上，输出向量因此偏向水果；B 句压在「发布」「手机」上，输出偏向公司。**同一个输入向量、同一组权重矩阵，出来了两个不同的结果**——差别全部来自上下文。这就是「重算成加权和」的字面意思：一个 token 的含义不由它自己决定，由它和上下文的关系决定。

再看一组，更能看出权重落在哪：

> 那只**猫**追那只**老鼠**，因为**它**饿了。
> 那只**猫**追那只**老鼠**，因为**它**跑得慢。

「它」指谁？第一句是猫，第二句是老鼠。模型里并没有一个专门的指代消解模块——靠的就是「它」这个位置在算 attention 时，把权重更多地给了「猫」还是「老鼠」。

至于「堆很多层」：一层 attention 只做一轮这样的信息汇聚。第二层拿到的已经是被上下文改写过的表示，在此之上再汇聚一次，能接住更绕的关系。几十层叠下来，最后一层每个位置的向量里已经融进了对全句的多轮解读。

## 原理

架构决定信息怎么流动，但它本身不含任何知识——能力在权重里，吞吐和延迟在推理服务里，三者的分工见 [[00-一个模型到底是什么]]。所以「换了个 attention 变体所以更强了」这类说法，得先分清在说哪一层。

### 前世：attention 本来是 RNN 的补丁

> [!info] RNN 是什么
> Recurrent Neural Network，循环神经网络，Transformer 之前处理序列的主流结构。它维护一个固定大小的隐状态向量 $h$，从左到右逐个读 token，每步把当前输入和上一步的隐状态送进**同一组权重**：$h_t = f(W_h h_{t-1} + W_x x_t)$。
> 「循环」指的就是这组权重在每个时间步被反复复用，所以它能吃任意长度的序列而参数量不变。$h_t$ 是它对「读过的一切」的唯一记忆。
> 打个比方：RNN 是一边读书一边往**一张便签**上记要点，读到第 500 页想起第 3 页，只能靠这张便签；attention 是把整本书摊开，任意两页直接对看。那张便签就是固定大小的 $h$。
> [LSTM](https://direct.mit.edu/neco/article/9/8/1735/6109)（Hochreiter 与 Schmidhuber，1997）和 [GRU](https://arxiv.org/abs/1406.1078)（Cho 等，2014）是 RNN 的改良版，用门控让信息能跨时间步直通而不必每步重写。它们是 2014–2017 年 RNN 实际可用的原因，但只缓解了梯度问题，没动串行这一条。

2014 年的 [seq2seq](https://arxiv.org/abs/1409.3215) 是这样干的：一个 RNN 把整句源文压成一个固定长度的向量，另一个 RNN 从这个向量生成译文。句子一长，信息就挤不进那个向量。作者是 Google 的 Ilya Sutskever、Oriol Vinyals、Quoc Le——Sutskever 后来是 OpenAI 的联合创始人兼首席科学家。

同年 [Bahdanau 等人](https://arxiv.org/abs/1409.0473) 给它打了个补丁——让 decoder 每一步回头看 encoder 的**全部**隐状态，按相关度加权取用。这就是 attention。它比 Transformer 早三年出现，当时只是 RNN 的一个附件，不是主角。三位作者是 Dzmitry Bahdanau、Kyunghyun Cho、Yoshua Bengio；Cho 也是 GRU 的作者之一，Bengio 是深度学习三巨头之一、2018 年图灵奖得主。

值得一提的是分歧从这里就埋下了：Bahdanau 那版用的是**加性注意力**，拿一个小前馈网络给 query 和 key 打分。一年后 [Luong 等人](https://arxiv.org/abs/1508.04025) 改成点积打分，更快也更容易矩阵化。Transformer 采用的「缩放点积注意力」是后一支的延续——下面那个 $QK^\top$ 的形式就是从这儿来的，而不是从 Bahdanau 那版。

但 RNN 的根本问题没被解决，而且是两条：

1. **串行**。算 $h_t$ 必须先有 $h_{t-1}$，这是结构性的硬依赖。1000 个 token 就要走 1000 步，序列维度上无法并行，GPU 喂不饱。
2. **梯度沿时间衰减**。从第 $n$ 步的 loss 回传到第 1 步，梯度要连乘 $n$ 次雅可比矩阵；乘数小于 1 就指数消失，大于 1 就爆炸。长程依赖因此学不到。

另一条路线是 CNN：[ConvS2S](https://arxiv.org/abs/1705.03122)（Facebook AI Research，2017）和 [ByteNet](https://arxiv.org/abs/1610.10099)（DeepMind，2016）。它们用卷积换来了并行，绕开了第 1 条；可要让相距很远的两个位置发生联系，需要的层数随距离增长——第 2 条换了个形式还在。

> [!info] CNN 是什么
> Convolutional Neural Network，卷积神经网络，最初为图像设计。核心是一个固定宽度 $k$ 的窗口（kernel）在输入上滑动，每次只看窗口内的 $k$ 个位置，用**同一组权重**加权求和得出一个输出值，滑完整个序列就是一层。「卷积」指的就是同一个 kernel 在所有位置复用。
> 和 RNN 的关键区别是它**无状态**：每个位置的输出只取决于自己窗口内的输入，位置之间没有依赖，所以全部位置可以同时算——这正是它比 RNN 快的原因，也是当年提出 ConvS2S、ByteNet 的动机。
> 代价是视野。一层只看得见 $k$ 个位置，想连接远处只能堆层数：普通卷积要 $O(n/k)$ 层，膨胀卷积（ByteNet 用的，卷积核带间隔）能压到 $O(\log_k n)$ 层。视野是金字塔式一层层攒出来的，不是一步到位。

### 2017 年的赌注：把 RNN 整个拿掉

原始论文的标题就是结论——[Attention Is All You Need](https://arxiv.org/abs/1706.03762)，Google Brain 与 Google Research 的八人团队，2017 年。其中 Noam Shazeer 值得单独记一下：这篇往后的 [MQA](https://arxiv.org/abs/1911.02150) 和 [SwiGLU](https://arxiv.org/abs/2002.05202) 也都出自他手，本篇参考里他一个人占三条。

三条路线的差别可以压成一句话：**RNN 靠一个隐状态把序列顺序串起来，CNN 靠堆层数把视野撑开，self-attention 一层就把所有位置直连。** 画出来是这样：

![[信息从头传到尾要几步.excalidraw.md|700]]

去掉循环结构之后，代价和收益都很极端。原文 Table 1 把这张图量化成了三列：

| | 每层计算量 | 串行步数 | 任意两位置的最大路径长度 |
| --- | --- | --- | --- |
| 循环（RNN） | $O(n d^2)$ | $O(n)$ | $O(n)$ |
| 卷积（CNN） | $O(k n d^2)$ | $O(1)$ | $O(\log_k n)$ |
| 自注意力 | $O(n^2 d)$ | $O(1)$ | $O(1)$ |

看最后一列：self-attention 里任意两个 token 之间只隔一层，信息不必沿序列一步步传递，长程依赖不再天然衰减。看中间一列：串行步数降为常数，训练可以在序列维度上完全并行。

代价在第一列——计算量对 $n$ 从线性变成平方。这笔买卖在 GPU 上非常划算：$O(n^2)$ 是一次能并行的大矩阵乘法，而 $O(n)$ 的串行依赖再便宜也填不满一张卡。**Transformer 真正的贡献不是「更聪明」，是把模型能力的问题转换成了算力投入的问题**——这才是后来 scaling law 能成立的前提。

那个平方项同时也是今天所有长上下文难题的源头，往下的计算量分解会再回到它。

### 今生：三条分支收敛成一条

原始 Transformer 是为机器翻译设计的 encoder-decoder。此后分出三条路：

1. **只留 encoder**——[BERT](https://arxiv.org/abs/1810.04805)（Devlin 等，Google，2018），双向看全文，擅长理解类任务，用法是预训练加微调。
2. **只留 decoder**——[GPT](https://cdn.openai.com/research-covers/language-unsupervised/language_understanding_paper.pdf) 系（Radford 等，OpenAI，2018 起），单向 causal，只做一件事：预测下一个 token。
3. **保留 encoder-decoder**——[T5](https://arxiv.org/abs/1910.10683)（Raffel 等，Google，2019），把所有任务统一成 text-to-text。

2020 年之后基本收敛到 decoder-only。原因不是它在每个任务上都最强，而是：next-token prediction 一个目标就能同时覆盖理解和生成，不必为每类任务换预测头；训练与推理栈都最简单；而且它最适合规模化。今天说「大模型」，默认指的就是 decoder-only。

所以下面讲 causal mask、KV cache、prefill/decode，默认说的都是 decoder-only。

### 八年里真正变过的东西

| | 原始 Transformer（2017） | 现在（Llama 系） |
| --- | --- | --- |
| 整体结构 | encoder-decoder | decoder-only |
| 归一化位置 | post-norm | pre-norm |
| 归一化方式 | LayerNorm | RMSNorm |
| FFN | ReLU 两层 | SwiGLU 门控三矩阵 |
| 位置编码 | 正弦绝对位置 | RoPE |
| KV head | MHA | GQA / MQA |

真正值得注意的是这张表里**没有**的东西：缩放点积注意力的形式、position-wise FFN 的存在、残差连接——这三件核心组件八年没有实质变化。变动全集中在稳定性、效率和位置表示这些外围。所以下面讲原理时，讲的是不会过时的那部分。

### Transformer 整体长什么样

前面讲的都是 attention。但 attention 只是其中一个零件，先把整台机器看一遍。以 decoder-only 为例，从一段文本到下一个 token 的完整通路：

1. **Tokenize**——文本切成 token id 序列，见 [[03-Tokenization]]。
2. **Embedding 查表**——一张 `[vocab_size, d]` 的表，每个 token id 查出一个 $d$ 维向量。这是 token 唯一的、与上下文无关的初始表示。开头「苹果」那个例子里说的「两句拿到的向量一模一样」，指的就是这一步的输出，见 [[06-Embedding 与向量空间]]。
3. **注入位置信息**——attention 看不见顺序，顺序在这里加进去。现代做法是 RoPE，作用在每一层的 Q 和 K 上，见 [[07-位置编码与长度外推]]。
4. **N 个结构相同的 block**——每个 block 是「attention 子层 + FFN 子层」，各自配残差和归一化。$N$ 通常几十：Llama 3 8B 是 32 层，70B 是 80 层。注意**每层的参数是独立的，不共享**——这一点和 RNN 反复复用同一组权重正好相反。
5. **末尾再归一化一次**。
6. **lm_head（unembedding）**——一个 `[d, vocab_size]` 的矩阵，把每个位置的 $d$ 维向量映回词表大小的一串分数，这串分数叫 logits。
7. **Softmax 加采样**——logits 变成概率分布，按采样参数挑出一个 token，见 [[04-采样参数]] 和 [[05-logprobs 与置信度]]。

训练和推理的差别只在第 6、7 步怎么用：训练时对**每个位置**都算 logits，目标是让位置 $i$ 的输出对准真实的第 $i+1$ 个 token（交叉熵）；推理时只取最后一个位置。

这条通路上有三件事值得单独记住：

**形状全程不变。** 从第 2 步到第 5 步，每个位置始终是一个 $d$ 维向量，`[B, T, d]` 这个形状穿过全部 $N$ 层。block 做的是**原地改写**这些向量，不是逐层压缩或放大。所以「第 10 层的第 3 个位置」和「第 40 层的第 3 个位置」是同一个槽位的不同版本。

**同一组权重作用于所有位置。** block 里的矩阵都不带位置下标，第 1 个 token 和第 1000 个 token 过的是同一套权重。所以序列长度 $T$ 可以变而参数量不变——这一点和 RNN、CNN 一样，都是权重共享，只是共享的方式不同。

**token 之间唯一的交流渠道是 attention。** FFN 和归一化都是**逐位置独立**的，它们只看当前位置的向量，完全不看别的 token。整个模型里跨位置的信息流动只发生在 attention 这一处。这句话的分量比它看起来重：任何需要跨 token 的能力——指代消解、长程依赖、检索式回忆——都必须经由 attention 才能实现，没有别的通道。

### 一次 attention 在算什么

每个 token 从自己的表示投影出三个东西：query（我要找什么）、key（我能提供什么）、value（我实际交出的内容）。用所有 query 和所有 key 两两点积，得到一张 $T \times T$ 的相关度矩阵，归一化成权重后去加权 value。

盯住一个位置看，就是开头那个「苹果」例子的内部：

![[一次 attention 在算什么.excalidraw.md|700]]

写成公式：

$$
\text{Attention}(Q, K, V) = \text{softmax}\!\left(\frac{QK^\top}{\sqrt{d_k}}\right)V
$$

形状是理解这件事最快的路径：

| 张量          | 形状              | 产生自                                 |
| ----------- | --------------- | ----------------------------------- |
| `x`         | `[B, T, d]`     | 上一层输出                               |
| `Q` `K` `V` | `[B, h, T, dh]` | `x @ Wq/Wk/Wv` 后拆成 `h` 个 head       |
| `scores`    | `[B, h, T, T]`  | `Q @ K.transpose(-1,-2) / sqrt(dh)` |
| `weights`   | `[B, h, T, T]`  | mask 后 softmax                      |
| `out`       | `[B, h, T, dh]` | `weights @ V`                       |
| 回到 `x`      | `[B, T, d]`     | concat 各 head 后 `@ Wo`              |

其中 `d = h × dh`，所以 multi-head 不增加参数量，只是把同一个 `d` 维空间切成 `h` 个子空间各算一遍。

### 为什么要除 $\sqrt{d_k}$

若 query 和 key 的各分量近似独立、均值 0 方差 1，它们点积的方差就是 $d_k$。维度越大，点积的分布越宽，softmax 越接近 one-hot——梯度随之趋近 0，训练停滞。除以 $\sqrt{d_k}$ 把方差拉回 1 附近。这是个**梯度问题**，不是数值美观问题。

### Causal mask

decoder-only 模型里，位置 $i$ 只允许看 $\le i$ 的位置。实现就是把 `scores` 的上三角填成 $-\infty$，softmax 后自然变成 0：

![[causal mask 的上三角.excalidraw.md|639]]

这个 mask 带来一条关键性质：一次前向就能同时拿到 $T$ 个位置各自的预测，训练可以完全并行。而生成时下一个 token 依赖上一个的输出，只能一步一步来。这就是 [[01-Prefill vs Decode]] 里两个阶段性质截然不同的根源。

### Block 是什么

先把术语对齐：**block、层（layer）、transformer layer、decoder layer 说的是同一个东西**。前面讲「Llama 3 8B 有 32 层」，指的就是 32 个 block 串成一条链，不是 32 次矩阵乘法。原论文管这个重复单元叫 layer，管它内部的 attention 和 FFN 叫 sublayer（子层）；社区后来更常用 block 指前者。这个歧义绊过很多人——看到「层」先确认说的是哪一级。

三句话概括它：

**它是重复单元。** 整个模型的主体就是同一个结构复制 $N$ 份串起来。结构完全一样，参数各自独立。所以描述一个模型的架构，只需要说清一个 block 长什么样，再给一个 $N$。

**它进出形状不变。** 进来 `[B, T, d]`，出去还是 `[B, T, d]`。这不是巧合而是设计约束：形状不变才能任意串接多少层都行，残差也才能直接相加、不需要额外投影去对齐维度。

**它做的是原地改写，不是逐层提取。** 图像 CNN 那种「浅层看边缘、深层看物体，分辨率一路下降」的金字塔在这里不存在。Transformer 每一层都在同一组槽位上工作，把每个位置的向量重写得更懂上下文一点。第 40 层的第 3 个位置，仍然是第 3 个 token 那个槽位，只是版本更新了。

一个 block 内部是**一读一写**：attention 子层跨位置搬信息（读全场），FFN 子层逐位置加工（自己消化）。32 层，就是把「读一遍全场、自己消化一下」这件事重复 32 轮。

> [!tip] residual stream：一个更好用的视角
> 把贯穿始终的那条 `[B, T, d]` 想成一条主干道，叫 residual stream。每个子层不是「接管」这条干道，而是从上面**读**一份、算出点东西、再**加**回去，写法就是 $x' = x + \text{Sublayer}(\text{Norm}(x))$。
> 因为是加不是替换，干道上的信息逐层累积——早期层写进去的东西，几十层之后仍然读得到。这个视角下残差就不再是「防梯度消失的训练技巧」，而是架构的骨架：真正的主体是那条一直在的干道，attention 和 FFN 只是挂在旁边、往里写东西的模块。
> 下面的图为了跟常见画法一致，把子层画在主线上、残差画成旁路。按 residual stream 的理解其实反过来更贴切：干道是直的，子层挂在旁边。两种画法对应的是同一个式子，看着顺手就行。

### 一个 block 的数据流

现代 decoder-only（Llama 系）用 pre-norm，归一化放在子层前面：

![[Transformer block 数据流.excalidraw.md|520]]

实线是主通路，数据依次穿过归一化和子层；两条虚线是残差通路，跳过子层直接汇到 ⊕，⊕ 是逐元素相加。图上每条边的形状都是 `[B, T, d]`——子层进出不改形状，残差才能直接相加，不需要任何投影去对齐维度。

分叉点的位置就是 pre-norm 的定义：第一条残差取的是 `x`，在 RMSNorm **之前**；第二条取的是第一次相加的结果，不是第二个 RMSNorm 的输出。于是从 `x'` 回到 `x` 存在一条只经过加法的通路，梯度沿它流动时不被归一化的缩放改写。这是能堆到几十上百层的前提。

post-norm 是另一种接法：`x' = Norm(x + Sublayer(x))`，残差要穿过归一化，那条纯加法通路就没有了。它对学习率敏感得多，原始 Transformer 靠 warmup 才稳得住；pre-norm 对 warmup 的依赖弱得多，代价是每个子层的输入没有被重新归一化过，深层的残差流幅度会一路累积，所以 Llama 系在整个 block 栈的末尾还要补一次 RMSNorm。

### FFN 和归一化各自在干什么

一个 block 里除了 attention 还有两样东西，都是逐位置独立的。

**FFN（前馈网络）负责加工。** 它是个每个位置各自过一遍的小网络：先把 $d$ 维升到 $d_{ff}$（经典设置是 $4d$），过一个非线性激活，再降回 $d$：

$$
\text{FFN}(x) = W_2 \, \sigma(W_1 x)
$$

为什么必须有它：attention 的输出是 value 的加权和。权重虽然由输入经 softmax 算出，整体并非严格线性，但它**对 value 的组合方式是线性的**——它只会重新混合已有的信息，不会对单个位置的表示做复杂的逐点变换。FFN 补的正是这一块：把 attention 搬过来的信息真正加工一遍。

一句话分工：**attention 决定「从哪儿取信息」，FFN 决定「取来之后怎么算」。**

它还占掉整个 block 约三分之二的参数（下面就算）。这么大的容量放在这里，一种有影响力的解释是它承担了大量事实性知识的存储——把 $d_{ff}$ 那个宽层看成一组 key-value 记忆槽，见 [Geva 等人的工作](https://arxiv.org/abs/2012.14913)。现代模型把激活换成了 SwiGLU（三个矩阵，其中一路当门控），效果更好，但角色没变。

**归一化负责稳住尺度。** 向量逐层被改写，幅度会一路累积或衰减，几十层之后数值就跑飞了。归一化在每个位置上把向量重新缩放到稳定的量级。LayerNorm 要先减均值再除标准差；RMSNorm 省掉减均值这一步，只除以平方均值的根号，少一遍统计量、快一些，效果相当——这就是「变过的东西」表里那一行。

注意它也是逐位置独立的：位置 $i$ 的归一化只用位置 $i$ 自己那 $d$ 个数，不涉及其他 token。**残差**则更简单，就是逐元素相加，作用是留出那条只经过加法的梯度通路，前面 block 数据流那节已经讲过。

### 参数量和计算量落在哪

一个 block 里，attention 的四个投影矩阵合计约 $4d^2$；FFN 无论是经典的 `d_ff = 4d` 两矩阵，还是 SwiGLU 的三矩阵配 `d_ff ≈ 8d/3`，都约 $8d^2$。**参数量约三分之二在 FFN，不在 attention。**

计算量的分布不一样，而且随序列长度变化：

| 部分 | 计算量 | T 从 8k 到 128k |
| --- | --- | --- |
| $QK^\top$ 与 $\text{weights} \times V$ | $O(T^2 d)$ | ×256 |
| QKVO 投影 + FFN | $O(T d^2)$ | ×16 |
| KV cache 显存 | $O(T)$ | ×16 |

`T` 远小于 `d` 时 FFN 主导，`T` 长到可比时 attention 的平方项接管。所谓「长上下文很贵」，贵的是这三行里增长速度完全不同的三件事，谈的时候要分开说。

### K 和 V 可以缓存，Q 不行

生成第 $t$ 步时，只有一个新 query（形状 `[B, h, 1, dh]`），但它要和历史全部 $t$ 个 key 做点积。而这些 key、value 只是历史 token 的函数，不随新 query 改变——重算一遍是纯浪费。这就是 [[02-KV cache 为什么存在]]。

顺着这条线还能推出 GQA / MQA 为什么有效：让多个 query head 共享同一组 kv head，KV cache 直接按共享倍数缩小，而 query 的表达力基本不受影响。

### Attention 本身看不见顺序

单看 attention 算子，它是**置换等变**的：把输入 token 打乱顺序，输出只会跟着同样打乱，没有任何额外信息告诉它谁在前面。顺序完全靠外部注入，见 [[07-位置编码与长度外推]]。

## 动手做

- [ ] 用 numpy 或 torch 写 20 行以内的 single-head causal attention，和 PyTorch 内置实现对齐数值
- [ ] 去掉 $\sqrt{d_k}$，把 `dh` 扫到 32 / 512 / 2048，记录 softmax 权重的最大值和熵，看分布怎么塌成 one-hot
- [ ] 去掉 causal mask 再训一遍，确认 loss 会假性下降（模型看见了未来 token）
- [ ] 扫 `T = 128 / 1k / 8k / 32k`，分别给 attention 段和 FFN 段计时，找出耗时占比翻转的那个 `T`
- [ ] 画某一层某个 head 的 `[T, T]` 权重热力图，找对角线、induction 模式，以及第 0 个 token 上的异常权重
- [ ] 给上面的实现加 KV cache，让第 $t$ 步只算 1 个 query，与全量重算逐 token 比对 → [[90-里程碑：极简 attention + KV cache + logprobs 置信度过滤器]]

第一项的验证脚手架：

```python
import torch
import torch.nn.functional as F

q, k, v = (torch.randn(1, 1, 64, 32) for _ in range(3))
ref = F.scaled_dot_product_attention(q, k, v, is_causal=True)
mine = my_attention(q, k, v)          # 自己写的那 20 行

assert torch.allclose(ref, mine, atol=1e-5), (ref - mine).abs().max()
```

对不上就逐步打印中间张量比形状，八成错在 mask 的方向或 `dh` 用成了 `d`。

## 算学会了

- [ ] 不查资料能从 `[B, T, d]` 推出全部中间张量的形状，包括 `scores` 为什么是 `[B, h, T, T]`
- [ ] 有人说「上下文从 8k 提到 128k」，能当场分开说出：attention 计算量 ×256、FFN ×16、KV cache 显存 ×16
- [ ] 能说出为什么 K、V 可以缓存而 Q 不行
- [ ] 被问「为什么除 $\sqrt{d_k}$」，答的是梯度饱和，不是「为了归一化」
- [ ] 能解释 prefill compute-bound、decode memory-bound 的成因，而不是只背结论

## 坑

**不除 $\sqrt{d_k}$ 是训练不动，不是精度差一点。** softmax 饱和后梯度接近 0，维度越大越严重。这个坑在自己手写实现时最常犯，而且现象是「loss 卡住」，不容易联想到缩放因子。

**位置编码的问题会伪装成推理能力的问题。** 因为 attention 置换等变，顺序信息全靠位置编码。长度外推失效时，表现常常是「模型在长文档上开始胡说」，很容易被误判成模型能力不够，而不是位置编码超出了训练分布。

**参数量的大头和长上下文显存的大头是两件事。** 前者在 FFN，后者在 KV cache。加深加宽影响前者，放长上下文影响后者。容量规划时混为一谈会算错，见 [[03-KV cache 管理与显存测算]]。

> [!warning] Attention sink
> 序列最前面的少数几个 token（尤其第 0 个）会吸走异常大的注意力权重，即使它们语义上完全无关——模型需要一个「什么都不想看时把权重倒进去」的地方。
> 后果是：做滑动窗口或裁剪上下文时，如果把开头这几个 token 一起丢掉，生成质量会明显崩坏。StreamingLLM 的做法是无论窗口怎么滑，永久保留最前面几个 token。

**attention 权重不是「模型在看哪里」的证据。** 拿它做归因解释很容易得出好看但站不住的结论，这一点有专门的论文反驳。要做归因请用真正的归因方法。

**multi-head 不是「每个 head 负责一种语义」。** 这个直觉太干净了。实际上 head 之间高度冗余，相当一部分可以剪掉而几乎不掉点。不要基于「某个 head 管某件事」去设计功能。

## 关联
- [[02-KV cache 为什么存在]]
- [[07-位置编码与长度外推]]
- [[01-Prefill vs Decode]]
- [[03-Tokenization]]

## 参考

前世今生这条线，按时间排：

| 年份 | 工作 | 人 / 机构 | 在本篇的位置 |
| --- | --- | --- | --- |
| 1997 | [LSTM](https://direct.mit.edu/neco/article/9/8/1735/6109) | Hochreiter、Schmidhuber | 门控让 RNN 实际可用 |
| 2014 | [seq2seq](https://arxiv.org/abs/1409.3215) | Sutskever、Vinyals、Le / Google | 固定长度向量瓶颈的来源 |
| 2014 | [GRU](https://arxiv.org/abs/1406.1078) | Cho 等 | LSTM 的简化版 |
| 2014 | [Bahdanau attention](https://arxiv.org/abs/1409.0473) | Bahdanau、Cho、Bengio | attention 的出处，加性打分 |
| 2015 | [Luong attention](https://arxiv.org/abs/1508.04025) | Luong、Pham、Manning / Stanford | 改成点积打分，Transformer 继承的是这一支 |
| 2016 | [ByteNet](https://arxiv.org/abs/1610.10099) | Kalchbrenner 等 / DeepMind | CNN 路线，膨胀卷积 |
| 2017 | [ConvS2S](https://arxiv.org/abs/1705.03122) | Gehring 等 / FAIR | CNN 路线 |
| 2017 | [Attention Is All You Need](https://arxiv.org/abs/1706.03762) | Vaswani 等八人 / Google | Table 1 的三方对比 |
| 2018 | [BERT](https://arxiv.org/abs/1810.04805) | Devlin 等 / Google | encoder-only 分支 |
| 2018 | [GPT](https://cdn.openai.com/research-covers/language-unsupervised/language_understanding_paper.pdf) | Radford 等 / OpenAI | decoder-only 分支 |
| 2019 | [T5](https://arxiv.org/abs/1910.10683) | Raffel 等 / Google | 坚持 encoder-decoder 的一支 |
| 2019 | [RMSNorm](https://arxiv.org/abs/1910.07467) | Zhang、Sennrich | 「变过的东西」表里 norm 一行 |
| 2020 | [SwiGLU](https://arxiv.org/abs/2002.05202) | Shazeer | 同表 FFN 一行 |
| 2020 | [FFN 是 key-value 记忆](https://arxiv.org/abs/2012.14913) | Geva 等 | FFN 存知识那个解释的出处 |

原理与实现：

- [Attention Is All You Need](https://arxiv.org/abs/1706.03762) — 原始论文。三方对比在 Table 1（第 4 节），$\sqrt{d_k}$ 的动机在 3.2.1
- [The Illustrated Transformer](https://jalammar.github.io/illustrated-transformer/) — 形状和数据流的可视化
- [nanoGPT](https://github.com/karpathy/nanoGPT) — 最值得逐行读的最小实现，`model.py` 一个文件
- [Fast Transformer Decoding: One Write-Head is All You Need](https://arxiv.org/abs/1911.02150) — MQA
- [GQA: Training Generalized Multi-Query Transformer Models](https://arxiv.org/abs/2305.13245) — GQA
- [Efficient Streaming Language Models with Attention Sinks](https://arxiv.org/abs/2309.17453) — attention sink
- [Attention is not Explanation](https://arxiv.org/abs/1902.10186) — 为什么权重不能当解释
