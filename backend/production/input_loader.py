from __future__ import annotations

import json
import logging
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from backend.production.contracts import (
    Chapter,
    InputContract,
    InputType,
    LoadedInput,
)

logger = logging.getLogger(__name__)


class InputDecodeError(ValueError):
    """Raised when a textual source cannot be decoded safely and reliably."""


CHAPTER_HEADING = re.compile(
    r"(?m)^(第[零〇一二三四五六七八九十百千万两\d]+[章节卷部回][^\r\n]*)$"
)


def detect_input_type(path_str: str) -> InputType:
    path = Path(path_str)
    suffix = path.suffix.lower()
    stem = path.stem.lower()

    if suffix == ".xml":
        return InputType.STORYBOARD
    if suffix == ".html":
        # 分镜 HTML（含 seq-N 章节 + S01-1 镜头号）识别为 STORYBOARD
        try:
            full = path.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            full = _read_head(path, 200000)
        if re.search(r'id="seq-\d+"', full) and re.search(r"S\d+-\d+", full):
            return InputType.STORYBOARD
        return InputType.UNKNOWN
    if stem.endswith("_script") or suffix == ".fountain":
        return InputType.SCRIPT
    if suffix in (".txt", ".md"):
        content_preview = _read_head(path, 2000)
        return InputType.SCRIPT if _has_script_markers(content_preview) else InputType.NOVEL
    return InputType.UNKNOWN


def load_input(path_str: str) -> LoadedInput:
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    input_type = detect_input_type(path_str)
    if input_type == InputType.NOVEL:
        return _load_novel(path, input_type)
    if input_type == InputType.SCRIPT:
        return _load_script(path, input_type)
    if input_type == InputType.STORYBOARD:
        return _load_storyboard(path, input_type)
    raise ValueError(f"Unsupported input type: {path.suffix}")


def _load_novel(path: Path, input_type: InputType) -> LoadedInput:
    text, source_metadata = _read_text_with_metadata(path)
    chapters = _split_chapters(text, fallback_title=path.stem)
    title = chapters[0].title if chapters else path.stem
    contract = InputContract(
        path=str(path),
        type=input_type,
        title=title,
        chapter_count=len(chapters),
        total_words=_count_characters(text),
        metadata={
            "line_count": len(text.splitlines()),
            "format": "novel",
            **source_metadata,
        },
    )
    return LoadedInput(contract=contract, text=text, chapters=chapters)


def _load_script(path: Path, input_type: InputType) -> LoadedInput:
    text, source_metadata = _read_text_with_metadata(path)
    title = path.stem.removesuffix("_script")
    chapter = Chapter(
        index=1,
        title=title,
        content=text,
        word_count=_count_characters(text),
    )
    contract = InputContract(
        path=str(path),
        type=input_type,
        title=title,
        chapter_count=1,
        total_words=_count_characters(text),
        metadata={
            "line_count": len(text.splitlines()),
            "format": "script",
            **source_metadata,
        },
    )
    return LoadedInput(contract=contract, text=text, chapters=[chapter])


def _load_storyboard(path: Path, input_type: InputType) -> LoadedInput:
    content, source_metadata = _read_text_with_metadata(path)
    title = path.stem
    sequences = []
    if path.suffix.lower() == ".html":
        try:
            from backend.production.storyboard_loader import load_storyboard
            sb = load_storyboard(path)
            title = _storyboard_title(sb)
            sequences = sb.sequences
        except Exception as exc:  # noqa: BLE001 - keep raw HTML as fallback
            logger.warning("Storyboard parse failed (%s), keeping raw HTML", exc)
    contract = InputContract(
        path=str(path),
        type=input_type,
        title=title,
        total_words=_count_characters(content),
        metadata={
            "format": "storyboard",
            "sequences": len(sequences),
            **source_metadata,
        },
    )
    return LoadedInput(contract=contract, text=content)


def _storyboard_title(sb) -> str:
    # 优先取 HTML <title>（正片名），否则回退第一章标题
    if sb.source:
        try:
            html = Path(sb.source).read_text(encoding="utf-8-sig", errors="ignore")
            m = re.search(r"<title>(.*?)</title>", html, re.S)
            if m:
                title = m.group(1).strip()
                # 去掉"《》/— 全片分镜脚本"等后缀
                title = re.sub(r"[《》]|全片分镜脚本.*$|分镜脚本.*$", "", title).strip()
                title = title.rstrip("—–-· \t").strip()
                if title:
                    return title
        except OSError:
            pass
    for seq in sb.sequences:
        if seq.get("title"):
            return str(seq["title"]).split(" ")[0]
    return "归墟觉醒"


def _split_chapters(text: str, fallback_title: str) -> list[Chapter]:
    # ``Path.write_text`` and Windows downloads commonly contain CRLF.  Normalise
    # before applying the line-anchored heading expression so ``\r`` cannot keep
    # an otherwise valid Chinese heading from matching.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(CHAPTER_HEADING.finditer(text))
    if not matches:
        stripped = text.strip()
        return [
            Chapter(
                index=1,
                title=fallback_title,
                content=stripped,
                word_count=_count_characters(stripped),
            )
        ]

    chapters: list[Chapter] = []
    for index, match in enumerate(matches, start=1):
        content_start = match.end()
        content_end = matches[index].start() if index < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        chapters.append(
            Chapter(
                index=index,
                title=match.group(1).strip(),
                content=content,
                word_count=_count_characters(content),
            )
        )
    return chapters


def _read_text(path: Path) -> str:
    """Read text safely while retaining the legacy string-only helper API."""
    return _read_text_with_metadata(path)[0]


def _read_text_with_metadata(path: Path) -> tuple[str, dict[str, Any]]:
    raw = path.read_bytes()
    _reject_binary_content(raw, path)
    text, encoding = _decode_text(raw, path)
    return text, {
        "encoding": encoding,
        "sha256": sha256(raw).hexdigest(),
        "source_size_bytes": len(raw),
    }


def _decode_text(raw: bytes, path: Path) -> tuple[str, str]:
    attempted = ("utf-8-sig", "utf-8", "gb18030")
    failures: list[str] = []
    decoders: tuple[tuple[str, str], ...] = (
        ("utf-8-sig", "utf-8-sig"),
        ("utf-8", "utf-8"),
        ("gb18030", "gb18030"),
    )
    for label, codec in decoders:
        if label == "utf-8-sig" and not raw.startswith(b"\xef\xbb\xbf"):
            failures.append(label)
            continue
        try:
            text = raw.decode(codec, errors="strict")
        except UnicodeDecodeError:
            failures.append(label)
            continue
        if _looks_like_reliable_text(text):
            return text, label
        failures.append(label)
    raise InputDecodeError(
        f"Unable to reliably decode text input {path}; attempted encodings: "
        + ", ".join(attempted)
    )


def _reject_binary_content(raw: bytes, path: Path) -> None:
    if not raw:
        return
    nul_count = raw.count(b"\x00")
    if nul_count > max(1, len(raw) // 100):
        raise InputDecodeError(f"Input appears to be binary/NUL-heavy: {path}")
    control_count = sum(
        byte < 32 and byte not in (9, 10, 13) for byte in raw
    )
    if control_count > max(4, len(raw) // 20):
        raise InputDecodeError(f"Input appears to be binary: {path}")


def _looks_like_reliable_text(text: str) -> bool:
    if "\x00" in text or "\ufffd" in text:
        return False
    meaningful = [
        char for char in text if not char.isspace() and char.isprintable()
    ]
    # A lone GB18030 mapping is not evidence of a usable text document.  This
    # rejects binary fragments such as ``0x81 0x40`` that happen to decode to a
    # printable CJK code point, while any real novel has more than one glyph.
    if len(meaningful) < 2:
        return False
    controls = sum(
        ord(char) < 32 and char not in "\t\n\r" for char in text
    )
    return (
        controls <= max(2, len(text) // 100)
        and len(meaningful) == sum(not char.isspace() for char in text)
    )


def _read_head(path: Path, chars: int) -> str:
    try:
        # Type detection needs only a preview; avoid hashing/reading a whole
        # user novel before the explicit import step.
        with path.open("rb") as source:
            raw = source.read(max(chars * 4, 8192))
        _reject_binary_content(raw, path)
        # A byte preview can end in the middle of a UTF-8/GB18030 character.
        # Retrying up to the maximum four-byte sequence preserves strict decode
        # validation without ever reading the full source at this stage.
        for end in range(len(raw), max(-1, len(raw) - 4), -1):
            try:
                text, _ = _decode_text(raw[:end], path)
                return text[:chars]
            except InputDecodeError:
                continue
        return ""
    except (OSError, InputDecodeError):
        return ""


def _count_characters(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _has_script_markers(text: str) -> bool:
    markers = [
        "INT.",
        "EXT.",
        "SCENE",
        "CHARACTER",
        "DIALOGUE",
        "FADE IN",
        "FADE OUT",
        "CUT TO",
    ]
    upper = text.upper()
    return any(marker in upper for marker in markers)
