#!/usr/bin/env python3
"""ark_image — 用火山方舟的 Seedream 出图（图像模型不走 chat 接口，所以单独一个工具）。

为什么不能塞进 DSH 的 provider 配置：provider 走的是 /chat/completions，
而 Seedream 走 /images/generations —— 端点不同、报文不同。所以图像能力以工具形式提供。

用法：
  python ark_image.py --prompt "一只橘猫坐在书桌前，简笔画风格"
  python ark_image.py --prompt "..." --size 2048x2048 --n 3 --out D:\\pics
  python ark_image.py --prompt "..." --model doubao-seedream-5-0-pro-260628 --watermark
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

BASE = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
CREDS = os.path.expanduser(r"~\.dsh\.credentials.yaml")
CTX = ssl.create_default_context()
DEFAULT_MODEL = "doubao-seedream-5-0-pro-260628"


def api_key() -> str:
    m = re.search(r"(?m)^\s*ARK_API_KEY\s*:\s*(.+?)\s*$",
                  io.open(CREDS, encoding="utf-8", errors="replace").read())
    if not m:
        sys.exit("凭据库里没有 ARK_API_KEY")
    return m.group(1).strip().strip('"').strip("'")


def sniff(raw: bytes) -> str:
    """按魔数判断真实图片格式——API 常返回 jpeg，直接存 .png 会得到假后缀文件。"""
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if raw[:2] == b"\xff\xd8":
        return "jpg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return "bin"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--size", default="1024x1024", help="如 1024x1024 / 2048x2048 / 2K / 4K")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--out", default=os.getcwd(), help="输出目录或文件名前缀")
    ap.add_argument("--watermark", action="store_true", help="加 AI 生成水印（默认不加）")
    ap.add_argument("--seed", type=int, default=None, help="固定种子可复现")
    a = ap.parse_args()

    key = api_key()
    payload = {"model": a.model, "prompt": a.prompt, "size": a.size,
               "response_format": "url", "n": a.n, "watermark": a.watermark}
    if a.seed is not None:
        payload["seed"] = a.seed
    req = urllib.request.Request(BASE, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300, context=CTX) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = re.sub(r"\s+", " ", e.read(400).decode("utf-8", "replace"))
        sys.exit(f"❌ HTTP {e.code}: {body}")

    usage = data.get("usage", {})
    print(f"模型 {a.model} · {a.size} · {a.n} 张 · 耗时 {time.time()-t0:.1f}s")
    print(f"用量 {usage}")

    outdir = a.out if os.path.isdir(a.out) else os.path.dirname(os.path.abspath(a.out)) or os.getcwd()
    os.makedirs(outdir, exist_ok=True)
    stamp = time.strftime("%m%d-%H%M%S")
    for i, item in enumerate(data.get("data", []), 1):
        raw = None
        if item.get("url"):
            raw = urllib.request.urlopen(item["url"], timeout=120, context=CTX).read()
        elif item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
        if not raw:
            print(f"  {i}: 没有拿到图像数据"); continue
        ext = sniff(raw)
        path = os.path.join(outdir, f"seedream-{stamp}-{i}.{ext}")
        open(path, "wb").write(raw)
        print(f"  ✅ {path}")
        print(f"     {len(raw):,} 字节 · {ext.upper()} · sha256={hashlib.sha256(raw).hexdigest()[:16]}…")
        if item.get("revised_prompt"):
            print(f"     改写后的 prompt：{item['revised_prompt'][:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
