---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_28baee4a86a911f18108525400287e28
    ReservedCode1: Q3LpLavghLj6BrB+kjS2Ft65N5E+nXMgbYW0RcyIg8jT7LTWo/P6c4/yMx5YXzWnA8zPIec8ZDkj2Hwm9EJ1yDBEbqYZdJ0R759gV+KeGuNsI3eWgBhUbiKbGm8Sv2itU6didZvgY5qCbLz29yZuyxh3Woq9rcbUJXZmatcNwc9fjLFcl+0Esgzga5I=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_28baee4a86a911f18108525400287e28
    ReservedCode2: Q3LpLavghLj6BrB+kjS2Ft65N5E+nXMgbYW0RcyIg8jT7LTWo/P6c4/yMx5YXzWnA8zPIec8ZDkj2Hwm9EJ1yDBEbqYZdJ0R759gV+KeGuNsI3eWgBhUbiKbGm8Sv2itU6didZvgY5qCbLz29yZuyxh3Woq9rcbUJXZmatcNwc9fjLFcl+0Esgzga5I=
---

# Story Parser | 小说解析器

## Overview

The Story Parser is the entry point of the AI_Manga_Studio pipeline. It ingests novels in various formats (plain text, DOCX, PDF, EPUB) and produces a structured representation with chapter boundaries, scene segmentation, character appearances, dialogue blocks, action descriptions, and temporal markers.

## Responsibilities

- Parse novel files into machine-readable structured data
- Detect chapter boundaries (numbered, titled, or implicit)
- Segment chapters into scenes based on location changes, time jumps, and POV shifts
- Extract character mentions and dialogue with speaker attribution
- Identify action descriptions and environmental details
- Build a chronological event timeline across the entire narrative

## Input

- **File formats**: `.txt`, `.docx`, `.pdf`, `.epub`
- **Content**: Long-form narrative fiction (novel, web novel, light novel)
- **Size**: Designed for 100K–1M+ character novels

## Output

Structured JSON with the following schema:

```json
{
  "novel_title": "Heavenly Sword",
  "total_chapters": 120,
  "total_scenes": 847,
  "characters": ["Ye Fan", "Lin Xue", "Master Zhang"],
  "chapters": [
    {
      "chapter_id": 12,
      "title": "The Forest Encounter",
      "scenes": [
        {
          "scene_id": 3,
          "location": "Dark Forest — Ancient Ruins",
          "time_of_day": "night",
          "characters_present": ["Ye Fan", "Lin Xue"],
          "dialogues": [
            {
              "speaker": "Ye Fan",
              "text": "Stay behind me. I sense something ahead.",
              "emotion": "alert"
            },
            {
              "speaker": "Lin Xue",
              "text": "Is it the beast from before?",
              "emotion": "fearful"
            }
          ],
          "actions": [
            "Ye Fan draws his sword, a faint blue glow emanating from the blade",
            "Lin Xue steps back, her hand reaching for a talisman in her sleeve"
          ],
          "atmosphere": "tense, dark, ancient ruins under moonlight",
          "narrative_summary": "The pair discovers an ancient ruin while fleeing pursuers..."
        }
      ]
    }
  ],
  "timeline": [
    {
      "event_id": 1,
      "chapter": 1,
      "scene": 1,
      "description": "Ye Fan discovers the ancient sword in his family's ancestral hall",
      "characters": ["Ye Fan"],
      "chronological_order": 1
    }
  ]
}
```

## Workflow

```
1. File Ingestion
   → Detect file format
   → Extract raw text (OCR for scanned PDFs if needed)
   → Normalize encoding to UTF-8

2. Chapter Detection
   → Pattern matching for chapter headers (e.g., "Chapter 12", "第12章")
   → Heuristic detection for unconventional formats
   → Manual override via configuration

3. Scene Segmentation
   → LLM-based analysis per chapter
   → Detect scene breaks by: location change, time skip, POV switch, section break markers
   → Assign scene IDs and metadata

4. Character Extraction
   → Identify all named entities (characters)
   → Track first appearance and cumulative mentions
   → Assign unique character IDs

5. Dialogue Extraction
   → Detect quotation marks and dialogue patterns
   → Attribute each dialogue segment to a speaker
   → Annotate with inferred emotion and context

6. Action & Environment Extraction
   → Separate action descriptions from narration
   → Extract environmental details (location, time, atmosphere)
   → Tag key visual elements for later image generation

7. Timeline Construction
   → Order all scenes chronologically
   → Build event index for cross-referencing
   → Detect flashbacks and non-linear narrative sections
```

## API

```python
class StoryParser:
    async def parse(self, file_path: str, config: ParseConfig = None) -> NovelStructure
    async def parse_chapter(self, novel_id: str, chapter_idx: int) -> Chapter
    async def get_timeline(self, novel_id: str) -> Timeline
    async def search_scenes(self, novel_id: str, query: SceneQuery) -> List[Scene]
```

## Future

- Support for multi-POV tracking with character-specific timelines
- Visual relationship graph generation from narrative data
- Integration with external knowledge bases for world-building
- Incremental parsing (only re-parse modified chapters)
- Support for script/screenplay formats
*（内容由AI生成，仅供参考）*
