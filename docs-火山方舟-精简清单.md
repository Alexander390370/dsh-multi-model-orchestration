# 火山方舟 · 精简清单（防晕版）

> 方舟 `/models` 列出 135 个模型、可售 30+ 个，但**你不需要那么多**。
> 这份清单只留"实测过、有用、值得开通"的，其余一律忽略。

## 推荐开通（就这 3 个，都是豆包文本模型）

| 模型 ID | 角色 | 实测结论 | 成本特征 |
|---|---|---|---|
| **`doubao-seed-2-1-turbo-260628`** | **便宜的 agentic 工人**：能读文件、做多步任务 | ✅ 两次文件任务全对（引用行一字不差、端点路径准确） | `minimal` 档输出 **155 tok**；不传参数 4426 tok（**28 倍差**）→ 一律给 `minimal` |
| **`doubao-seed-2-0-mini-260428`** | 最便宜的纯文本批量活：翻译 / 计算 / 摘要 / 分类 | ✅ 计算题（-16%）与商务翻译都准确 | `minimal` 输出 ~423 tok |
| **`doubao-seed-2-0-lite-260428`** | 同上的备份 | ⚠️ **只做纯文本**：让它读文件时**两次编造**内容（假行号假代码） | `minimal` ~538 tok |

### 关键分工（踩过坑才总结出来的）

- **要读文件/跑多步 → 用 turbo**（2.0 mini/lite 会忽略工具、直接编）
- **纯文本批量 → 用 mini**（最便宜，够准）
- **任何便宜模型的输出都要核验**：它的工具调用能力在 API 层正常，但经 DSH 的大工具表时小模型会"跳过工具直接作答"

## 可以先不开的

| 类别 | 例子 | 为什么先不开 |
|---|---|---|
| 视频生成 | `doubao-seedance-*` | 你目前不需要；按秒/按条计费，容易误烧 |
| 图像生成 | `doubao-seedream-*` | 同上；要生成配图时再开 |
| 向量/embedding | `doubao-embedding-*` | 除非做 RAG 知识库 |
| 语音 | `doubao-seed-tts/asr-*` | 除非做语音标注链路 |
| 2.0 系列旧版 | `doubao-seed-2-0-pro-*`、1.6/1.5 全系 | turbo 更便宜也更新 |
| 三方模型 | 方舟上的 `kimi-k3` / `glm-5-*` / `deepseek-v4-*` | 这些是 **Agent Plan 套餐**通道（当前 `ModelNotOpen`）；你在 Moonshot/百炼已经有好通道了，除非想合并账单 |

## 开通与配额的两个开关（都已踩过）

1. **`SetLimitExceeded`** = 账户上的「安全体验模式」用量上限 → 去 **开通管理** 关掉/调高。
   **充值不会自动解除**（充了 ¥20 仍然报同一错，直到手动关掉）。
2. **`ModelNotOpen`** = 该模型没在控制台开通。注意 `/models` 能列出 ≠ 已开通。

控制台直达：<https://ark.volcengine.com/region:cn-beijing/openManagement?LLM=%7B%7D&advancedActiveKey=agentPlan>

## 已经接进 DSH 的配置

两个 profile（`desktop` + `phone`）都含上面 3 个模型，均已配：

```yaml
      ark:
        baseURL: https://ark.cn-beijing.volces.com/api/v3
        apiKeyEnv: ARK_API_KEY          # 明文只进凭据库
        compat: { supportsDeveloperRole: false }
        models:
          - id: doubao-seed-2-1-turbo-260628   # contextWindow 131072 + 五档思考
          - id: doubao-seed-2-0-mini-260428
          - id: doubao-seed-2-0-lite-260428
```

> ⚠️ **新加的模型要重启 DSH** 才会进运行中会话的模型注册表（provider 本身能热加载，模型列表是快照）。
> 重启前想在 DSH 里用新模型，可以先走 CLI：`dsh --profile phone "任务"`。
