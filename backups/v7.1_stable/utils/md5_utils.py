"""
观尘子引擎 V7.1 - MD5与文件完整性工具
"""
import hashlib
import os
import json


class MD5Utils:
    """MD5计算与文件完整性校验工具"""

    @staticmethod
    def compute_file_md5(file_path: str, chunk_size: int = 8192) -> str:
        """计算文件MD5值"""
        if not os.path.exists(file_path):
            return ""
        md5_hash = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception:
            return ""

    @staticmethod
    def compute_string_md5(text: str) -> str:
        """计算字符串MD5值"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_json_md5(data: dict) -> str:
        """计算JSON对象的MD5（排序后序列化，确保一致性）"""
        sorted_json = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(sorted_json.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_file_md5(file_path: str, expected_md5: str) -> bool:
        """验证文件MD5是否匹配"""
        actual = MD5Utils.compute_file_md5(file_path)
        return actual == expected_md5 and actual != ""

    @staticmethod
    def batch_compute_md5(directory: str, extensions: list = None) -> dict:
        """批量计算目录下文件的MD5"""
        results = {}
        if not os.path.isdir(directory):
            return results
        for root, dirs, files in os.walk(directory):
            # 跳过隐藏目录和缓存
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for filename in files:
                if filename.startswith("."):
                    continue
                if extensions and not any(filename.endswith(ext) for ext in extensions):
                    continue
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, directory)
                results[rel_path] = {
                    "md5": MD5Utils.compute_file_md5(filepath),
                    "size": os.path.getsize(filepath),
                    "mtime": os.path.getmtime(filepath),
                }
        return results

    @staticmethod
    def compare_md5_sets(baseline: dict, current: dict) -> dict:
        """比较两组MD5快照，返回变更差异"""
        added = {}
        removed = {}
        modified = {}
        unchanged = {}

        for path, info in current.items():
            if path not in baseline:
                added[path] = info
            elif baseline[path].get("md5") != info.get("md5"):
                modified[path] = {
                    "old": baseline[path],
                    "new": info,
                }
            else:
                unchanged[path] = info

        for path, info in baseline.items():
            if path not in current:
                removed[path] = info

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "unchanged": unchanged,
            "summary": {
                "total_baseline": len(baseline),
                "total_current": len(current),
                "added_count": len(added),
                "removed_count": len(removed),
                "modified_count": len(modified),
                "unchanged_count": len(unchanged),
            },
        }
