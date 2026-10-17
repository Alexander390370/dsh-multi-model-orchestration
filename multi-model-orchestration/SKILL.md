---
name: multi-model-orchestration
description: Orchestrate one task across several models and modalities as Team Lead. Use when a job benefits from different model strengths (long-context reading, code, cheap bulk passes, adversarial review, vision), when the user says "让几个模型一起做 / 多模型 / 交叉验证 / 找一个不同模型唱反调", or when routing work to Kimi / Qwen / GLM / DeepSeek / local Ollama through a workflow. Covers model routing, panel patterns, verified provider failure modes, and the delegation contract. Skip for single-model tasks — one model is faster and cheaper.
metadata:
  version: "2"
  verified_on: "2026-10-17"
  reviewed_by: "kimi-k3, qwen3.8-max, doubao-seed-2-1-pro, claude-opus-5.5"
  tested_dsh_version: "2026-10-14 快照"
---

# 多模型编排（中轴线手册）

我是这条线的中轴：**拆任务 → 按模型长处派活 → 合并 → 自己验证**。
委派出去的东西永远不是最终答案，最终答案由我在工具与证据上落定。

判断标准只有一条：**这个活儿换个模型是不是明显更好？** 不是就别派——单模型更快更省。

## 1. 硬事实：怎么把活派给指定模型

| 工具 | 能否指定模型 | 说明 |
|---|---|---|
| `workflow` 的 `agent(prompt, { provider, model })` | ✅ **逐 agent 覆盖** | 目前唯一能按次指定 provider/model 的委派方式，可混着跑多家的模型 |
| `spawn_teammate` | ❌ **入参没有 model 字段** | 常驻队友只能继承会话默认模型（`agent-default-model`）。别用它做跨模型 |
| 子代理（`subagent` / `subagent_fork`） | ❌ 同上 | 一次性委派，仍继承会话模型 |

所以：**要跨模型，就用 `workflow`**；需要"常驻队友"时接受它与主会话同模型。

> 上面这行结论**只对当前 DSH 版本成立**（见 frontmatter 的 `tested_dsh_version`）。DSH 是活跃开发中的框架，
> 如果哪天 `subagent` 加上了 model 参数，这段就该改写——用之前先看一眼工具签名。

`provider` 名必须与 profile 配置一致（见 §2 表），写错 → agent 静默返回 `null`。

## 2. 模型路由表（**作者环境快照**，截至 2026-10-15）

> ⚠️ **这不是通用事实，是一份个人账号的快照。** 表里的可用性、上下文上限、思考词表、
> token 数、限流等级都跟你自己的账号开通状态和厂商当月版本强相关，会过期。
> 拿去用之前先跑 §6 的 `modelops.py matrix` 在你自己的环境重测一遍。
> token 数字是**单次探针观测**，不是基准测试。

| provider / model | 定位 | 实测 | 备注 |
|---|---|---|---|
| `moonshot / kimi-k3` | 长文、方案、跨领域推理 | ✅ 含视觉 | 上下文 262144；图像输入已声明 |
| `moonshot / kimi-k2.7-code` | 代码 | ✅ | 262144 |
| `qwen / qwen-plus` | 通用、便宜、稳 | ✅ | 非思考型 |
| `qwen / qwen3.8-max` | 最新旗舰，复杂分析 | ✅ | 思考五档 |
| `qwen / qwen3.5-flash` | 快、便宜、会思考 | ✅ | 批量活首选 |
| `qwen / qwen3.5-*`、`qwen3.6-*`、`qwen3.7-*` | 各档位 | ✅（同族抽验） | 均有思考等级 |
| `qwen / qwen3-vl-plus` | **视觉** | ✅ 读图验证过 | 必须声明 `input: [text, image]` |
| `qwen / qwen3.8-omni-flash`、`qwen3.5-omni-plus` | 全模态 | 已声明 image | |
| `qwen / qwen-max` | 老旗舰 | ⚠ **输入上限 30720** | 已声明 `contextWindow: 30720`，别拿它跑长上下文 |
| `bailian / kimi-k3` | Kimi 的备用通道 | ✅ | 走百炼，**不受 Moonshot 账号并发限制** |
| `bailian / glm-5.3` | 挑剔型评审 | ✅ | 只认 `low/high/max` 三档 |
| `bailian / deepseek-v4-pro` | 中文长文 | ✅ | 只认 `low/medium/high/xhigh/max` |
| `router-one / anthropic/claude-opus-5.5` | **Claude 通道**（跨厂商交叉验证的第二家） | ✅ 实测通过 | 只有 Claude 系（opus/sonnet/haiku 5.5），**没有 GPT 直连**；1M 上下文 |
| `stepfun / step-3.5-flash` 等 | Step 系 | ⬜ 已配置未详测 | 见 profile 配置 |
| `ark / doubao-seed-2-1-turbo-260628` | **便宜的 agentic 工人**（能读文件、多步任务） | ✅ 两次全对 | `minimal` 输出 **155 tok**（不传参数 4426 tok，**28 倍差**）；单文件任务约 11 秒 |
| `ark / doubao-seed-2-1-pro-260915`（及 `-260628`） | 方舟旗舰，重活候选 | ✅ 基础+档位通过 | `minimal` 29–40 tok vs 默认 867–1700 tok（**20–42 倍差**） |
| `ark / doubao-seed-evolving` | 跟随最新版的豆包别名 | ✅ 基础+档位通过 | `minimal` 29 vs 默认 834 |
| `ark / glm-5-2-260617` | **GLM-5.2 的方舟通道** | ✅ 基础+档位通过 | `minimal` 28 vs 775；百炼限流时的备用通道 |
| `ark / doubao-seed-2-0-mini-260428` | **最便宜的纯文本批量活** | ✅ | 计算/翻译准确；**读文件会编**，别给 agentic 活 |
| `ark / doubao-seed-2-0-lite-260428` | 同上的备份 | ⚠ 只纯文本 | 工具调用 API 层正常，但经 DSH 大工具表时**不读文件直接编**（假行号假代码） |
| `ark / doubao-seedream-5-0-pro-260628` | **图像生成**（配图 / UI 示意 / 插画） | ✅ 实测出图 | ⚠ **不是对话模型**：走 `/images/generations`，**不能写进 provider 配置**；用 `tools/ark_image.py`；1024² 约 47 秒、4096 tok/张；返回 JPEG（工具按魔数自动命名） |
| `ark / doubao-seedream-5-0-flash-260915` | 图像生成（更快更省） | ⬜ 需先在控制台开通 | 开通后同样用 `ark_image.py --model` 调用 |
| `ollama / *` | 本地、离线、零成本 | 未测 | 走 127.0.0.1:11434 |

### 2.1 怎么拍板 —— 灵活决策，不搞"某活必用某模型"

**没有固定映射。** 每次先问自己四个问题，再从候选池里挑**最合适、够用、且更便宜**的那个：

1. **这活需要工具吗？**（读文件/跑命令/多步）→ 需要就别给纯文本模型
2. **上下文多长？** → 长文/大仓 → 只用 262k 那档（Kimi 系）
3. **需要交叉验证吗？** → 需要就必须**换厂商**挑第二个（同源盲区相同）
4. **错了代价大吗？** → 大 → 用主力模型，或便宜模型出草稿 + 我核验

**加分规则**：成本接近时，优先"能一次做对"的；能自己做就别外包（见下）；先试便宜的，不行再升级——**升级的代价通常小于一上来就用贵的**。

### 2.1.1 别忘了我自己（最重要的一条）

**当前会话的默认模型本身就是一名可用的工人**，不是只会派活的调度台。本机默认是
`deepseek-account/deepseek-flash`；如果你在别的模型上加载这份技能，把下表换成你自己的默认档位。

| 档位 | 什么时候用 |
|---|---|
| 会话默认模型（本机＝deepseek-flash） | **默认先自己干**：小任务、要我保持上下文的活、需要连续多步试错的活 |
| `deepseek-account/deepseek-v4-pro`（更强档） | 需要更强推理时；比外包更省事——**同一个 harness、同一份上下文**，只是换个更重的脑子 |

**为什么"自己做"经常最省**：委派不是免费的——**每个子代理都要重发一遍系统提示 + 工具表 + 技能清单（≈1–2 万 token）**，还要重新读一遍文件才能干活。所以：
- 小任务、一次能说完的任务 → **自己做**（委派的开销比任务本身还大）
- 大批量、可并行的、需要"另一个脑子"的 → 才值得外包

### 2.1.2 候选池（按"适合什么形状的活"分组，不是映射表）

| 池 | 成员 | 适合的活的形状 |
|---|---|---|
| **我自己** | deepseek-flash（默认）、deepseek-v4-pro | 默认先上；需要连续上下文/多步试错；小任务 |
| 💰 极便宜 | 豆包 **2.1-turbo**（能读文件）、**2.0-mini**（纯文本）、**2.0-lite**（纯文本备份） | 大批量、可并行、错了能核验的活 |
| 💰 便宜 | qwen3.5-flash、qwen-plus、bailian/GLM-flash、deepseek-v4.1-flash | 日常主力、筛候选、中等难度 |
| 💰💰 主力 | kimi-k2.7-code（代码）、qwen3.8-max（复杂分析）、glm-5.3（挑刺）、deepseek-v4-pro（中文长文） | 一次做对、要质量 |
| 💰💰💰 重器 | kimi-k3（长上下文/方案）、qwen3-vl-plus（看图） | 只在确实需要那项能力时用 |
| 免费 | ollama | 离线、敏感、零成本兜底 |

**挑的时候看能力而不是看名字**：要读代码就看谁代码强，要"挑刺"就找出名的严格模型，要长文就找窗口大的——**同一个模型在不同任务上表现会变，别把它钉死在一个角色上**。用完觉得不顺手，下次换一个，把结论记回这里。


### 2.2 思考档位经济学（实测，省钱全靠这个）

| 模型 | 不传参数 | `minimal` | `high` | 结论 |
|---|---|---|---|---|
| doubao-seed-2-1-turbo | 4426 tok | **155 tok** | 4247 tok | 差 **28 倍** |
| doubao-seed-2-0-mini | 1114 tok | **423 tok** | 3033 tok | 差 7 倍 |
| doubao-seed-2-0-lite | 4435 tok | **538 tok** | 7687 tok | 差 14 倍 |
| kimi-k3（直连实测） | 最深（357 字） | ≈0 字 | ≈102–141 字 | 只有 on/off 硬边界 |
| qwen3.5-flash | 2463 字 | 0（≡ 关思考） | 2785 字 | 单调 |

**两条硬规则**：
1. **永远显式传档位**——不传参数往往比 `medium` 还贵（豆包/ Kimi 都是）。
2. **批量活一律 `minimal`**；只有"要它想清楚"时才给 `high`，且先给便宜模型试。

### 2.3 成本分档（选型先看这栏）

| 档 | 模型 | 用法 |
|---|---|---|
| 💰 极便宜 | 豆包 mini / turbo / lite | 批量、草稿、纯文本；turbo 可做 agentic |
| 💰 便宜 | qwen3.5-flash、qwen-plus、bailian 的 GLM/DeepSeek flash | 日常主力、筛候选 |
| 💰💰 中等 | kimi-k2.7-code、qwen3.8-max、glm-5.3 | 难活、评审、写代码 |
| 💰💰💰 贵 | kimi-k3（长上下文）、qwen3-vl-plus | 只在长文/看图时用 |
| 免费 | ollama | 离线、敏感、零成本兜底 |


## 3. 四种编排模式（复制即用）

**① 并行扇出（独立子任务）**
```js
const rs = await parallel(items.map(it => () => agent(brief(it), { provider: "qwen", model: "qwen3.5-flash" })));
```

**② 对抗式复核（最值钱）** — 同一份结论给两家模型各写批评，分歧点就是我要亲自查的地方：
```js
const [a, b] = await parallel([
  () => agent(critiqueBrief, { provider: "bailian", model: "glm-5.3" }),
  () => agent(critiqueBrief, { provider: "qwen",   model: "qwen3.8-max" }),
]);
```

**③ 便宜模型筛 + 强模型定**：先用 flash 跑 N 个候选，只把前 3 个交给 K3/3.8-max 深做。

**④ 多模态分工**：图片/截图的判读交给 `qwen3-vl-plus`（让它自己用 `read_image` 读本地文件），
文本推理交给 K3/Qwen，**我负责把两边结论对齐**。

有 `pipeline(items, ...stages)` 时优先用它（无栅栏，快）；只有确实要等全部结果才用 `parallel`。

## 4. 失败手册（都是实测踩过的，按此排查能省半小时）

| 症状 | 根因 | 处置 |
|---|---|---|
| `agent()` 返回 `null`，无报错 | 子代理失败被静默吞掉 | 去会话日志捞错误（§5 配方） |
| `400 developer is not one of [...]` | 非 OpenAI 端点不认 `developer` 角色 | provider 加 `compat: { supportsDeveloperRole: false }`（ollama/moonshot/qwen/bailian 已加） |
| `400 tools.function.parameters is not a valid moonshot flavored json schema … infinite recursion` | 工具 schema 里有自引用 `$ref` | MCP 服务设 `REA_MCP_INPUT_SCHEMA_PROFILE: compact` |
| `400 … Range of input length should be [1, 30720]` | 模型输入上限比 DSH 以为的小（qwen-max） | 声明 `contextWindow` |
| `400 'reasoning_effort' must be one of: 'low','high','max'` | 各家思考词表不同 | 只声明该模型认的键（见 §2 备注） |
| 模型说"看不到图像" | provider 配置没声明 `input: [text, image]` | 在模型条目补 `input` |
| `429 max organization concurrency: 1` / `max RPM: 3` | Moonshot 账号等级限制（0 级） | 升到 1 级（15 并发）或改走 `bailian/kimi-k3` |
| `429 SetLimitExceeded … Safe Experience Mode` | **火山方舟「安全体验模式」免费额度用尽**（试用账号） | 控制台「开通管理」关闭/调高该模式；**教训：试用账号上别做大上下文探测**——一次 400k 字符探测≈20 万 token，能直接吃光额度 |
| `InvalidEndpointOrModel.NotFound`（方舟） | 方舟模型**没在控制台开通**（`/models` 会列出全部可售模型，但不等于已开通） | 控制台开通对应模型；只有已开通的 id 能调 |
| 小模型**编造文件内容**（假行号/假代码） | 它根本没调用工具，直接凭上下文作答——工具表太大时小模型会忽略工具 | 让它在纯文本任务里干活；或换 Kimi/Qwen/DeepSeek；**任何小模型输出都要核验** |
| 新加的模型在 workflow 里查不到 | 运行中的会话**模型注册表是快照**，新模型要重启 DSH 才进注册表（provider 本身会热加载） | 重启 DSH；或先用 CLI（dsh --profile phone '任务'）验证 |
| workflow 报 model 不存在 | `provider` 名或 model id 写错 | 对照 §2；改完 provider 配置**通常热加载**，不生效再重启 |

## 5. 诊断配方（我自己用的）

**捞子代理真实报错**（`agent()` 的 null 不告诉你原因）：
```python
import glob, os, re, time
try:
    from compression import zstd        # Python 3.14+ 内置
except ImportError:
    import zstandard as zstd            # 3.9-3.13: pip install zstandard

paths = sorted(((os.path.getmtime(p), p) for p in
    glob.glob(os.path.expanduser(r"~\.dsh\sessions\**\*"), recursive=True) if os.path.isfile(p)),
    reverse=True)
for mt, p in paths[:6]:
    raw = open(p, "rb").read()
    t = (zstd.decompress(raw) if p.endswith(".zstd") else raw).decode("utf-8", "replace")
    for m in re.finditer(r'"kind":"error"', t):
        print(time.strftime("%H:%M:%S", time.localtime(mt)), re.sub(r"\s+", " ", t[m.start():m.start()+400]))
```

> DSH 的会话日志（`~\.dsh\sessions\**\session.v4.jsonl.zstd`）**全是 zstd 压缩的**，
> 没有解压能力就捞不到任何东西。Python 3.14 自带 `compression.zstd`；3.9–3.13 要
> `pip install zstandard`。本仓库的 `tools/dsh-errors.py` 已做双路径回退。

**矩阵复测**（怀疑路由坏了时，10 个 1-token agent 并行，几秒出结果）：
```js
const Q = "只回两个字符：OK";
const cases = [["moonshot","kimi-k3"],["qwen","qwen-plus"],["qwen","qwen3.8-max"],["qwen","qwen3-vl-plus"],["bailian","glm-5.3"]];
return await parallel(cases.map(([p,m]) => () => agent(Q, { provider: p, model: m, label: m }).then(r => ({m, ok: r !== null}))));
```

## 6. 工具（本技能自带，别手工试错）

```powershell
# 解释器用你自己的 python（3.9+；跑 dsh-errors.py 需要 3.14 或 pip install zstandard）
$py = "python"
$t  = "$HOME\.agents\skills\multi-model-orchestration\tools"

& $py $t\modelops.py check                 # 连通性：key 是否有效、端点是否可达、账号可见多少模型
& $py $t\modelops.py matrix                # 全量能力矩阵 → references\model-matrix.md（约 1~2 分钟）
& $py $t\modelops.py matrix --only qwen    # 只测某家
& $py $t\modelops.py add --provider qwen --model qwen3.9-max --deep   # 探查新模型并推导配置块
& $py $t\dsh-errors.py -m 30 -g qwen       # 捞最近报错（agent() 返回 null 时的第一手段）
```

```bash
# macOS / Linux
py=python
t="$HOME/.agents/skills/multi-model-orchestration/tools"
$py $t/modelops.py check
```

> **`--profile` / `--creds` 必须写在子命令前面**（argparse 父级参数）：
> `modelops.py --profile phone check` ✅，`modelops.py check --profile phone` ❌

`references/model-matrix.md` 由工具生成，**不要手改**；每次加/换模型后重跑一次即可。
矩阵里的 `developer 角色=拒绝` 一列直接告诉你该 provider 要不要 `compat.supportsDeveloperRole: false`。

### 新增一个模型的标准流程（3 步）

1. **加凭据**（新厂商）：`~\.dsh\.credentials.yaml` 的 `refs:` 加一行 `XXX_API_KEY: sk-...`，
   或在 GUI 里加；配置里只写 `apiKeyEnv: XXX_API_KEY`，**明文永不进配置文件、也不贴聊天**。
2. **探查**：`modelops.py add --provider <id> --model <model-id> --deep`
   → 自动判定：能否调用 / `developer` 角色是否被拒（要不要 compat）/ 思考词表（哪些档位合法，
   且只输出合法的）/ 是否吃图像（要不要 `input: [text, image]`）。把打印出的 YAML 块填进
   `cordis.patch.yml` 的 `providers.<id>.models` 下。
3. **验证**：`modelops.py matrix --only <id>` 确认全绿；再在 workflow 里发一个 1-token 真任务
   确认 DSH 路由也通（直连通 ≠ DSH 通，两者故障模式不同）。

> 新 provider 还要写 `api: openai-completions`、`baseURL`、`apiKeyEnv`；
> 若 `add` 报告拒绝 developer 角色，**该 provider 必须**加：
> ```yaml
>         compat:
>           supportsDeveloperRole: false
> ```

## 7. 失败回退链（聪明地兜底，别硬等）

`agent()` 返回 `null` 时按顺序做，不要盲目重试同一个模型：

| 场景 | 回退动作 |
|---|---|
| 某模型 429 / 限流 | **换通道**：`moonshot/kimi-k3` ↔ `bailian/kimi-k3`（后者不走 Moonshot 账号限流）。⚠️ 前提是你**已经配好 bailian provider 且有有效百炼 key**，否则换了还是 401——备用通道要提前配，别等限流了才想起来 |
| 某模型 400 参数错 | 跑 `dsh-errors.py` 看原话 → 按 §4 修配置 → 修完再试；**别换模型掩盖配置错** |
| 单模型不可用 | 用同族替代：Qwen3.8Max→3.7-Max→3.5-Plus；GLM-5.3→GLM-5.2；K3→K2.7-Code |
| 长上下文被截断 | 换 `contextWindow` 大的：Kimi 系 262144；或先让便宜模型压缩摘要再交给强模型 |
| 视觉模型说看不到图 | 检查该模型条目有没有 `input: [text, image]`（§4） |
| 多家同时失败 | 先跑 `modelops.py check` 判断是不是 key/网络问题，再怀疑模型 |

**成本纪律**：探针用 1-token；矩阵别频繁跑（只在加/换模型后）；真任务优先给便宜模型，只把难的部分交给旗舰。

## 8. 派活契约（不遵守就会返工）

1. **任务书要短、边界清晰、要求结构化输出**——跨模型最常死在"指令遵循风格不一致"，不是能力不足。
2. **给绝对路径**；告诉它用哪个工具读（`read` / `read_image`）。
3. **禁区要明说**："不要编造客户名/数字；缺数据就写占位符"（面向客户的产物尤其重要）。
4. **写范围不重叠**：多个执行者时，一人一份文件；`write_scopes` 只是提示不是锁。
5. **我负责**：合并、跑验证（不是靠它自称完成）、把结论落到证据上。
6. **成本纪律**：先 1-token 探针验证路由，再发真任务；能并行的别串行。

## 9. 何时不要用这套

- 单文件小改动、一问一答 → 我自己做，别开 agent。
- 需要连续多轮试探、频繁改文件 → 单模型（同模型队友）更顺，跨模型反而在交接上耗损。
- 目标是"最终答案"而不是"多视角" → 多模型只值一次交叉复核，不值得全流程铺开。
