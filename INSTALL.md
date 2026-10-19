# 安装 multi-model-orchestration

这是一个 **DSH Agent Skill**（不是插件 bundle）。安装 = 把目录放进 DSH 的技能扫描路径，
DSH 会实时发现，无需重启。

---

## 方式一：用仓库自带脚本（推荐）

从仓库根目录运行：

```powershell
# Windows
.\install.ps1
```

```bash
# macOS / Linux
chmod +x install.sh
./install.sh
```

脚本会：
1. 检查源目录存在
2. 如果目标已存在，先备份成 `multi-model-orchestration.backup-<时间戳>`
3. 复制到 `~/.agents/skills/multi-model-orchestration/`
4. 提示自检命令

---

## 方式二：用本压缩包

把压缩包里的 `multi-model-orchestration/` 整个目录复制到技能目录：

```powershell
# Windows
$dst = "$env:USERPROFILE\.agents\skills"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Expand-Archive -Path multi-model-orchestration-2.0.0.zip -DestinationPath $env:TEMP -Force
Copy-Item "$env:TEMP\multi-model-orchestration\multi-model-orchestration" $dst -Recurse -Force
```

```bash
# macOS / Linux
mkdir -p ~/.agents/skills
unzip -o multi-model-orchestration-2.0.0.zip -d /tmp
cp -r /tmp/multi-model-orchestration/multi-model-orchestration ~/.agents/skills/
```

安装后应该是：

```
~/.agents/skills/multi-model-orchestration/
├── SKILL.md
├── references/
│   └── model-matrix.example.md
└── tools/
    ├── modelops.py
    ├── ark_image.py
    └── dsh-errors.py
```

---

## 依赖

| 依赖 | 说明 |
|---|---|
| Python **3.9+** | 运行 `tools/*.py` |
| `pyyaml` | `modelops.py` 需要（缺了会提示） |
| `zstandard` | `dsh-errors.py` 读 `.zstd` 会话文件需要。**Python 3.14+ 自带 `compression.zstd`，无需安装** |

```bash
pip install pyyaml zstandard
```

> `zstandard` 是可选的：没有也能跑，只是 `.zstd` 格式的会话文件会被跳过并提示。

---

## 验证安装

```powershell
$py = "python"
$t  = "$env:USERPROFILE\.agents\skills\multi-model-orchestration\tools"

# 1. 配置自检：key 是否有效、端点是否可达
& $py $t\modelops.py check

# 2. 生成能力矩阵（约 1-2 分钟，直连 API 探测）
& $py $t\modelops.py matrix
```

`matrix` 会生成 `references/model-matrix.md`（不入库，本地快照）。

**注意**：`modelops.py check` 需要你的 profile 里已经配好各家的 `apiKeyEnv`。
没配的话它会报告"未找到 key"，这不是安装失败。

---

## 在 DSH 里确认技能被识别

打开新会话，问模型：

> 你现在有哪些 skills？

应该能看到 `multi-model-orchestration`。或者直接触发：

> 让几个模型交叉验证一下这个方案

---

## 更新

```powershell
# 拉最新
git pull

# 重新安装（会先备份旧版）
.\install.ps1
```

---

## 卸载

```powershell
Remove-Item "$env:USERPROFILE\.agents\skills\multi-model-orchestration" -Recurse -Force
```

```bash
rm -rf ~/.agents/skills/multi-model-orchestration
```

---

## 排查

**技能没出现**

- 确认目录名和 `SKILL.md` 里的 `name:` 一致（都是 `multi-model-orchestration`）
- 确认路径是 `~/.agents/skills/<name>/SKILL.md`，不是多套了一层
- DSH 实时发现新技能，但**当前会话**可能不会立刻刷新，开新会话试试

**`modelops.py` 报 ModuleNotFoundError: yaml**

```bash
pip install pyyaml
```

**`modelops.py check` 报找不到 key**

检查 `~/.dsh/profiles/<你的profile>/cordis.patch.yml` 里各 provider 的 `apiKeyEnv`，
以及 `~/.dsh/.credentials.yaml` 里对应的 key 是否存在。这个工具只做检查，不会帮你填 key。

**`dsh-errors.py` 说跳过 .zstd 文件**

```bash
pip install zstandard
```
或升级到 Python 3.14+。

**`modelops.py add` 报连不上 API**

`add` 需要直连厂商 API 探测模型能力。检查网络 / 代理，或先用 `check` 确认哪些 provider 可达。

---

## 和 DSH 插件有什么区别

| | Agent Skill（本包） | DSH 插件 bundle |
|---|---|---|
| 形态 | 目录 + `SKILL.md` | `package.json` + `cordis.patch.yml` |
| 安装 | 复制到 `~/.agents/skills/` | 建链接 + 登记 profile |
| 生效 | 实时发现，无需重启 | 需重启应用 |
| 作用 | 给模型的操作手册 + 辅助脚本 | 给 DSH 增加运行时能力（工具/MCP/UI） |

本包是前者。它不注册任何工具，只是让模型知道**怎么正确地把任务分给不同模型**，
并附带几个自检脚本。

---

## License

MIT
