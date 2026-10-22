#!/usr/bin/env python3
"""Export auto-processed images and a reproducible manifest without MinIO."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.img_adjust import is_supported_image, process_image_with_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source, target = args.input.resolve(), args.output.resolve()
    if not source.is_dir() or source == target:
        parser.error("输入必须为目录，输出目录必须与输入不同")
    files = sorted((p for p in source.iterdir() if p.is_file() and is_supported_image(p.name)),
                   key=lambda p: (0, int(p.stem)) if p.stem.isdigit() else (1, p.name))
    if not files:
        parser.error("输入目录没有支持的图片")
    outputs = [target / f"{i:03d}_{p.stem}_auto.jpg" for i, p in enumerate(files, 1)]
    manifest_path = target / "处理记录.json"
    if manifest_path.exists() or any(p.exists() for p in outputs):
        parser.error("输出已存在，请选择新的输出目录以保留历史送测版本")
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for src, dst in zip(files, outputs):
        report = process_image_with_report(str(src), str(dst), mode="auto")
        records.append({"source_name": src.name, "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                        "output_name": dst.name, "output_sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
                        "processing": report})
        # Save progress so a later failure does not discard successful image records.
        manifest_path.write_text(json.dumps({"source_directory": str(source), "images": records},
                                           ensure_ascii=False, indent=2) + "\n")
        print(f"{src.name}: {report['label']}")
    print(dict(Counter(item['processing']['category'] for item in records)))
    print(manifest_path)


if __name__ == "__main__":
    main()
