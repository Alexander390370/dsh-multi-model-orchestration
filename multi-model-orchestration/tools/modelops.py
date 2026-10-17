#!/usr/bin/env python3
"""modelops — DSH 多模型编排的自动化工具。

三个子命令：
  matrix                探测 profile 里配置的全部 provider/model，生成能力矩阵
                        （写入 skill 的 references/model-matrix.md + JSON 缓存）
  add --provider --model [--base-url --key-env --display-name]
                        探查一个**新模型**，自动推导它需要的配置块
                        （compat / input / reasoningEfforts / contextWindow）并打印 YAML
  check                 只做连通性检查（key 是否有效、端点是否可达、模型是否存在）

设计原则：
  * 全部依据服务端真实响应，不猜；拿不到证据就写"未知"。
  * 密钥只从 ~/.dsh/.credentials.yaml 读，永不打印。
  * 探测走**直连 API**（绕开 DSH），这样能独立判断 key/端点/词表是否可用。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

# 可用环境变量覆盖：DSH_HOME / DSH_PROFILE
DSH_HOME = os.path.expanduser(os.environ.get("DSH_HOME", "~/.dsh"))
PROFILE = os.path.join(DSH_HOME, "profiles", os.environ.get("DSH_PROFILE", "desktop"),
                       "cordis.patch.yml")
CREDS = os.path.join(DSH_HOME, ".credentials.yaml")
# 技能根目录：从本文件位置反推（tools/ 的上一级），跨平台，且不假设装在 ~/.agents/skills。
# 想覆盖就设环境变量 MMO_SKILL_DIR。
SKILL_DIR = os.environ.get("MMO_SKILL_DIR") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
REFS = os.path.join(SKILL_DIR, "references")
CACHE = os.path.join(REFS, "model-matrix.json")
MATRIX_MD = os.path.join(REFS, "model-matrix.md")
CTX = ssl.create_default_context()
PROBE_Q = "只回两个字：OK"
# 1x1 红点 PNG，用来判断模型是否接受图像输入
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


# ───────────────────────────── 配置与凭据 ─────────────────────────────

def load_yaml(path):
    try:
        import yaml  # type: ignore
    except ImportError:
        sys.exit("需要 PyYAML：pip install pyyaml")
    return yaml.safe_load(io.open(path, encoding="utf-8").read())


def load_credentials() -> dict:
    text = io.open(CREDS, encoding="utf-8", errors="replace").read()
    refs = {}
    m = re.search(r"^refs:\s*$([\s\S]*)$", text, re.M)
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"\s+([A-Za-z0-9_.\-]+)\s*:\s*(.+?)\s*$", line)
            if mm:
                refs[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return refs


def load_providers() -> dict:
    doc = load_yaml(PROFILE)
    for entry in doc:
        if entry.get("id") == "llm-pi-ai":
            return entry["config"]["providers"]
    sys.exit("profile 里找不到 llm-pi-ai")


# ───────────────────────────── 探测原语 ─────────────────────────────

class Probe:
    def __init__(self, base_url: str, key: str, timeout: int = 60):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.key = key
        self.timeout = timeout

    def chat(self, model: str, messages, max_tokens: int = 8, extra: dict | None = None):
        body = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if extra:
            body.update(extra)
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=CTX) as r:
                    payload = json.loads(r.read())
                msg = payload["choices"][0]["message"]
                return {"ok": True, "content": (msg.get("content") or "").strip(),
                        "reasoning": len(msg.get("reasoning_content") or ""),
                        "tokens": payload.get("usage", {}).get("completion_tokens")}
            except urllib.error.HTTPError as e:
                text = re.sub(r"\s+", " ", e.read(300).decode("utf-8", "replace"))
                if e.code == 429 and attempt < 2:
                    time.sleep(6 * (attempt + 1))
                    continue
                return {"ok": False, "status": e.code, "error": text}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "status": 0, "error": f"{type(e).__name__}: {e}"}
        return {"ok": False, "status": 429, "error": "rate limited"}


def probe_basic(p: Probe, model: str) -> dict:
    return p.chat(model, [{"role": "user", "content": PROBE_Q}])


def probe_developer_role(p: Probe, model: str) -> bool:
    """True = 该端点接受 OpenAI 的 developer 角色（否则需要 compat 关闭）。"""
    r = p.chat(model, [{"role": "developer", "content": "你是助手"},
                       {"role": "user", "content": PROBE_Q}])
    if r["ok"]:
        return True
    return "developer" not in r.get("error", "")


def probe_image(p: Probe, model: str) -> str:
    content = [{"type": "text", "text": "这张图什么颜色？只回一个词。"},
               {"type": "image_url", "image_url": {"url": "data:image/png;base64," +
                                                   base64.b64encode(TINY_PNG).decode()}}]
    r = p.chat(model, [{"role": "user", "content": content}], max_tokens=16)
    if r["ok"]:
        return "accepts"
    err = r.get("error", "")
    if re.search(r"(image|vision|multimodal|图片|模[态型])", err, re.I):
        return "rejects"
    return f"unknown({r.get('status')})"


def probe_reasoning(p: Probe, model: str, levels=("none", "minimal", "low", "medium", "high", "max")) -> dict:
    out = {}
    for lvl in levels:
        r = p.chat(model, [{"role": "user", "content": PROBE_Q}], max_tokens=32,
                   extra={"reasoning_effort": lvl})
        if r["ok"]:
            out[lvl] = "ok"
        else:
            if "must be one of" in r.get("error", ""):
                allowed = re.findall(r"'([a-z]+)'", r["error"])
                out[lvl] = "invalid"
                out["_allowed"] = ",".join(dict.fromkeys(allowed))
                break
            out[lvl] = f"err{r.get('status')}"
        time.sleep(0.6)
    return out


def probe_context_cap(p: Probe, model: str, start: int = 8000, cap: int = 400000) -> int | None:
    """二分找出服务端接受的近似输入上限（字符数）。返回 None = 未触及上限。"""
    def fits(n):
        r = p.chat(model, [{"role": "user", "content": "数据标注" * (n // 4) + "\n只回：OK"}], max_tokens=4)
        if r["ok"]:
            return True
        if r.get("status") == 400 and re.search(r"input length|too long|maximum", r.get("error", ""), re.I):
            return False
        return None  # 其他错误不参与二分

    lo, hi = start, start
    if fits(start) is not True:
        return None
    hi = start * 2
    while hi <= cap:
        r = fits(hi)
        if r is True:
            lo, hi = hi, hi * 2
            continue
        if r is False:
            break
        return None
    else:
        return None
    while lo + 1000 < hi:
        mid = (lo + hi) // 2
        r = fits(mid)
        if r is True:
            lo = mid
        elif r is False:
            hi = mid
        else:
            break
    return lo


# ───────────────────────────── 子命令 ─────────────────────────────

def cmd_matrix(args):
    providers = load_providers()
    creds = load_credentials()
    rows, t0 = [], time.time()
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(io.open(CACHE, encoding="utf-8"))

    for pid, cfg in providers.items():
        if args.only and pid not in args.only:
            continue
        key = creds.get(cfg.get("apiKeyEnv", ""), "")
        base = cfg.get("baseURL", "")
        if not key or not base:
            print(f"[{pid}] 跳过（缺 apiKeyEnv 或 baseURL）")
            continue
        p = Probe(base, key)
        dev_ok = None
        for m in cfg.get("models", []):
            mid = m["id"]
            r = probe_basic(p, mid)
            if dev_ok is None and r["ok"]:
                dev_ok = probe_developer_role(p, mid)
            row = {
                "provider": pid, "model": mid, "ok": r["ok"],
                "status": r.get("status"), "error": (r.get("error") or "")[:180],
                "reasoning_levels": list((m.get("reasoningEfforts") or {}).keys()),
                "declared_image": bool(isinstance(m.get("input"), list) and "image" in m["input"]),
                "contextWindow": m.get("contextWindow"),
                "checked_at": time.strftime("%Y-%m-%d %H:%M"),
            }
            rows.append(row)
            mark = "✅" if r["ok"] else "❌"
            print(f"{mark} {pid}/{mid:<26} {'' if r['ok'] else row['error'][:90]}")
            time.sleep(0.35)
        if dev_ok is not None:
            for row in rows:
                if row["provider"] == pid and row["ok"]:
                    row["accepts_developer_role"] = dev_ok
            print(f"    └ {pid}: 端点{'接受' if dev_ok else '**拒绝**'} developer 角色"
                  f"{'' if dev_ok else ' → 必须 compat.supportsDeveloperRole: false'}")

    cache[str(int(t0))] = {"generated": time.strftime("%Y-%m-%d %H:%M"), "rows": rows}
    os.makedirs(REFS, exist_ok=True)
    json.dump(cache, io.open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_matrix_md(rows)
    ok = sum(1 for r in rows if r["ok"])
    print(f"\n矩阵完成：{ok}/{len(rows)} 可用 → {MATRIX_MD}")
    return 0


def write_matrix_md(rows):
    good = [r for r in rows if r["ok"]]
    bad = [r for r in rows if not r["ok"]]
    lines = [
        "# 模型能力矩阵（自动生成，勿手改）",
        "",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M')}　可用 **{len(good)}/{len(rows)}**",
        "生成命令：`python modelops.py matrix`（直连 API 探测，绕开 DSH）",
        "",
        "## 可用",
        "",
        "| provider / model | 思考等级 | 声明图像输入 | contextWindow | developer 角色 |",
        "|---|---|---|---|---|",
    ]
    for r in good:
        dev = {True: "接受", False: "**拒绝→需 compat 关闭**", None: "—"}.get(r.get("accepts_developer_role"))
        lines.append(f"| `{r['provider']}/{r['model']}` | {','.join(r['reasoning_levels']) or '—'} | "
                     f"{'是' if r['declared_image'] else '否'} | {r['contextWindow'] or '—'} | {dev} |")
    if bad:
        lines += ["", "## 不可用（附服务端原话）", "", "| provider / model | 错误 |", "|---|---|"]
        for r in bad:
            lines.append(f"| `{r['provider']}/{r['model']}` | `{r['error'][:150]}` |")
    lines += ["", "> 排查顺序见 SKILL.md §4 失败手册；新增模型用 `python modelops.py add`。", ""]
    io.open(MATRIX_MD, "w", encoding="utf-8").write("\n".join(lines))


def cmd_check(args):
    providers = load_providers()
    creds = load_credentials()
    for pid, cfg in providers.items():
        env = cfg.get("apiKeyEnv", "")
        key = creds.get(env, "")
        base = cfg.get("baseURL", "")
        n = len(cfg.get("models", []))
        status = "缺失！" if not key else f"len={len(key)}"
        print(f"{pid:<9} key({env})={status:<10} base={base:<56} models={n}")
        if key and base:
            try:
                req = urllib.request.Request(base.rstrip('/') + "/models",
                                             headers={"Authorization": f"Bearer {key}"})
                with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
                    data = json.loads(r.read())
                ids = [m.get("id") for m in data.get("data", [])] if isinstance(data, dict) else []
                print(f"          /models → {r.status}，账号可见 {len(ids)} 个模型")
            except Exception as e:  # noqa: BLE001
                print(f"          /models → {type(e).__name__}: {str(e)[:80]}")
    return 0


def cmd_add(args):
    providers = load_providers()
    creds = load_credentials()
    cfg = providers.get(args.provider)
    base = args.base_url or (cfg or {}).get("baseURL")
    env = args.key_env or (cfg or {}).get("apiKeyEnv")
    key = creds.get(env or "", "")
    if not base or not key:
        sys.exit(f"缺少 baseURL 或凭据（provider={args.provider} base={base} keyEnv={env}）")
    p = Probe(base, key)
    print(f"探测 {args.provider}/{args.model} @ {base}\n")

    basic = probe_basic(p, args.model)
    if not basic["ok"]:
        print(f"❌ 基础调用失败：{basic.get('status')} {basic.get('error','')[:200]}")
        print("\n先解决连通性/key/模型名，再谈能力声明。")
        return 1
    print(f"✅ 基础调用 200（思考内容 {basic['reasoning']} 字，输出 {basic['tokens']} tok）")

    dev = probe_developer_role(p, args.model)
    print(f"{'✅' if dev else '⚠️ '} developer 角色：{'接受' if dev else '拒绝 → 该 provider 需要 compat.supportsDeveloperRole: false'}")

    vocab = probe_reasoning(p, args.model)
    allowed = vocab.pop("_allowed", None)
    ok_levels = [k for k, v in vocab.items() if v == "ok"]
    if allowed:
        print(f"⚠️  思考词表受限：只认 {allowed}")
        ok_levels = [x for x in allowed.split(",") if x]
    elif ok_levels:
        print(f"✅ 思考等级可用：{','.join(ok_levels)}")
    else:
        print("➖ 未观察到思考等级支持（可能完全不支持 reasoning_effort）")

    img = probe_image(p, args.model) if args.deep else "skipped"
    print(f"{'🖼️ ' if img == 'accepts' else '➖ '}图像输入：{img}")

    mapped = []
    for lvl in ok_levels:
        mapped.append(('"off": none' if lvl == "none" else f"{lvl}: {lvl}"))
    block = [f"          - id: {args.model}", f"            name: {args.display_name or args.model}"]
    if mapped:
        block.append("            reasoningEfforts:")
        block += [f"              {x}" for x in mapped]
    if img == "accepts":
        block += ["            input:", "              - text", "              - image"]
    print("\n—— 复制到 cordis.patch.yml 的 models: 下 ——")
    print("\n".join(block))
    if not dev:
        print("\n（该 provider 若还没加过 compat，记得在 provider 层级加：\n"
              "        compat:\n          supportsDeveloperRole: false）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="DSH 多模型编排工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("matrix", help="全量能力矩阵")
    m.add_argument("--only", nargs="*", help="只测这些 provider")
    m.set_defaults(func=cmd_matrix)

    c = sub.add_parser("check", help="连通性检查")
    c.set_defaults(func=cmd_check)

    a = sub.add_parser("add", help="探查新模型并推导配置")
    a.add_argument("--provider", required=True)
    a.add_argument("--model", required=True)
    a.add_argument("--base-url")
    a.add_argument("--key-env")
    a.add_argument("--display-name")
    a.add_argument("--deep", action="store_true", help="额外探测图像输入（多一次调用）")
    a.set_defaults(func=cmd_add)

    ap.add_argument("--profile", help="profile 名（默认 desktop，或环境变量 DSH_PROFILE）")
    ap.add_argument("--creds", help="凭据文件路径（默认 <DSH_HOME>/.credentials.yaml）")
    args = ap.parse_args()
    global PROFILE, CREDS
    if args.profile:
        PROFILE = os.path.join(DSH_HOME, "profiles", args.profile, "cordis.patch.yml")
    if args.creds:
        CREDS = os.path.expanduser(args.creds)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
