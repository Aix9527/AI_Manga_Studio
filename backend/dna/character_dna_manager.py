"""
V3.0 Layer 3 — Character DNA Manager

Singleton registry for all character DNA definitions.
All downstream modules query this manager instead of regenerating character data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from backend.dna.character_dna import CharacterDNA


class CharacterDNAManager:
    """Singleton registry for CharacterDNA instances.

    Usage:
        mgr = CharacterDNAManager.instance()
        mgr.register(CharacterDNA(...))
        dna = mgr.get("char_001")
        prompt = dna.get_prompt_context()
    """

    _instance: Optional["CharacterDNAManager"] = None

    def __init__(self):
        self._registry: Dict[str, CharacterDNA] = {}

    @classmethod
    def instance(cls) -> "CharacterDNAManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Registration ──────────────────────────────────────

    def register(self, dna: CharacterDNA) -> None:
        """Register or update a character DNA."""
        self._registry[dna.character_id] = dna
        logger.info(f"CharacterDNA: Registered '{dna.name}' (id={dna.character_id})")

    def register_many(self, dnas: List[CharacterDNA]) -> None:
        for dna in dnas:
            self.register(dna)

    # ── Retrieval ─────────────────────────────────────────

    def get(self, character_id: str) -> Optional[CharacterDNA]:
        """Get full DNA by character_id."""
        return self._registry.get(character_id)

    def get_by_name(self, name: str) -> Optional[CharacterDNA]:
        """Find DNA by character name."""
        for dna in self._registry.values():
            if dna.name == name:
                return dna
        return None

    def get_all(self) -> Dict[str, CharacterDNA]:
        """Return all registered DNAs."""
        return dict(self._registry)

    def get_names(self) -> List[str]:
        """Return all registered character names."""
        return [dna.name for dna in self._registry.values()]

    # ── Specialized accessors ─────────────────────────────

    def get_face_embedding(self, character_id: str) -> str:
        """Get face embedding path for PuLID/Consistency injection."""
        dna = self.get(character_id)
        return dna.face_embedding_path if dna else ""

    def get_lora_path(self, character_id: str) -> str:
        """Get LoRA model path."""
        dna = self.get(character_id)
        return dna.lora_path if dna else ""

    def get_prompt_context(self, character_id: str) -> str:
        """Get the fixed character prompt fragment."""
        dna = self.get(character_id)
        return dna.get_prompt_context() if dna else ""

    def get_seed(self, character_id: str) -> int:
        """Get fixed generation seed."""
        dna = self.get(character_id)
        return dna.seed if dna else 42

    def get_voice_id(self, character_id: str) -> str:
        """Get CosyVoice voice ID."""
        dna = self.get(character_id)
        return dna.voice_id if dna else ""

    # ── Persistence ───────────────────────────────────────

    def save_to_db(self, db_path: str = "") -> None:
        """Save all DNA entries to SQLite database."""
        if not db_path:
            return

        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS character_dna (
                character_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                data_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for dna in self._registry.values():
            conn.execute(
                "INSERT OR REPLACE INTO character_dna (character_id, name, data_json) VALUES (?, ?, ?)",
                (dna.character_id, dna.name, json.dumps(dna.to_dict(), ensure_ascii=False)),
            )
        conn.commit()
        conn.close()
        logger.info(f"CharacterDNA: Saved {len(self._registry)} entries to {db_path}")

    def load_from_db(self, db_path: str) -> None:
        """Load all DNA entries from SQLite database."""
        if not os.path.isfile(db_path):
            logger.warning(f"CharacterDNA: DB not found: {db_path}")
            return

        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT character_id, data_json FROM character_dna").fetchall()
        for character_id, data_json in rows:
            data = json.loads(data_json)
            dna = CharacterDNA.from_dict(data)
            self._registry[character_id] = dna
        conn.close()
        logger.info(f"CharacterDNA: Loaded {len(rows)} entries from {db_path}")

    def save_to_json(self, json_path: str) -> None:
        """Export all DNA entries to a JSON file."""
        data = {cid: dna.to_dict() for cid, dna in self._registry.items()}
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"CharacterDNA: Exported {len(data)} entries to {json_path}")

    def load_from_json(self, json_path: str) -> None:
        """Import DNA entries from a JSON file."""
        if not os.path.isfile(json_path):
            logger.warning(f"CharacterDNA: JSON not found: {json_path}")
            return
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for cid, d in data.items():
            dna = CharacterDNA.from_dict(d)
            dna.character_id = cid
            self._registry[cid] = dna
        logger.info(f"CharacterDNA: Imported {len(data)} entries from {json_path}")

    def __len__(self) -> int:
        return len(self._registry)
