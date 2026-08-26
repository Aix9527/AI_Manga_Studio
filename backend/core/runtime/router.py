class ModelRouter:
    """
    视频后端路由（MiniMax H3 迁移后）

    - 普通批量、依赖稳定性的镜头：wan22
    - 原生对白 / 环境音 / 音效 / 音乐同步生成：h3
    - 快速运动、复杂调度、首尾帧约束：h3/standard
    - 人物 / 服装多参考、动作视频参考、声音参考：h3/reference
    - H3 一体化/长分段：仅显式 opt-in；外部 Unified runtime 缺失时必须阻断
    - h3/reference 可作为重新编译后的替代路线，但不是 Unified request 的透明 fallback
    - H3 缺依赖、OOM、执行失败或质量门未通过：仅既有明确允许的生产路由可回退 wan22/dialogue
    """

    def select(self, request):
        if request.get("stage") != "video_generation":
            return {
                "provider": "local",
                "confidence": 0.5,
            }

        intent = request.get("intent", "")
        audio_sync = request.get("audio_sync", False)
        ref_count = request.get("ref_count", 0)
        ref_video = request.get("ref_video", False)

        # H3 Unified：只在明确启用时进入，避免改变既有生产路由。
        # Unified 与传统 Ref2VA/FL2VA 的输入契约不同；缺少外部控制台
        # 时必须让调用方重新编译到另一条路线，不能原请求自动切换。
        if request.get("h3_unified", False) or intent in (
            "long_reference",
            "segmented_reference",
        ):
            return {
                "provider": "h3",
                "model": "minimax_h3_unified",
                "workflow": "unified",
                "confidence": 0.95,
                "fallback": None,
                "alternate_route": "h3/reference",
                "alternate_route_requires_recompile": True,
            }

        # H3 Reference：多参考（图片/视频/音频）
        if ref_count >= 2 or ref_video or intent == "reference":
            return {
                "provider": "h3",
                "model": "minimax_h3_ref2va",
                "workflow": "reference",
                "confidence": 0.93,
                "fallback": "wan22/dialogue",
            }

        # H3 Standard：原生对白 / 音效 / 首尾帧
        if (
            audio_sync
            or request.get("first_frame", False)
            or request.get("last_frame", False)
            or intent in ("dialogue", "sfx", "motion")
        ):
            return {
                "provider": "h3",
                "model": "minimax_h3_fl2va",
                "workflow": "standard",
                "confidence": 0.92,
                "fallback": "wan22/dialogue",
            }

        # 默认：Wan 2.2 稳定批量
        return {
            "provider": "local",
            "model": "wan2.2_ti2v_5B",
            "workflow": "wan22_native",
            "confidence": 0.94,
        }
