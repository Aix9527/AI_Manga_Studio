# AI Manga Studio v0.8 Release Acceptance

本文档定义 v0.8 的正式发布门槛。**代码 Gate 与目标机器硬件 Gate 分开记录，任何未实际执行的 Gate 不得标记为 PASS。**

## 1. 发布基线

- 默认分支：`master`
- 产品形态：本地优先、单用户、Windows 桌面/浏览器工作台
- 后端监听：`127.0.0.1:8000`
- ComfyUI 默认：`127.0.0.1:8188`
- Unified Studio：项目台 / 故事·资产台 / 分镜导演台 / 高级画布 / 时间线·质检
- H3 Unified：T2VA / FL2VA / Ref2VA、多媒体引用、分段长视频、Motion Context continuity、accepted prompt 恢复

## 2. Gate 0：安装

Windows：

```bat
setup.bat
```

必须满足：

- Python 存在
- `requirements.txt` 安装成功
- Node/npm 存在
- lockfile 存在时使用 `npm ci`
- 前端 `npm run build` 成功
- 任一核心步骤失败时 `setup.bat` 返回非 0
- 只有全部核心步骤通过才显示 `Setup complete!`

## 3. Gate 1：代码 Release Gate

安全默认模式：

```bat
verify_release.bat
```

必须依次通过：

1. `tests/test_local_launchers.py`
2. H3 Unified 目标测试集
3. 前端 `npm run typecheck`
4. 前端 `npm test -- --run`
5. 前端 `npm run build`

默认模式不得调用 `verify_h3.bat`，不得提交 GPU 生成。

### GitHub 手动代码 Gate

Actions → **v0.8 Release Gate** → **Run workflow**。

该 workflow 可手动执行，并在 `v0.8*` tag push 时执行；包含：

- launcher contract
- H3 Unified syntax + target tests
- Unified Studio install/audit/typecheck/tests/build

GitHub Actions 不能替代目标 Windows / RTX / ComfyUI 的真实硬件验收。

## 4. Gate 2：目标机器 H3 preflight

推荐统一入口：

```bat
verify_release.bat preflight
```

也可仅执行 H3：

```bat
verify_h3.bat preflight
```

必须满足：

- `nvidia-smi` 成功
- GPU 被识别
- VRAM 达到 live gate 的 16GB 档阈值
- `ffmpeg` / `ffprobe` 可用
- ComfyUI `/object_info` 可访问
- 存在 `LtoJ_H3UnifiedControlDesk`
- Motion Context 节点完整：
  - `MiniMaxH3MotionContextLoadLatent`
  - `MiniMaxH3MotionContext`
  - `MiniMaxH3MotionContextTrim`
  - `MiniMaxH3MotionContextSaveLatent`
- `recommended_runtime == "external_unified"`
- `preflight.ok == true`

若缺 Unified control node：

- 必须 fail closed
- `recommended_runtime == "unavailable"`
- 可报告 `alternate_route == "h3/reference"`
- 必须报告 `alternate_route_requires_recompile == true`
- 不得把原 Unified request 透明提交到传统 H3 route

## 5. Gate 3：目标机器真实 H3 smoke

统一入口：

```bat
verify_release.bat full
```

也可仅执行 H3：

```bat
verify_h3.bat
```

固定 smoke：

- mode: `T2VA`
- duration: `5s`
- resolution: `480p`
- aspect ratio: `9:16`
- steps: `12`

必须满足：

- Gate 2 已通过
- ComfyUI 接受 prompt
- accepted `prompt_id` 被保存
- 任务完成并产出媒体
- evidence `state == "completed"`
- evidence `runtime == "external_unified"`
- 证据文件存在：`storage/live/h3_unified_live_gate.json`

## 6. Crash / Resume 验收

若 accepted prompt 之后进程中断：

```bat
python tools\h3_unified_live_gate.py --submit --resume-prompt-id <prompt_id>
```

必须：

- 等待同一个 accepted prompt
- 不重新上传参考素材
- 不提交第二个 prompt
- 不切换 provider/runtime

## 7. Release 决策

只有以下全部成立，才能将 v0.8 标记为目标机器正式验收完成：

- [ ] Gate 0 安装 PASS
- [ ] Gate 1 代码 Release Gate PASS
- [ ] Gate 2 H3 target-machine preflight PASS
- [ ] Gate 3 H3 real smoke PASS
- [ ] evidence JSON 已保留
- [ ] GPU / VRAM / ComfyUI nodes / prompt_id / output media 已记录

### 当前仓库侧已完成

- [x] 统一 Studio 主工作台
- [x] H3 Unified Formal Runtime 与 provider wiring
- [x] 视频/音频/图片引用绑定与 SHA256 验证
- [x] accepted prompt durable recovery 规则
- [x] H3 live gate
- [x] Windows `setup.bat` fail-closed
- [x] Windows `run.py` / `run.bat` loopback-only 启动策略
- [x] `verify_h3.bat`
- [x] `verify_release.bat`
- [x] 手动 `v0.8 Release Gate` GitHub workflow

### 仍需目标机器证据

- [ ] RTX / VRAM preflight
- [ ] ComfyUI Unified + Motion Context node catalogue
- [ ] 5 秒真实 H3 smoke generation

硬件 Gate 完成后，再创建/发布 `v0.8.0` 正式 release；不要仅凭代码 review 或云端 CI 宣称硬件验收通过。
