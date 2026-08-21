# Director Benchmark Dataset (Phase 10.8-A)

20 scenes derived from 《归墟觉醒·天倾》 (production_plan.json + gx_manifest.json)
for A/B evaluation of director providers:

- A group: rule-v2 (deterministic baseline)
- B group: LLM director (Qwen / OpenAI / Claude)

Each scene JSON: {scene_id, source_shot_id, shot: {...}, section_context: {...}}.
Run the A/B with: `python -m backend.director.benchmark --ab --limit 20`
