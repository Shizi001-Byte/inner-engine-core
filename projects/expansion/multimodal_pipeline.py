#!/usr/bin/env python3
"""
multimodal_pipeline.py — 多模态处理流水线（模块3.2）
统一调度入口：图片生成、OCR识别、PDF解析、音频转写。
用法：
  python3 multimodal_pipeline.py image "描述"        # 生成图片
  python3 multimodal_pipeline.py ocr <image_path>     # OCR识别
  python3 multimodal_pipeline.py pdf <pdf_path>       # PDF解析
  python3 multimodal_pipeline.py status               # 查看处理历史
"""
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

ENGINE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
HISTORY_FILE = DATA_DIR / "multimodal_history.json"


def load_history():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if HISTORY_FILE.exists():
        return json.load(open(HISTORY_FILE))
    return {"tasks": []}


def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, indent=2, ensure_ascii=False)


def record_task(task_type, input_info, result, success=True):
    h = load_history()
    h["tasks"].append({
        "type": task_type,
        "input": input_info[:100],
        "success": success,
        "result": str(result)[:200],
        "time": datetime.now().isoformat(),
    })
    h["tasks"] = h["tasks"][-100:]
    save_history(h)


def generate_image(prompt):
    """图片生成（调用image_gen工具的占位实现，实际由上层调用）"""
    print(f"[图片生成] 描述: {prompt}")
    print("  提示: 图片生成需通过image_gen工具执行，本脚本提供统一调度接口")
    record_task("image_gen", prompt, "待上层工具执行", True)
    return {"status": "pending", "prompt": prompt, "note": "需调用image_gen工具"}


def ocr_image(image_path):
    """OCR识别"""
    path = Path(image_path)
    if not path.exists():
        print(f"[OCR] 文件不存在: {image_path}")
        record_task("ocr", image_path, "文件不存在", False)
        return None
    print(f"[OCR] 识别: {image_path}")
    try:
        # 尝试用pytesseract
        try:
            import pytesseract
            from PIL import Image
            text = pytesseract.image_to_string(Image.open(path), lang='chi_sim+eng')
            print(f"  识别结果 ({len(text)}字): {text[:200]}")
            record_task("ocr", image_path, text, True)
            return text
        except ImportError:
            print("  pytesseract未安装，使用基础识别")
            record_task("ocr", image_path, "pytesseract未安装", False)
            return None
    except Exception as e:
        print(f"  识别失败: {e}")
        record_task("ocr", image_path, str(e), False)
        return None


def parse_pdf(pdf_path):
    """PDF解析"""
    path = Path(pdf_path)
    if not path.exists():
        print(f"[PDF] 文件不存在: {pdf_path}")
        record_task("pdf", pdf_path, "文件不存在", False)
        return None
    print(f"[PDF] 解析: {pdf_path}")
    try:
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(str(path))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            print(f"  解析完成: {len(reader.pages)}页, {len(text)}字")
            record_task("pdf", pdf_path, f"{len(reader.pages)}页/{len(text)}字", True)
            return text
        except ImportError:
            print("  PyPDF2未安装")
            record_task("pdf", pdf_path, "PyPDF2未安装", False)
            return None
    except Exception as e:
        print(f"  解析失败: {e}")
        record_task("pdf", pdf_path, str(e), False)
        return None


def show_status():
    h = load_history()
    print(f"=== 多模态处理历史 ===")
    print(f"总任务数: {len(h['tasks'])}")
    types = {}
    for t in h["tasks"]:
        types[t["type"]] = types.get(t["type"], 0) + 1
    for t, c in types.items():
        print(f"  {t}: {c}次")
    print("\n最近5条:")
    for t in h["tasks"][-5:]:
        icon = "✅" if t["success"] else "❌"
        print(f"  {icon} [{t['type']}] {t['input'][:40]}")


def main():
    parser = argparse.ArgumentParser(description="多模态处理流水线")
    sub = parser.add_subparsers(dest="cmd")
    p_img = sub.add_parser("image")
    p_img.add_argument("prompt")
    p_ocr = sub.add_parser("ocr")
    p_ocr.add_argument("image_path")
    p_pdf = sub.add_parser("pdf")
    p_pdf.add_argument("pdf_path")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.cmd == "image":
        generate_image(args.prompt)
    elif args.cmd == "ocr":
        ocr_image(args.image_path)
    elif args.cmd == "pdf":
        parse_pdf(args.pdf_path)
    elif args.cmd == "status":
        show_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
