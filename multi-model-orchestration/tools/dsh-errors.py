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
    from compression import zstd  # Python 3.14+
except ImportError:  # pragma: no cover
    zstd = None

ROOTS = [os.path.expanduser(r"~\.dsh\sessions"),
         os.path.expanduser(r"~\.dsh\storages\session_projcache\sessions")]


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
    for mt, path in files[: args.files]:
        if mt < cut:
            continue
        raw = open(path, "rb").read()
        if path.endswith(".zstd"):
            if zstd is None:
                print("需要 Python 3.14 的 compression.zstd")
                return 2
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
    print(f"共 {shown} 条（窗口 {args.minutes} 分钟，扫描 {min(args.files, len(files))} 个最新会话文件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
