"""SQLite-backed character repository using the existing orchestration DB."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from backend.characters.models import (
    Character, CharacterTrait, CharacterImage, CharacterCostume,
    CharacterRelationship, CharacterEmbedding,
    Appearance, FaceAppearance, BodyAppearance, HairAppearance,
    Personality, CombatStyle,
)


class CharacterRepository:
    def __init__(self, db_path: str = "storage/orchestrator.db"):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def initialize_schema(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS characters (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    aliases TEXT DEFAULT '[]',
                    species TEXT DEFAULT 'human',
                    gender TEXT DEFAULT '',
                    age INTEGER DEFAULT 0,
                    role TEXT DEFAULT '',
                    archetype TEXT DEFAULT '',
                    appearance TEXT DEFAULT '{}',
                    personality TEXT DEFAULT '{}',
                    combat_style TEXT DEFAULT '{}',
                    backstory TEXT DEFAULT '',
                    goal TEXT DEFAULT '',
                    arc_description TEXT DEFAULT '',
                    novel_id TEXT DEFAULT '',
                    chapter_introduced INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    version INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS character_traits (
                    id TEXT PRIMARY KEY,
                    character_id TEXT NOT NULL,
                    trait_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    intensity REAL DEFAULT 1.0,
                    source_chapter INTEGER DEFAULT 0,
                    source_evidence TEXT DEFAULT '',
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS character_images (
                    id TEXT PRIMARY KEY,
                    character_id TEXT NOT NULL,
                    image_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    prompt_used TEXT DEFAULT '',
                    generation_params TEXT DEFAULT '',
                    is_primary INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS character_costumes (
                    id TEXT PRIMARY KEY,
                    character_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    chapter_range TEXT DEFAULT '',
                    season TEXT DEFAULT '',
                    occasion TEXT DEFAULT '',
                    image_id TEXT DEFAULT '',
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS character_relationships (
                    id TEXT PRIMARY KEY,
                    character_id TEXT NOT NULL,
                    related_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    intensity REAL DEFAULT 1.0,
                    chapter_established INTEGER DEFAULT 0,
                    history TEXT DEFAULT '',
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS character_embeddings (
                    id TEXT PRIMARY KEY,
                    character_id TEXT NOT NULL,
                    embedding_type TEXT NOT NULL,
                    model TEXT NOT NULL,
                    vector BLOB DEFAULT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(name);
                CREATE INDEX IF NOT EXISTS idx_characters_novel ON characters(novel_id);
                CREATE INDEX IF NOT EXISTS idx_traits_char ON character_traits(character_id);
                CREATE INDEX IF NOT EXISTS idx_images_char ON character_images(character_id);
                CREATE INDEX IF NOT EXISTS idx_relationships_char ON character_relationships(character_id);
                CREATE INDEX IF NOT EXISTS idx_embeddings_char ON character_embeddings(character_id);
            """)

    # ── Characters ──

    def save_character(self, ch: Character) -> Character:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO characters
                    (id, name, aliases, species, gender, age, role, archetype,
                     appearance, personality, combat_style, backstory, goal,
                     arc_description, novel_id, chapter_introduced, status,
                     version, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ch.id, ch.name, json.dumps(ch.aliases), ch.species, ch.gender, ch.age,
                ch.role, ch.archetype, json.dumps(ch.appearance.to_dict() if hasattr(ch.appearance, 'to_dict') else {}),
                json.dumps(ch.personality.to_dict() if hasattr(ch.personality, 'to_dict') else {}),
                json.dumps(ch.combat_style.to_dict() if hasattr(ch.combat_style, 'to_dict') else {}),
                ch.backstory, ch.goal, ch.arc_description,
                ch.novel_id, ch.chapter_introduced, ch.status,
                ch.version, ch.created_at, ch.updated_at,
            ))
        return ch

    def get_character(self, character_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
        return dict(row) if row else None

    def list_characters(self, novel_id: str = "", status: str = "") -> list[dict]:
        query = "SELECT * FROM characters WHERE 1=1"
        params: list = []
        if novel_id:
            query += " AND novel_id = ?"
            params.append(novel_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY name"
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    def search_characters(self, keyword: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM characters WHERE name LIKE ? OR backstory LIKE ? OR role LIKE ?",
                (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_character(self, character_id: str) -> bool:
        with self._conn() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        return cursor.rowcount > 0

    # ── Traits ──

    def save_trait(self, t: CharacterTrait) -> CharacterTrait:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO character_traits
                VALUES (?,?,?,?,?,?,?,?)
            """, (t.id, t.character_id, t.trait_type, t.name, t.value, t.intensity, t.source_chapter, t.source_evidence))
        return t

    def list_traits(self, character_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM character_traits WHERE character_id = ? ORDER BY trait_type, name", (character_id,)).fetchall()
        return [dict(r) for r in rows]

    # ── Images ──

    def save_image(self, img: CharacterImage) -> CharacterImage:
        with self._conn() as conn:
            if img.is_primary:
                conn.execute("UPDATE character_images SET is_primary = 0 WHERE character_id = ?", (img.character_id,))
            conn.execute("""
                INSERT OR REPLACE INTO character_images VALUES (?,?,?,?,?,?,?,?)
            """, (img.id, img.character_id, img.image_type, img.file_path, img.prompt_used, img.generation_params, 1 if img.is_primary else 0, img.created_at))
        return img

    def list_images(self, character_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM character_images WHERE character_id = ? ORDER BY is_primary DESC, created_at DESC", (character_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_image(self, image_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM character_images WHERE id = ?", (image_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_primary_image(self, character_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM character_images WHERE character_id = ? AND is_primary = 1", (character_id,)).fetchone()
        return dict(row) if row else None

    # ── Costumes ──

    def save_costume(self, c: CharacterCostume) -> CharacterCostume:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO character_costumes VALUES (?,?,?,?,?,?,?,?)
            """, (c.id, c.character_id, c.name, c.description, c.chapter_range, c.season, c.occasion, c.image_id))
        return c

    def list_costumes(self, character_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM character_costumes WHERE character_id = ? ORDER BY name", (character_id,)).fetchall()
        return [dict(r) for r in rows]

    # ── Relationships ──

    def save_relationship(self, rel: CharacterRelationship) -> CharacterRelationship:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO character_relationships VALUES (?,?,?,?,?,?,?,?)
            """, (rel.id, rel.character_id, rel.related_id, rel.relation_type, rel.description, rel.intensity, rel.chapter_established, rel.history))
        return rel

    def list_relationships(self, character_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT cr.*, c.name AS related_name
                FROM character_relationships cr
                LEFT JOIN characters c ON cr.related_id = c.id
                WHERE cr.character_id = ?
                ORDER BY cr.relation_type, c.name
            """, (character_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_relationship_graph(self, character_id: str, depth: int = 2) -> dict:
        """BFS graph of relationships."""
        graph: dict[str, list] = {}
        visited: set = set()
        queue: list = [(character_id, 0)]

        with self._conn() as conn:
            while queue:
                cid, d = queue.pop(0)
                if cid in visited or d > depth:
                    continue
                visited.add(cid)
                rows = conn.execute("""
                    SELECT related_id, relation_type, description FROM character_relationships WHERE character_id = ?
                """, (cid,)).fetchall()
                graph[cid] = [dict(r) for r in rows]
                for r in rows:
                    if r["related_id"] not in visited:
                        queue.append((r["related_id"], d + 1))
        return graph

    # ── Embeddings ──

    def save_embedding(self, emb: CharacterEmbedding) -> CharacterEmbedding:
        import struct
        packed = struct.pack(f"{len(emb.vector)}f", *emb.vector) if emb.vector else b""
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO character_embeddings VALUES (?,?,?,?,?,?)
            """, (emb.id, emb.character_id, emb.embedding_type, emb.model, packed, emb.created_at))
        return emb

    def get_embedding(self, character_id: str, embedding_type: str = "visual") -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM character_embeddings WHERE character_id = ? AND embedding_type = ? ORDER BY created_at DESC LIMIT 1",
                (character_id, embedding_type),
            ).fetchone()
        return dict(row) if row else None
