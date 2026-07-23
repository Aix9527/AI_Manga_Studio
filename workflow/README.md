# 📖 小说转视频工作流使用指南

## ⚠️ ComfyUI 当前状态

由于工作流文件过大导致 ComfyUI 启动时卡住，请按以下步骤操作：

### 第一步：恢复 ComfyUI

1. 关闭 ComfyUI（按 Ctrl+C 或关闭窗口）
2. 删除以下文件（这会让 ComfyUI 正常启动）：
   ```
   D:\ComfyUI\workflows\novel_to_video_comprehensive.json
   ```
3. 重新启动 ComfyUI

### 第二步：手动加载工作流

1. 打开 ComfyUI 浏览器界面: http://localhost:8188
2. 点击菜单 → **Load** → 选择 `D:\AI_Manga_Studio\workflow\novel_to_video_comprehensive.json`
3. 等待所有节点加载完成

---

## 📋 工作流架构说明

本工作流分为 **7 个模块化区域**，每个区域独立运作：

### 模块 1: 📖 小说解析模块（蓝色区域）
```
输入 → 分析引擎 → 输出
```
- **小说原文输入**: 粘贴你的小说章节文本
- **作品名称**: 输入小说标题
- **主要角色数**: 设置需要分析的角色数量
- **分镜数量**: 设置生成的分镜数量（默认10）
- **OpenAI API 配置**: 填入你的 API Key（sk-xxx）
- **小说深度分析引擎**: 调用 GPT-4o 分析文本
- **人物设定分析结果**: 输出的人物档案
- **场景设定分析结果**: 输出的场景描述
- **动作/情绪/分镜提示词**: 输出的动作链和分镜脚本

### 模块 2: 👤 角色身份板模块（橙色区域）
```
提示词 → RecraftV4 生成 → 三视图预览
```
- **角色1/2 正面/侧面/背面提示词**: 自动生成或手动编辑
- **RecraftV4TextToImageNode**: 使用 Recraft V4 API 生成高质量角色图
- **PreviewAny**: 实时预览生成的角色图

### 模块 3: 😊 微表情&服饰模块（红色区域）
```
情绪提示词 → 表情/服饰生成 → 预览
```
- **微表情-喜怒哀乐**: 生成4种基础表情
- **服饰-日常/正式**: 生成不同场合的服装搭配
- **饰品-武器/法器**: 生成角色道具

### 模块 4: 🎬 场景&动作生成模块（绿色区域）
```
场景提示词 → IdeogramV3/ByteDance → 场景/动作图
```
- **IdeogramV3**: 生成高质量场景概念图
- **ByteDance**: 生成角色动作参考图

### 模块 5: 🎥 视频生成&预览模块（紫色区域）
```
静态图 → Wan2 API → 动态视频
```
- **WanImageToVideoApi**: 将角色/场景图转为视频片段
- **PreviewAny**: 预览生成的视频

### 模块 6: 🔗 一致性保障模块（青色区域）
```
SAM3 追踪 → ControlNet → 动作链验证
```
- **SAM3_VideoTrack**: 跨镜头角色一致性追踪
- **ControlNetLoader + ControlNetApplyAdvanced**: 动作链一致性控制
- **FLUX.1-dev-Controlnet-Union**: Union ControlNet 模型

### 模块 7: 📊 总览仪表盘（黄色区域）
```
10人物预览 + 10分镜预览 + 最终合成
```
- **CreateList**: 收集所有角色图和视频
- **PreviewAny**: 仪表盘式预览
- **LumaVideoNode**: 最终视频合成

---

## 🔑 关键配置说明

### OpenAI API 配置
在节点 #5 `OpenAIChatConfig` 中填入：
- API Key: `sk-your-actual-key-here`
- Model: `gpt-4o`（推荐）或 `gpt-4-turbo`
- Temperature: `0.3`（低温度保证分析稳定性）

### RecraftV4 配置
- Style: `digital_illustration`（数字插画风格）
- Resolution: `1024x1024`
- Steps: 3
- CFG: 7

### Wan2 视频生成配置
- Duration: 24 frames
- Resolution: 720x720
- Steps: 5
- CFG: 6.5

---

## 🎯 工作流程

1. **粘贴小说文本** → 节点 #1
2. **配置 OpenAI API** → 节点 #5
3. **运行分析** → 节点 #6 自动生成人物/场景/动作分析
4. **审查分析结果** → 节点 #7, #8, #9
5. **生成角色三视图** → 节点 #20-35
6. **生成表情/服饰/饰品** → 节点 #50-63
7. **生成场景图** → 节点 #70-71
8. **生成动作参考图** → 节点 #80-81
9. **生成人物视频** → 节点 #90-91
10. **一致性追踪** → 节点 #110-111
11. **ControlNet 验证** → 节点 #120-121
12. **最终合成** → 节点 #130-131
13. **预览仪表盘** → 节点 #104-105

---

## 💡 优化建议

### VRAM 管理（16GB RTX 5070 Ti）
- 每次只运行一个模块，避免同时生成大量图像
- 使用 `SaveImage` 节点保存中间结果，释放显存
- 视频生成建议使用低分辨率（576x576）先测试

### 角色一致性技巧
- 使用相同的 Seed 值生成同一角色的不同视角
- PhotoMaker 节点可用于进一步锁定角色面部特征
- ControlNet Union 可保持姿势/构图一致性

### 分镜连贯性
- SAM3 追踪确保角色在不同镜头中保持一致
- ControlNet 动作链防止肢体变形
- Wan2 API 的视频生成已内置时序一致性

---

## 📁 文件结构

```
D:\AI_Manga_Studio\workflow\
├── novel_to_video_comprehensive.json  ← 主工作流文件
└── novel_to_video_workflow.json       ← 简化版工作流

D:\ComfyUI_Models_Backup\
├── checkpoints\
│   ├── sd_xl_base_1.0.safetensors     ← SDXL 基础模型
│   ├── flux1-schnell.safetensors      ← Flux 快速模型
│   └── ltx-2.3-22b-distilled-fp8.safetensors ← LTX 视频模型
├── clip_vision\
│   └── CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors
├── vae\
│   ├── ae.safetensors
│   └── Wan2.2_VAE.pth
├── controlnet\
│   └── FLUX.1-dev-Controlnet-Union.safetensors
└── loras\
    ├── ltx2.3-transition.safetensors
```

---

## ⚡ 快速开始

1. 确保 ComfyUI 正常运行: http://localhost:8188
2. 拖拽 `novel_to_video_comprehensive.json` 到 ComfyUI 界面
3. 配置 OpenAI API Key
4. 粘贴小说文本
5. 点击 "Queue Prompt" 开始生成
