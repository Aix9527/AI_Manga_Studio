# ComfyUI 提示词模板 (Prompt Master Template K)

## 漫剧角色生成专用
POSITIVE: [character_name], anime style, [gender], [appearance], [clothing], full body, clean lineart, cel shading, vibrant colors, manga illustration, character design sheet
NEGATIVE: realism, 3d render, photorealistic, deformed face, extra fingers, bad proportions, watermark, signature
SAMPLER: Euler ancestral | CFG: 7 | STEPS: 22 | RES: 768x1024

## 漫剧场景生成专用
POSITIVE: [scene_description], manga background art, [time_of_day], [weather], [mood], detailed environment, atmospheric, anime style, 16:9 composition
NEGATIVE: characters, people, text, watermark, blurry background, low detail
SAMPLER: DPM++ 2M Karras | CFG: 7.5 | STEPS: 25 | RES: 1280x720

## SDXL 通用
POSITIVE: [natural language subject description], [artistic style], [lighting setup], [camera angle], masterpiece, best quality
NEGATIVE: lowres, bad anatomy, bad hands, text, error, missing fingers, cropped, worst quality, jpeg artifacts
SAMPLER: DPM++ 2M Karras | CFG: 5-7 | STEPS: 25-35
