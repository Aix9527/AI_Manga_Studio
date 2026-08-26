# AI Manga Studio

长篇小说 → CG AI 视频的一站式、本地优先、一键成片工作台（Novel to CG AI Video Studio）。

AI Manga Studio 将小说或剧本文本转化为带角色/场景资产、分镜、关键帧、视频、配音、字幕、质检与版本管理的 AI 影视内容，并将默认创作路径收口为一个可观察、可重试、可回退的本地生产流程。

## v0.8 当前状态

当前 `master` 已进入 **v0.8 Release Hardening** 阶段：统一 Studio、H3 Unified Formal Runtime、媒体绑定与恢复、Windows 一键安装/启动、H3 Live Gate 和统一 Release Gate 均已落地。

代码侧正式验收入口：

```bat
verify_release.bat
```

它会依次执行 launcher contract、H3 Unified 代码/运行时契约、前端 typecheck/tests/build，默认**不会提交 GPU 生成**。

目标机器 H3 体检：

```bat
verify_release.bat preflight
```

最终目标机器完整验收：

```bat
verify_release.bat full
```

`full` 会在代码 Gate 全部通过后执行 RTX / FFmpeg / ComfyUI / H3 Unified 节点体检，并提交一次 **T2VA / 5 秒 / 480p / 9:16 / 12 steps** 的真实 smoke generation。硬件证据写入：

```text
storage/live/h3_unified_live_gate.json
```

> H3 Unified 的完整请求契约要求 `LtoJ_H3UnifiedControlDesk`。传统 `h3/reference` / FL2V 是不同输入契约的替代路线，不会对同一个 Unified request 做透明自动 fallback。

## 新版工作台

默认界面不再暴露大量彼此割裂的工具页，而是围绕 Project → Episode → Scene → Shot 与可复用 Assets 组织为 5 个主工作区：

- **项目台 `/project`**：小说/剧本导入、六阶段一键成片、本地环境状态、媒体预览、实时任务队列。
- **故事·资产台 `/story-assets`**：故事结构与 Character / Location / Prop / Voice / Style 资产统一管理。
- **分镜导演台 `/director`**：镜头预览、镜头卡、场景时间线、构图/景别/运镜/焦段/光线/情绪、QC 与版本。
- **高级画布 `/canvas`**：基于 React Flow 的专业精修节点工作流；普通生产无需进入节点模式。
- **时间线·质检 `/timeline`**：多轨成片、QC Gate、失败/审核任务、重试与版本化导出。

旧 `/overview`、`/creator`、`/industrial`、`/workflow`、`/quality`、`/export`、`/os/*` 等界面入口已退出主路由，并会重定向到对应的新工作区。

## 一键生产流程

```text
导入小说/剧本
  → AI 拆解故事、角色与场景
  → 批量分镜
  → 关键帧 / 视频生成
  → 配音与字幕
  → 合成
  → QC Gate
  → 导出成片
```

普通模式优先使用现有自动编排、任务队列和 SSE 状态流；高级画布只用于特殊镜头与专业精修，不会成为一键成片的前置条件。

## 技术栈

- 后端：Python 3.10+ / FastAPI / Uvicorn / SQLite（结构化编排与任务队列）
- 前端：React 18 / TypeScript / Vite / Ant Design / Zustand / React Flow
- 媒体生成：ComfyUI 工作流（Wan / MiniMax H3 / FLUX 等）、edge-tts、CosyVoice、FFmpeg
- 质量保障：多智能体导演评审、画质/音质 QC、角色一致性校验、缺陷修复闭环
- 运行策略：**本地优先**，项目数据、缓存、媒体与日志默认保留在本机

## 快速开始

### Windows 推荐路径

```bat
setup.bat
verify_release.bat
run.bat
```

`setup.bat` 会安装核心 Python 依赖、使用 lockfile 安装前端依赖并构建正式前端；任一核心步骤失败都会返回非 0，不会再显示假成功。

### 手动安装

#### 1. 安装后端依赖

```bash
pip install -r requirements.txt
```

#### 2. 安装并构建前端

```bash
cd frontend
npm ci
npm run build
```

#### 3. 启动

```bash
python run.py
```

启动后访问：

- 前端界面：http://localhost:8000（生产构建）或 http://localhost:5173（开发模式）
- API 文档：http://localhost:8000/docs

后端与开发前端默认仅绑定 `127.0.0.1`。

## 目录结构

```text
├── backend/            # FastAPI 后端源码（核心业务模块）
│   ├── agents/         # 多智能体（导演 / 编剧 / 评论家 / 制片人）
│   ├── characters/     # 角色库、一致性校验
│   ├── production/     # ComfyUI 适配、工作流注册、制作圣经
│   ├── novel_video/    # 小说视频生成编排（分镜 → 画面 → 视频）
│   ├── orchestration/  # 任务队列与编排器
│   ├── quality/        # 画质评估与缺陷修复
│   └── ...
├── frontend/
│   └── src/studio/     # 新版统一工作台
├── architecture/       # 架构与许可证清单
├── docs/               # Release / 验收 / 重构文档
├── requirements.txt
├── run.py
├── setup.bat
├── verify_release.bat  # v0.8 统一 Release Gate
└── verify_h3.bat       # H3 Unified 目标机器真实验收
```

## 核心能力

- 小说解析：章节切分、中文分词、人物抽取与情感映射
- 角色一致性：角色设定库（Character Bible）、人脸编码、跨镜头身份校验
- 分镜导演：H3 提示词系统、参考帧、景别、构图、焦段、光线与镜头运动
- 画面生成：ComfyUI 工作流（文生图 / 图生视频 / 首尾帧）、Wan 与 MiniMax H3 多模型切换
- H3 Unified：T2VA / FL2VA / Ref2VA、多图片/视频/音频引用、分段长视频、Motion Context latent continuity、accepted prompt 恢复
- 音频合成：edge-tts 免费 TTS、CosyVoice 音色克隆、多轨混音与响度归一
- 任务可观察：运行、排队、暂停、继续、失败重试、审核与 SSE 状态更新
- 成片导出：字幕烧录、镜头拼接、版本化发布
- 质量保障：多智能体导演评审、QC 门禁、缺陷定位与自动修复

## 验证

### Windows 统一 Release Gate

```bat
verify_release.bat
```

只验证代码，不提交 GPU 生成。

```bat
verify_release.bat preflight
```

代码 Gate + H3 硬件/ComfyUI preflight，不生成视频。

```bat
verify_release.bat full
```

代码 Gate + H3 preflight + 5 秒真实 smoke generation。

### GitHub Actions

仓库包含分离的前端/H3/launcher CI，并新增 **`v0.8 Release Gate`** 工作流支持 `workflow_dispatch` 手动运行；发布 `v0.8*` tag 时也会执行代码 Release Gate。目标 GPU/ComfyUI 的真实 smoke 仍必须在本机完成。

### 手动前端验证

```bash
cd frontend
npm run typecheck
npm test -- --run
npm run build
```

完整 v0.8 验收标准见 `docs/RELEASE_V0.8.md`。

## 许可证

本项目为内部专有软件（Proprietary），详见 `architecture/license_manifest.json`。
