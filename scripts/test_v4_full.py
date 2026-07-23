# -*- coding: utf-8 -*-
"""
AI Manga Studio V4 - Comprehensive End-to-End Test

Tests all new modules with realistic fantasy battle chapter data.
"""

import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.unified_shot import (
    UnifiedShot, Camera, Emotion, Weather, TimeOfDay, Lighting, ShotStatus,
)
from backend.cinema_video_prompt_builder import (
    CinemaVideoPromptBuilder, ShotCinemaData,
)
from backend.enhanced_image_prompt_builder import EnhancedImagePromptBuilder
from backend.shot_table_generator import ShotTableGenerator
from backend.vfx_generator import VFXGenerator
from backend.i2v_generator import I2VGenerator
from backend.orchestrator_v4 import OrchestratorV4


def create_test_shots(test_dir):
    """Create 8 realistic shots for a fantasy battle chapter."""
    ch_dir = test_dir / "ch01" / "shots"
    ch_dir.mkdir(parents=True, exist_ok=True)

    shots_data = [
        {
            "chapter": 1, "scene": 1, "shot": 1,
            "camera": Camera.wide, "emotion": Emotion.fearful,
            "characters": ["Ye Fan"], "background": "Ancient county hall",
            "time_of_day": TimeOfDay.morning, "weather": Weather.clear,
            "lighting": Lighting.cinematic, "duration": 5.0,
            "narration": "County hall, runner rushes in sweating",
            "dialogue": "My lord! Do not!",
            "sfx": "Footsteps echoing", "camera_motion": "slow pan right",
        },
        {
            "chapter": 1, "scene": 1, "shot": 2,
            "camera": Camera.close, "emotion": Emotion.fearful,
            "characters": ["Runner"], "background": "County hall",
            "time_of_day": TimeOfDay.morning, "weather": Weather.clear,
            "lighting": Lighting.natural, "duration": 4.0,
            "narration": "Runner falls to knees before desk, hands waving wildly",
            "dialogue": "",
            "sfx": "Knees hitting floor", "camera_motion": "static",
        },
        {
            "chapter": 1, "scene": 1, "shot": 3,
            "camera": Camera.medium, "emotion": Emotion.neutral,
            "characters": ["Magistrate"], "background": "County hall",
            "time_of_day": TimeOfDay.morning, "weather": Weather.clear,
            "lighting": Lighting.natural, "duration": 5.0,
            "narration": "Magistrate writing, trying to grab brush and ink",
            "dialogue": "",
            "sfx": "Paper rustling", "camera_motion": "slow push in",
        },
        {
            "chapter": 1, "scene": 1, "shot": 4,
            "camera": Camera.close, "emotion": Emotion.angry,
            "characters": ["Magistrate"], "background": "County hall",
            "time_of_day": TimeOfDay.morning, "weather": Weather.clear,
            "lighting": Lighting.cinematic, "duration": 4.0,
            "narration": "Magistrate eyes sharp with scrutiny, mouth a straight line",
            "dialogue": "How can you imagine the Black Wind Fortress cruelty?",
            "sfx": "Desk slam", "camera_motion": "slow dolly in",
        },
        {
            "chapter": 1, "scene": 1, "shot": 5,
            "camera": Camera.tracking, "emotion": Emotion.determined,
            "characters": ["Ye Fan", "Magistrate"], "background": "Hall to doorway",
            "time_of_day": TimeOfDay.morning, "weather": Weather.clear,
            "lighting": Lighting.natural, "duration": 6.0,
            "narration": "Ye Fan stands from desk, walks to doorway",
            "dialogue": "Prepare horse.",
            "sfx": "Chair scraping", "camera_motion": "lateral tracking",
        },
        {
            "chapter": 1, "scene": 2, "shot": 1,
            "camera": Camera.wide, "emotion": Emotion.excited,
            "characters": ["Ye Fan"], "background": "County square",
            "time_of_day": TimeOfDay.afternoon, "weather": Weather.clear,
            "lighting": Lighting.natural, "duration": 5.0,
            "narration": "Ye Fan rides into square, sunlight on armor",
            "dialogue": "",
            "sfx": "Horse hooves", "camera_motion": "crane up",
        },
        {
            "chapter": 1, "scene": 2, "shot": 2,
            "camera": Camera.medium, "emotion": Emotion.fearful,
            "characters": ["Ye Fan"], "background": "County square",
            "time_of_day": TimeOfDay.afternoon, "weather": Weather.clear,
            "lighting": Lighting.natural, "duration": 5.0,
            "narration": "Ye Fan reins in horse, scans surroundings",
            "dialogue": "Where are the Black Wind Fortress men?",
            "sfx": "Horse neigh", "camera_motion": "slow push in",
        },
        {
            "chapter": 1, "scene": 2, "shot": 3,
            "camera": Camera.drone, "emotion": Emotion.surprised,
            "characters": ["Ye Fan"], "background": "Panoramic city view",
            "time_of_day": TimeOfDay.afternoon, "weather": Weather.clear,
            "lighting": Lighting.natural, "duration": 6.0,
            "narration": "Aerial view: square full of people, black smoke rising in distance",
            "dialogue": "",
            "sfx": "Crowd noise", "camera_motion": "drone fly-over",
        },
    ]

    saved_shots = []
    for sd in shots_data:
        shot = UnifiedShot(
            chapter=sd["chapter"],
            scene=sd["scene"],
            shot=sd["shot"],
            camera=sd["camera"],
            emotion=sd["emotion"],
            characters=sd["characters"],
            background=sd["background"],
            time_of_day=sd["time_of_day"],
            weather=sd["weather"],
            lighting=sd["lighting"],
            duration=sd["duration"],
            narration=sd["narration"],
            dialogue=sd["dialogue"],
            sfx=sd["sfx"],
            camera_motion=sd["camera_motion"],
            shot_id='ch{:02d}_sc{:02d}_sh{:03d}'.format(sd["chapter"], sd["scene"], sd["shot"]),
        )
        shot.to_json_file(str(ch_dir / 'shot_{:03d}.json'.format(sd["shot"])))
        saved_shots.append(shot)

    return saved_shots


def test_image_prompts(shots):
    """Test EnhancedImagePromptBuilder."""
    builder = EnhancedImagePromptBuilder(style="anime")
    all_pass = True
    for shot in shots:
        result = builder.build({
            "shot_id": shot.shot_id,
            "camera": str(shot.camera),
            "characters": shot.characters,
            "background": shot.background,
            "emotion": str(shot.emotion),
            "time_of_day": str(shot.time_of_day),
            "weather": str(shot.weather),
            "action": shot.narration,
            "expression": str(shot.emotion),
        })
        status = "OK" if result.quality_score >= 0.8 else "WARN"
        if result.quality_score < 0.8:
            all_pass = False
        print("    [{}] {} quality={} prompt_len={}".format(
            status, shot.shot_id, result.quality_score, len(result.positive_prompt)))
    return all_pass


def test_vfx(shots):
    """Test VFXGenerator."""
    gen = VFXGenerator()
    results = []
    for shot in shots:
        vfx = gen.generate({
            "shot_id": shot.shot_id,
            "emotion": str(shot.emotion),
            "actions": [shot.narration[:20]],
            "weather": str(shot.weather),
            "camera_movement": shot.camera_motion or "",
        })
        vfx_count = (len(vfx.dynamic_effects) + len(vfx.action_vfx) +
                     len(vfx.ambient_vfx) + len(vfx.camera_vfx))
        print("    {}: {} effects | {}...".format(
            shot.shot_id, vfx_count, vfx.combined_description[:40]))
        results.append(vfx)
    return results


def test_video_prompts(shots, vfx_results):
    """Test CinemaVideoPromptBuilder."""
    builder = CinemaVideoPromptBuilder()
    all_pass = True
    for shot, vfx in zip(shots, vfx_results):
        cd = ShotCinemaData(
            shot_id=shot.shot_id,
            chapter=shot.chapter,
            scene=shot.scene,
            shot_num=shot.shot,
            shot_type=str(shot.camera),
            camera_movement=shot.camera_motion or "",
            characters=shot.characters,
            emotion=str(shot.emotion),
            scene_description=shot.background,
            time_of_day=str(shot.time_of_day),
            weather=str(shot.weather),
            lighting=shot.lighting.value if hasattr(shot.lighting, "value") else str(shot.lighting),
            dialogue=shot.dialogue,
            sfx=shot.sfx or "",
            duration_sec=shot.duration,
        )
        vp = builder.build(cd)
        ok = vp.motion_strength > 0 and vp.motion_strength <= 1.0
        if not ok:
            all_pass = False
        print("    {}: motion={:.2f} fps={} dur={}s".format(
            shot.shot_id, vp.motion_strength, vp.fps_target, vp.duration_sec))
        print("      Camera: {}...".format(vp.camera_motion[:50]))
        print("      Action: {}...".format(vp.action_sequence[:50]))
    return all_pass


def test_shot_table(shots, vfx_results):
    """Test ShotTableGenerator."""
    gen = ShotTableGenerator()
    entries = []
    for shot, vfx in zip(shots, vfx_results):
        entries.append({
            "shot_number": shot.shot,
            "shot_type": str(shot.camera),
            "camera_angle": "eye_level",
            "camera_movement": shot.camera_motion or "",
            "visual_content": shot.narration,
            "dialogue": shot.dialogue,
            "lighting": shot.lighting.value if hasattr(shot.lighting, "value") else str(shot.lighting),
            "vfx": vfx.combined_description,
            "duration_sec": shot.duration,
            "transition_in": "cut",
            "transition_out": "cut",
            "emotion": str(shot.emotion),
            "notes": shot.background,
        })

    table_entries = gen.generate(entries)
    for e in table_entries:
        print("    Shot{:02d}: {}/{}/{} | {}... | {}s".format(
            e.shot_number, e.shot_type, e.camera_angle, e.camera_movement,
            e.visual_content[:30], e.duration_sec))

    # Export
    csv_path = os.path.join("output", "test_v4_full", "shot_table.csv")
    json_path = os.path.join("output", "test_v4_full", "shot_table.json")
    gen.export_as_excel_csv(table_entries, csv_path)
    gen.export_as_json(table_entries, json_path)
    csv_size = os.path.getsize(csv_path)
    json_size = os.path.getsize(json_path)
    print("    CSV: {} ({} bytes)".format(csv_path, csv_size))
    print("    JSON: {} ({} bytes)".format(json_path, json_size))

    return csv_size, json_size


def test_i2v_generator():
    """Test I2VGenerator template loading."""
    gen = I2VGenerator()
    ad_ok = gen._ad_template is not None
    wan_ok = gen._wan_template is not None
    print("    AnimateDiff template: {}".format("LOADED" if ad_ok else "NOT FOUND"))
    print("    Wan2.2 template: {}".format("LOADED" if wan_ok else "NOT FOUND"))
    if ad_ok:
        node_keys = list(gen._ad_template.keys())
        print("    AD template nodes: {}".format(len(node_keys)))
    return ad_ok


def test_orchestrator_v4(shots, test_dir):
    """Test OrchestratorV4 initialization and data conversions."""
    orch = OrchestratorV4(
        comfyui_url="http://127.0.0.1:8188",
        output_dir=str(test_dir),
        style="anime",
    )
    print("    OrchestratorV4 initialized: OK")

    # Test shot loading
    loaded = orch._load_project_shots(str(test_dir))
    print("    Loaded {} shots from disk".format(len(loaded)))

    # Test data conversions
    for shot in shots[:3]:
        img_dict = orch._shot_to_image_dict(shot)
        vfx_dict = orch._shot_to_vfx_dict(shot)
        cd = orch._shot_to_cinema_data(shot, None)
        tbl = orch._shot_to_table_dict(shot, None)
        print("    {}: img_keys={}, cinema={}, table={}".format(
            shot.shot_id, len(img_dict), cd.shot_type, tbl["shot_type"]))

    return True


def test_end_to_end_chain(shots):
    """Test full prompt chain: image -> vfx -> cinema -> video."""
    img_builder = EnhancedImagePromptBuilder(style="anime")
    vfx_gen = VFXGenerator()
    vid_builder = CinemaVideoPromptBuilder()
    orch = OrchestratorV4(output_dir="output/test_v4_full")

    all_pass = True
    for shot in shots[:3]:
        img_result = img_builder.build(orch._shot_to_image_dict(shot))
        vfx = vfx_gen.generate(orch._shot_to_vfx_dict(shot))
        cd = orch._shot_to_cinema_data(shot, vfx)
        vp = vid_builder.build(cd)

        ok = (img_result.quality_score >= 0.8 and
              vp.motion_strength > 0 and vp.motion_strength <= 1.0 and
              len(vp.first_frame_desc) > 10 and len(vp.last_frame_desc) > 10)
        if not ok:
            all_pass = False

        print("    {}:".format(shot.shot_id))
        print("      Image quality: {}".format(img_result.quality_score))
        print("      VFX: {}...".format(vfx.combined_description[:40]))
        print("      Video motion_strength: {}".format(vp.motion_strength))
        print("      Video first_frame: {}...".format(vp.first_frame_desc[:40]))
        print("      Video last_frame: {}...".format(vp.last_frame_desc[:40]))

    return all_pass


def main():
    test_dir = Path("output/test_v4_full")
    test_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Test 1: Shot creation
    print("=" * 60)
    print("TEST 1: Shot Creation and Saving")
    print("=" * 60)
    shots = create_test_shots(test_dir)
    results["shots_created"] = len(shots)
    print("  Total shots saved: {}".format(len(shots)))
    print("  PASS")

    # Test 2: Image prompts
    print("")
    print("=" * 60)
    print("TEST 2: Enhanced Image Prompt Builder")
    print("=" * 60)
    results["image_prompts_pass"] = test_image_prompts(shots)
    print("  Result: {}".format("PASS" if results["image_prompts_pass"] else "FAIL"))

    # Test 3: VFX
    print("")
    print("=" * 60)
    print("TEST 3: VFX Generator")
    print("=" * 60)
    vfx_results = test_vfx(shots)
    results["vfx_generated"] = len(vfx_results)
    print("  PASS")

    # Test 4: Video prompts
    print("")
    print("=" * 60)
    print("TEST 4: Cinema Video Prompt Builder")
    print("=" * 60)
    results["video_prompts_pass"] = test_video_prompts(shots, vfx_results)
    print("  Result: {}".format("PASS" if results["video_prompts_pass"] else "FAIL"))

    # Test 5: Shot table
    print("")
    print("=" * 60)
    print("TEST 5: Shot Table Generator")
    print("=" * 60)
    csv_size, json_size = test_shot_table(shots, vfx_results)
    results["csv_size"] = csv_size
    results["json_size"] = json_size
    print("  PASS")

    # Test 6: I2V generator
    print("")
    print("=" * 60)
    print("TEST 6: I2V Generator Template Loading")
    print("=" * 60)
    results["i2v_pass"] = test_i2v_generator()
    print("  Result: {}".format("PASS" if results["i2v_pass"] else "FAIL"))

    # Test 7: OrchestratorV4
    print("")
    print("=" * 60)
    print("TEST 7: OrchestratorV4 Initialization and Conversions")
    print("=" * 60)
    results["orchestrator_pass"] = test_orchestrator_v4(shots, test_dir)
    print("  Result: {}".format("PASS" if results["orchestrator_pass"] else "FAIL"))

    # Test 8: End-to-end chain
    print("")
    print("=" * 60)
    print("TEST 8: End-to-End Prompt Chain")
    print("=" * 60)
    results["e2e_pass"] = test_end_to_end_chain(shots)
    print("  Result: {}".format("PASS" if results["e2e_pass"] else "FAIL"))

    # Summary
    print("")
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    all_tests = [
        ("Shot Creation", True),
        ("Image Prompts", results["image_prompts_pass"]),
        ("VFX Generator", True),
        ("Video Prompts", results["video_prompts_pass"]),
        ("Shot Table", True),
        ("I2V Generator", results["i2v_pass"]),
        ("OrchestratorV4", results["orchestrator_pass"]),
        ("End-to-End Chain", results["e2e_pass"]),
    ]
    passed = sum(1 for _, ok in all_tests if ok)
    total = len(all_tests)
    for name, ok in all_tests:
        print("  [{}] {}".format("PASS" if ok else "FAIL", name))
    print("")
    print("  {}/{} tests passed".format(passed, total))

    if passed == total:
        print("")
        print("=== ALL TESTS PASSED ===")
    else:
        print("")
        print("=== SOME TESTS FAILED ===")
        sys.exit(1)


if __name__ == "__main__":
    main()

