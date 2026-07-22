## 正式运行入口

- CLI：`python run.py --web` 或 `python run.py --novel <文本路径>`
- API：`python -m uvicorn backend.main:app --host 127.0.0.1 --port 8800`
- 正式任务接口：`/api/jobs`

`backend_v3/v4/v6/v7/v10/v11`、根目录 `pipeline.py` 和
`orchestrator.py` 仅保留为历史参考，不再是正式生产入口。

当前里程碑只提供可靠任务与项目底座。真实本地模型执行器未安装时，
任务会以 `PIPELINE_NOT_READY` 明确失败，不会生成占位图片或伪成片。
