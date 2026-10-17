# DSH 多模型编排技能包（multi-model-orchestration）

> 让一个 AI 主控（Team Lead）把任务**按模型长处拆给不同的大模型**去干，并把结果收口验证。
> 面向 [DeepSeek Harness](https://github.com/deepseek-ai) 的 Agent Skill + 自检工具，纯本地运行，不依赖任何服务。

---

## 为什么需要它

DSH 里让多个模型协作有两个坑，这个包把它堵上：

1. **`spawn_teammate`（常驻队友）不能指定模型** —— 它的入参只有 `name/description/prompt/context`，
   队友只能继承会话默认模型。于是"找两个不同模型交叉验证"用队友是做不到的。
   → **唯一可靠路径是 `workflow` 的 `agent(prompt, { provider, model })` 逐次覆盖**。
2. **每家模型的"脾气"都不一样**，配错了就静默失败（`agent()` 失败只返回 `null`，不给原因）：
   - 非 OpenAI 端点普遍拒绝 `developer` 角色 → 需要 `compat.supportsDeveloperRole: false`
   - 各家 `reasoning_effort` **词表不同**（GLM 只认 `low/high/max`；DeepSeek 认 `low/medium/high/xhigh/max`）
   - 视觉模型必须显式声明 `input: [text, image]`，否则 DSH 会把图片丢掉，模型回答"我看不到图"
   - 有些模型输入上限比你想的小（例：`qwen-max` = 30720），DSH 压缩时超限会整轮失败
   - Moonshot 拒绝带自引用 `$ref` 的工具 JSON Schema（`infinite recursion`）

这些坑本仓库的工具都能**自动探出来**，不用一个个试。

## 安装

把 `multi-model-orchestration/` 放进技能目录即可（DSH 会实时发现新技能）：

```powershell
# Windows
.\install.ps1
```
```bash
# macOS / Linux
./install.sh
```

手动安装 = 把这个目录复制到 `~/.agents/skills/multi-model-orchestration/`。

要求：Python 3.9+。**跑 `dsh-errors.py` 需要 zstd 解压能力**：Python 3.14+ 自带 `compression.zstd`；3.9–3.13 请 `pip install zstandard`（脚本已做双路径回退，没有也能跑，只是 `.zstd` 会话文件会被跳过）。

## 目录

```
multi-model-orchestration/
├─ SKILL.md                        技能本体：路由表 / 编排模式 / 失败手册 / 派活契约
├─ references/
│   └─ model-matrix.example.md     自动生成的模型能力矩阵（示例）
└─ tools/
    ├─ modelops.py                 check / matrix / add —— 自检与配置推导
    └─ dsh-errors.py               从会话语料里捞子代理的真实报错
```

## 快速开始

```powershell
# 解释器用你自己的 python（3.9+；dsh-errors.py 需 3.14 或 pip install zstandard）
$py = "python"
$t  = "$HOME\.agents\skills\multi-model-orchestration\tools"

& $py $t\modelops.py check          # 连通性：key 是否有效、端点是否可达
& $py $t\modelops.py matrix         # 全量能力矩阵 → references\model-matrix.md
& $py $t\modelops.py add --provider qwen --model qwen3.9-max --deep   # 新模型：自动推导该怎么配
& $py $t\dsh-errors.py -m 30 -g qwen                                  # 捞最近报错
```

> `--profile` / `--creds` 必须写在子命令**前面**：`modelops.py --profile phone check` ✅

`modelops.py add` 会打印**可直接粘贴**的 YAML 片段，例如：

```yaml
          - id: qwen3.7-plus
            name: qwen3.7-plus
            reasoningEfforts:
              "off": none          # 注意引号：YAML 里裸写的 off 会变成布尔 False
              minimal: minimal
              low: low
              medium: medium
              high: high
              xhigh: xhigh
```

## 四种编排模式

```js
// ① 并行扇出：独立子任务
await parallel(items.map(it => () => agent(brief(it), { provider: "qwen", model: "qwen3.5-flash" })));

// ② 对抗式复核（最值钱）：同一份结论给两家模型各写批评，分歧点 = 我亲自查的地方
const [a, b] = await parallel([
  () => agent(critique, { provider: "bailian", model: "glm-5.3" }),
  () => agent(critique, { provider: "qwen",    model: "qwen3.8-max" }),
]);

// ③ 便宜模型筛 + 强模型定：flash 出 N 个候选，前 3 个交给旗舰深做
// ④ 多模态分工：截图判读交给视觉模型（让它自己 read_image），文本推理交给 K3/Qwen
```

## 失败回退链（摘要）

| 症状 | 处置 |
|---|---|
| `agent()` 返回 `null` | 跑 `dsh-errors.py` 看服务端原话，别盲目重试 |
| `400 developer is not one of [...]` | provider 加 `compat: { supportsDeveloperRole: false }` |
| `400 ... infinite recursion` | MCP 工具 schema 设 `REA_MCP_INPUT_SCHEMA_PROFILE: compact` |
| `400 ... Range of input length` | 该模型声明真实 `contextWindow` |
| `400 'reasoning_effort' must be one of` | 只声明该模型认的档位 |
| 模型说"看不到图像" | 模型条目补 `input: [text, image]` |
| `429 max organization concurrency` | 换通道（直连 ↔ 聚合网关）或升级账号等级 |

## 设计原则

1. **证据优先**：所有结论来自服务端真实响应；拿不到证据就写"未知"，不猜。
2. **密钥不出配置文件**：配置里只写 `apiKeyEnv: NAME`，明文只进凭据库，永不打印、永不入日志。
3. **直连探测 ≠ DSH 可用**：工具走直连 API 判断 key/端点/词表，最终仍要在 DSH 里发一个 1-token 任务确认路由。
4. **成本纪律**：探针 1-token；矩阵只在加/换模型后跑；真任务先给便宜模型。

## 兼容性

- DSH profile 配置文件默认为 `~/.dsh/profiles/desktop/cordis.patch.yml`，
  用 `--profile` 或环境变量 `DSH_PROFILE` / `DSH_HOME` 覆盖。
- 模型清单与词表会随厂商更新变化，**矩阵是快照**：加/换模型后重跑 `modelops.py matrix`。

## License

MIT —— 见 [LICENSE](LICENSE)。
