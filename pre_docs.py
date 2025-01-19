import shutil
from pathlib import Path
from typing import Iterable

SRC = Path(__file__).parent
DOCS_DIR = SRC / "docs"
IGNORED_MD_DIRECTORIES = [".pytest_cache", "test", "dist"]

FILENAME_RENAME = {"readme.md": "index.md"}


def ignore_md_path(rel_path: str) -> bool:
    return any(f"{d}/" in rel_path for d in IGNORED_MD_DIRECTORIES)


def add_dest_paths(src_path: Path, md_dest_path: Path) -> Iterable[Path]:
    if new_name := FILENAME_RENAME.get(md_dest_path.name):
        yield md_dest_path.parent / new_name
    yield md_dest_path


def move_md_files():
    for md_src_path in SRC.rglob("*.md"):
        rel_path = str(md_src_path.relative_to(SRC))
        if md_src_path.is_relative_to(DOCS_DIR) or ignore_md_path(rel_path):
            continue
        md_dest_path = DOCS_DIR / rel_path
        for final_dest_path in add_dest_paths(md_src_path, md_dest_path):
            final_dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(md_src_path, final_dest_path)


if __name__ == "__main__":
    move_md_files()
