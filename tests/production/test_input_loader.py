from pathlib import Path
from hashlib import sha256
import os

import pytest

from backend.production.contracts import InputType
from backend.production.input_loader import InputDecodeError, detect_input_type, load_input


def test_plain_chinese_txt_is_novel(tmp_path: Path):
    """Catches the bug where every .txt file is classified as a script."""
    source = tmp_path / "归墟第一部.txt"
    source.write_text("第一章 归来\n潮水吞没了旧城。", encoding="utf-8")

    assert detect_input_type(str(source)) is InputType.NOVEL


def test_load_input_returns_chapters_and_chinese_character_count(tmp_path: Path):
    """Catches loss of chapter metadata and under-counting Chinese text."""
    source = tmp_path / "book.txt"
    source.write_text(
        "第一章 潮声\n潮水吞没旧城。\n第二章 灯塔\n灯塔重新亮起。",
        encoding="utf-8",
    )

    loaded = load_input(str(source))

    assert [chapter.title for chapter in loaded.chapters] == [
        "第一章 潮声",
        "第二章 灯塔",
    ]
    assert loaded.contract.chapter_count == 2
    assert loaded.contract.total_words == 24


def test_gb18030_chinese_novel_is_decoded_with_report(tmp_path: Path):
    source = tmp_path / "贪狼.txt"
    source.write_bytes("第一章 贪狼\n雨夜中的枪声。".encode("gb18030"))

    loaded = load_input(str(source))

    assert loaded.chapters[0].title.startswith("第一章")
    assert loaded.contract.metadata["encoding"] == "gb18030"
    assert loaded.contract.metadata["sha256"] == sha256(source.read_bytes()).hexdigest()
    assert loaded.contract.metadata["source_size_bytes"] == source.stat().st_size


def test_binary_or_nul_heavy_input_is_rejected(tmp_path: Path):
    source = tmp_path / "not-a-novel.txt"
    source.write_bytes(b"\x00" * 64 + b"hello")

    with pytest.raises(InputDecodeError, match="binary"):
        load_input(str(source))


def test_gb18030_ideographic_space_garbage_is_rejected(tmp_path: Path):
    source = tmp_path / "garbage.txt"
    # 0x81 0x40 is valid GB18030 but decodes to an ideographic space, not text.
    source.write_bytes(b"\x81\x40")

    with pytest.raises(InputDecodeError, match="reliably decode"):
        load_input(str(source))


def test_user_supplied_novel_smoke_is_read_only_when_available():
    source = Path(r"D:\番茄小说下载器\代号：贪狼 - 梦醉孤新.txt")
    if os.environ.get("RUN_USER_NOVEL_SMOKE") != "1" or not source.is_file():
        pytest.skip("set RUN_USER_NOVEL_SMOKE=1 to read the user novel")

    before = sha256(source.read_bytes()).hexdigest()
    loaded = load_input(str(source))

    assert loaded.contract.metadata["sha256"] == before
    assert loaded.contract.metadata["encoding"] in {"utf-8-sig", "utf-8", "gb18030"}
    assert loaded.contract.chapter_count >= 1
    assert sha256(source.read_bytes()).hexdigest() == before
