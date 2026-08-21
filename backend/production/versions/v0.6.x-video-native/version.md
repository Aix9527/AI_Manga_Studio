# AI Manga Studio — v0.6.x-video-native（生产版本锁定）

版本: v0.6.x-video-native
锁定日期: 2026-08-05
状态: ✅ 生产链冻结（Wan2.2 Native Pipeline 验证通过）

## 版本记录

```yaml
version: v0.6.x-video-native
model:
  wan2.2_ti2v_5B_fp16
  sha256:
    456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e
  vae: wan2.2_vae.safetensors (e40321bd... 校验通过)
  text_encoder: umt5_xxl_fp8_e4m3fn_scaled.safetensors (c3355d30... 校验通过)
resolution: 480x832
frames: 81
fps: 24
sampler: uni_pc/simple
steps: 20
cfg: 5
shift: 8
denoise: 1.0
workflow: wan22_ti2v5b_native.json
quality_gate: quality_gate.py (mosaic/block/static/motion + motion_cv 闪烁门禁)
model_guard: model_guard.py (SHA256 硬校验 + 损坏文件黑名单)
motion_profile: motion_profile.py (close_up/dialogue/detail/drama_action/transition/cinematic_action/environment)
```

## 验证结论（2026-08-05）
- Phase 1（3镜头验证）: ✅ PASS（近景 87.0 / 动作 87.9 / 环境 87.3）
- Phase 2（10镜头回归）: ✅ PASS（全部 86.5-88.1，motion_cv 0.32-0.56 < 0.65）
- GPT 评审: 确认可进入成片合成

## 冻结内容
- wan22_ti2v5b_native.json — 官方原生链路（UNETLoader→ModelSamplingSD3→Wan22ImageToVideoLatent→KSampler→VAEDecode→VHS_VideoCombine）
- model_guard.py — 模型哈希门禁
- quality_gate.py — 视频质量门禁（含 motion_std/motion_cv）
- motion_profile.py — 镜头级运动模板
- workflow_registry.py — 原生/回滚双轨注册表

## 后续（Phase 3 之后）
- v0.7 方向: 角色一致性（Reference Image/Face embedding/LoRA）、首尾帧动作链接、704x1280 关键镜升级、短剧化（BGM 节拍/口型/字幕时间轴）
