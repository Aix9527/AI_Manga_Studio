# -*- coding: utf-8 -*-
"""Fix: add image generation to run_v4_pipeline.py"""
from pathlib import Path

p = Path("scripts/run_v4_pipeline.py")
text = p.read_text(encoding="utf-8")

# Replace the final message with actual image generation code
old = "    print('  To generate images/videos, start ComfyUI and re-run')"
new = """    # Generate images via ComfyUI
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
    print('  For now, only image generation is supported.')"""

text = text.replace(old, new)
p.write_text(text, encoding="utf-8")
print("Added image generation step")
