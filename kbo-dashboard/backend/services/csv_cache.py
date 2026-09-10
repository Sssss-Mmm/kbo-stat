"""CSV 교체·생성·삭제를 감지하는 파일 버전."""
from pathlib import Path


def file_versions(paths: list[Path]) -> tuple:
    versions = []
    for path in paths:
        try:
            stat = path.stat()
            versions.append((stat.st_mtime_ns, stat.st_size, stat.st_ino))
        except FileNotFoundError:
            versions.append(None)
    return tuple(versions)
