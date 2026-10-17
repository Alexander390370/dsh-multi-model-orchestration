#!/usr/bin/env python3
r"""dsh-errors — 捞出最近子代理/主会话的真实报错。

为什么需要它：`workflow` 的 agent() 失败时**只返回 null，不给原因**。
真正的错误在会话日志里（`~\.dsh\sessions\**\session.v4.jsonl.zstd`，zstd 压缩）。

用法：
  python dsh-errors.py                # 最近 15 分钟
  python dsh-errors.py -m 60          # 最近 60 分钟
  python dsh-errors.py -g qwen        # 只看含 qwen 的错误
  python dsh-errors.py -n 3           # 只看最新 3 个会话文件
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import time

try:
    from compression import zstd  # Python 3.14+ 内置
except ImportError:  # pragma: no cover
    try:
        import zstandard as zstd  # 3.9-3.13：pip install zstandard
    except ImportError:
        zstd = None

# 用 os.path.join 拼路径，而不是硬编码反斜杠：POSIX 上反斜杠不是分隔符，
# 写成 r"~\.dsh\sessions" 会 expanduser 成一个带反斜杠的字面目录名，
# 结果扫到 0 个文件却静默输出「共 0 条」。
# 也尊重 DSH_HOME 环境变量，和 modelops.py 保持一致。
_DSH_HOME = os.path.expanduser(os.environ.get("DSH_HOME", "~/.dsh"))
ROOTS = [
    os.path.join(_DSH_HOME, "sessions"),
    os.path.join(_DSH_HOME, "storages", "session_projcache", "sessions"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--minutes", type=float, default=15)
    ap.add_argument("-g", "--grep", default=None)
    ap.add_argument("-n", "--files", type=int, default=8)
    ap.add_argument("--all", action="store_true", help="不做时间过滤")
    args = ap.parse_args()

    files = []
    for root in ROOTS:
        for p in glob.glob(os.path.join(root, "**", "*"), recursive=True):
            if os.path.isfile(p):
                files.append((os.path.getmtime(p), p))
    files.sort(reverse=True)

    cut = 0 if args.all else time.time() - args.minutes * 60
    shown = 0
    skipped_zstd = 0
    for mt, path in files[: args.files]:
        if mt < cut:
            continue
        raw = open(path, "rb").read()
        if path.endswith(".zstd"):
            if zstd is None:
                # 真·跳过：继续扫后面的文件，而不是整体退出
                skipped_zstd += 1
                continue
            try:
                raw = zstd.decompress(raw)
            except Exception:  # noqa: BLE001
                continue
        text = raw.decode("utf-8", "replace")
        for m in re.finditer(r'"kind":"error"', text):
            win = re.sub(r"\s+", " ", text[m.start(): m.start() + 600])
            if args.grep and not re.search(args.grep, win, re.I):
                continue
            print(f"--- {time.strftime('%H:%M:%S', time.localtime(mt))}  {os.path.basename(path)[:44]}")
            print(f"    {win[:420]}\n")
            shown += 1
            break  # 每个文件只报第一条，避免刷屏

    if skipped_zstd:
        print(
            f"⚠️ 跳过了 {skipped_zstd} 个 .zstd 会话文件（没有 zstd 解压能力）。\n"
            f"   Python 3.14+ 自带 compression.zstd；3.9-3.13 请 pip install zstandard\n"
        )
    print(f"共 {shown} 条（窗口 {args.minutes} 分钟，扫描 {min(args.files, len(files))} 个最新会话文件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
