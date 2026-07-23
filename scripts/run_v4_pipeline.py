# -*- coding: utf-8 -*-
import sys, re, argparse, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.unified_shot import UnifiedShot, Camera, Emotion, Weather, TimeOfDay, Lighting
from backend.orchestrator_v4 import OrchestratorV4
from backend.enhanced_image_prompt_builder import EnhancedImagePromptBuilder
from backend.vfx_generator import VFXGenerator

def extract_narrative_paragraphs(novel_text, num_shots=20):
    raw_lines = novel_text.split(chr(10))
    paragraphs = []
    current = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(' '.join(current))
                current = []
        else:
            current.append(stripped)
    if current:
        paragraphs.append(' '.join(current))
    narrative = []
    bio_markers = ['【', '】', '**名字**', '**身份**', '**角色定位**', '**目标**', '**抱负**', '**价值观**', '**特长**', '**性格**', '**气质**', '**外表**', '**矛盾**', '**顿悟**', '**背景**', '**结局**', '**一句话**', '**背景补充**', '**结局**']
    for para in paragraphs:
        if len(para) < 15:
            continue
        if para.startswith('- ') or para.startswith('* ') or para.startswith('#') or para.startswith('**'):
            continue
        if any(kw in para for kw in bio_markers):
            continue
        if re.match(r'^【.*】$', para):
            continue
        if chr(9472)*3 in para or chr(9474) in para:
            continue
        narrative.append(para)
    return narrative[:num_shots]

def detect_scene(para):
    t = para.lower()
    if '实验' in t or '实验室' in t or '基因' in t:
        return '京城大学基因考古实验室'
    if '铁路' in t or '维修通道' in t or '高铁' in t:
        return '高铁维修通道'
    if '公寓' in t or '家中' in t or '魔都' in t:
        return '魔都公寓'
    if '地下城' in t or '三星堆' in t:
        return '三星堆地下城'
    if '归墟' in t or '遗迹' in t or '珠峰' in t:
        return '归墟遗迹'
    if '山岗' in t or '蜀地' in t:
        return '蜀地山岗'
    if '医院' in t or '产房' in t:
        return '妇产医院'
    if '列车' in t or '货运' in t:
        return '货运列车'
    return '未知场景'

def detect_emotion(para):
    t = para.lower()
    fear_kw = ['恐惧', '害怕', '颤抖', '冷汗', '窒息', '惊', '慌', '枪响', '破门', '黑衣', '带走', '掳走']
    angry_kw = ['愤怒', '恨', '怒', '咬牙', '握紧']
    tense_kw = ['紧张', '屏息', '沉默', '对峙']
    determined_kw = ['决心', '坚定', '必须', '绝不', '完成', '手术', '牺牲']
    calm_kw = ['平静', '冷静', '深呼吸', '理智']
    for kw in fear_kw:
        if kw in t: return Emotion.fearful
    for kw in angry_kw:
        if kw in t: return Emotion.angry
    for kw in determined_kw:
        if kw in t: return Emotion.determined
    for kw in calm_kw:
        if kw in t: return Emotion.calm
    for kw in tense_kw:
        if kw in t: return Emotion.fearful
    return Emotion.fearful

def detect_camera(para):
    t = para.lower()
    if any(k in t for k in ['屏幕', '盯着', '凝视', '数据', '基因', '碱基']):
        return Camera.close
    if any(k in t for k in ['天空', '远方', '俯瞰', '全景', '山岗', '城市']):
        return Camera.wide
    if any(k in t for k in ['跑步', '行走', '徒步', '移动', '通道', '铁路']):
        return Camera.tracking
    if any(k in t for k in ['高空', '鸟瞰']):
        return Camera.drone
    return Camera.medium

def create_shots(paragraphs, num_shots):
    shots = []
    scene_num = 1
    for i, para in enumerate(paragraphs[:num_shots]):
        scene = detect_scene(para)
        emotion = detect_emotion(para)
        camera = detect_camera(para)
        chars = ['苏晚']
        if '陈夜' in para: chars.append('陈夜')
        if '白砚行' in para or '白先生' in para: chars.append('白砚行')
        if '苏小满' in para or '女儿' in para: chars.append('苏小满')
        if '方觉明' in para or '老师' in para: chars.append('方觉明')
        dialogue = ''
        dm = re.findall(r'[“”](.+?)[“”]', para)
        if dm: dialogue = dm[0][:100]
        shot = UnifiedShot(
            chapter=1, scene=scene_num, shot=i+1,
            camera=camera, emotion=emotion,
            characters=chars, background=scene,
            time_of_day=TimeOfDay.night, weather=Weather.clear,
            lighting=Lighting.cinematic, duration=5.0,
            narration=para[:200], dialogue=dialogue, sfx='',
            camera_motion='',
            shot_id='ch01_sc{:02d}_sh{:03d}'.format(scene_num, i+1),
        )
        shots.append(shot)
        if i > 0 and scene != detect_scene(paragraphs[i-1]):
            scene_num += 1
    return shots

def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('novel')
    pa.add_argument('--output', default='output/v4_pipeline')
    pa.add_argument('--shots', type=int, default=20)
    pa.add_argument('--style', default='anime', choices=['anime','cinematic','realistic'])
    pa.add_argument('--no-images', action='store_true')
    args = pa.parse_args()
    np = Path(args.novel)
    if not np.exists():
        print('[ERROR] Not found:', np); sys.exit(1)
    text = np.read_text(encoding='utf-8')
    print('='*60)
    print('  AI Manga Studio V4 - Director Pipeline')
    print('='*60)
    print('  Novel:', np.name)
    print('  Length:', len(text), 'chars')
    print('  Output:', args.output)
    print()
    print('[1/6] Extracting narrative paragraphs...')
    paras = extract_narrative_paragraphs(text, args.shots)
    print('  Found', len(paras), 'narrative paragraphs (filtered bios/markdown)')
    for i,p in enumerate(paras[:3]):
        print('  Para', i+1, ':', p[:80])
    print('[2/6] Creating shots...')
    shots = create_shots(paras, args.shots)
    print('  Created', len(shots), 'shots')
    print('[3/6] Initializing pipeline...')
    orch = OrchestratorV4(comfyui_url='http://127.0.0.1:8188', output_dir=args.output, style=args.style)
    print('  Ready')
    print('[4/6] Saving shots...')
    sd = Path(args.output)/'ch01'/'shots'
    sd.mkdir(parents=True, exist_ok=True)
    for s in shots:
        s.to_json_file(str(sd/'shot_{:03d}.json'.format(s.shot)))
    print('  Saved', len(shots), 'shot JSONs')
    print('[5/6] Building prompts...')
    ib = EnhancedImagePromptBuilder(style=args.style)
    vg = VFXGenerator()
    vb = orch.video_prompt_builder
    for s in shots:
        ib.build(orch._shot_to_image_dict(s))
        vg.generate(orch._shot_to_vfx_dict(s))
        cd = orch._shot_to_cinema_data(s, None)
        vb.build(cd)
    print('  Image/VFX/Video prompts built for', len(shots), 'shots')

    # Export shot table
    from backend.shot_table_generator import ShotTableGenerator
    import os
    stg = ShotTableGenerator()
    shots_data = []
    vfx_g = VFXGenerator()
    for s in shots:
        v = vfx_g.generate({"shot_id": s.shot_id, "emotion": str(s.emotion), "weather": str(s.weather)})
        shots_data.append({
            "shot_number": s.shot, "shot_type": str(s.camera), "camera_angle": "eye_level",
            "camera_movement": s.camera_motion or "", "visual_content": s.narration,
            "dialogue": s.dialogue, "lighting": str(s.lighting), "vfx": v.combined_description,
            "duration_sec": s.duration, "transition_in": "cut", "transition_out": "cut",
            "emotion": str(s.emotion), "notes": s.background,
        })
    entries = stg.generate(shots_data)
    stg.export_as_excel_csv(entries, os.path.join(args.output, "shot_table.csv"))
    stg.export_as_json(entries, os.path.join(args.output, "shot_table.json"))
    print("  Shot table exported")
    print('[6/6] Done!')
    print()
    print('='*60)
    print('  Pipeline complete!')
    print('  Output:', args.output)
    # Generate images via ComfyUI
    print('  Attempting image generation via ComfyUI...')
    from backend.comfyui_client import ComfyUIClient
    from backend.workflow_generator import WorkflowGenerator
    client = ComfyUIClient(base_url='http://127.0.0.1:8188')
    wgen = WorkflowGenerator()
    success_count = 0
    for shot in shots:
        try:
            wf = wgen.generate(shot)
            result = client.submit_workflow(wf, wait=True)
            if result and result.get('images'):
                img_path = result['images'][0].get('path', '')
                if img_path:
                    shot.image_path = img_path
                    shot.mark_success(image=img_path)
                    shot_dir = Path(args.output) / 'ch01' / 'shots'
                    shot.to_json_file(str(shot_dir / f'shot_{shot.shot:03d}.json'))
                    success_count += 1
        except Exception as e:
            print(f'    Shot {shot.shot_id}: image gen failed: {e}')
    print(f'  Image generation: {success_count}/{len(shots)} shots rendered')
    print('  Video generation requires Wan2.2/Hunyuan custom nodes.')
    print('  For now, only image generation is supported.')
    print('='*60)

if __name__ == '__main__':
    main()
