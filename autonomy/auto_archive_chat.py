#!/usr/bin/env python3
"""
对话自动归档脚本
每次对话结束后运行，把当前对话记录归档到原始层
"""
import os
import subprocess, sys, json, hashlib
from datetime import datetime
from pathlib import Path

ARCHIVE_ROOT = Path(__file__).parent.parent / "archive" / "00-原始层"
SESSION_DIR = Path.home() / ".super_doubao" / "super-doubao-runtime" / "workspace" / ".sessions"

def archive_current_session():
    """归档当前会话记录"""
    today = datetime.now().strftime("%Y-%m-%d")
    month_dir = ARCHIVE_ROOT / datetime.now().strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    
    archived = 0
    if SESSION_DIR.exists():
        for session_dir in SESSION_DIR.iterdir():
            if session_dir.is_dir():
                target = month_dir / f"session_{session_dir.name}_{today}.tar.gz"
                if not target.exists():
                    subprocess.run(["tar", "-czf", str(target), "-C", str(SESSION_DIR), session_dir.name],
                       capture_output=True, timeout=60)
                    if target.exists():
                        archived += 1
    
    print(f"归档会话: {archived}个")
    return archived

if __name__ == "__main__":
    archive_current_session()
