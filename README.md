# AI Manga Studio

长篇小说 → CG AI 视频 一键生成工作台（Novel to CG AI Video Studio）。

AI Manga Studio 将小说文本自动转化为带分镜、配音、字幕与画面一致性的 CG 风格 AI 视频，覆盖从剧本解析、角色一致性、分镜生成、画面生成、音频合成到成片导出的完整制作流水线。

## 技术栈

- 后端：Python 3.10+ / FastAPI / Uvicorn / SQLite（结构化编排与任务队列）
- 前端：React 18 / TypeScript / Vite / Ant Design / Zustand
- 媒体生成：ComfyUI 工作流（Wan / MiniMax H3 / FLUX 等）、edge-tts、CosyVoice、FFmpeg
- 质量保障：多智能体导演评审、画质/音质 QC、角色一致性校验、缺陷修复闭环

## 快速开始

### 1. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 2. 安装并构建前端

```bash
cd frontend
npm install
npm run build
```

### 3. 启动

```bash
python run.py
```

启动后访问：

- 前端界面：http://localhost:8000（生产构建）或 http://localhost:5173（开发模式）
- API 文档：http://localhost:8000/docs

Windows 下也可直接运行 `setup.bat` 一键安装依赖、`run.bat` 启动服务。

## 目录结构

```
├── backend/            # FastAPI 后端源码（核心业务模块）
│   ├── agents/         # 多智能体（导演 / 编剧 / 评论家 / 制片人）
│   ├── characters/     # 角色库、一致性校验
│   ├── production/     # ComfyUI 适配、工作流注册、制作圣经
│   ├── novel_video/    # 小说视频生成编排（分镜 → 画面 → 视频）
│   ├── orchestration/  # 任务队列与编排器
│   ├── quality/        # 画质评估与缺陷修复
│   └── ...
├── frontend/           # React 前端源码（工作台 / 制作台 / 评审中心）
├── architecture/       # 架构与许可证清单
├── requirements.txt    # Python 依赖
├── run.py              # 一键启动脚本
└── setup.bat           # Windows 一键安装脚本
```

## 核心能力

- 小说解析：章节切分、中文分词、人物抽取与情感映射
- 角色一致性：角色设定库（Character Bible）、人脸编码、跨镜头身份校验
- 分镜生成：H3 提示词系统、参考帧选取、镜头语言模板
- 画面生成：ComfyUI 工作流（文生图 / 图生视频 / 首尾帧）、Wan 与 MiniMax H3 多模型切换
- 音频合成：edge-tts 免费 TTS、CosyVoice 音色克隆、多轨混音与响度归一
- 成片导出：字幕烧录、镜头拼接、预告片合成、版本化发布
- 质量保障：多智能体导演评审、QC 门禁、缺陷定位与自动修复

## 许可证

本项目为内部专有软件（Proprietary），详见 `architecture/license_manifest.json`。
