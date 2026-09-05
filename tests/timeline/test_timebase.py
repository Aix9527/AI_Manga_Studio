from backend.timeline.timebase import frame_index_to_tick, snap_video_tick


def test_24fps_frame_mapping_is_deterministic_without_float():
    assert frame_index_to_tick(0, ticks_per_second=1_000_000, fps_num=24, fps_den=1) == 0
    assert frame_index_to_tick(1, ticks_per_second=1_000_000, fps_num=24, fps_den=1) == 41667
    assert frame_index_to_tick(24, ticks_per_second=1_000_000, fps_num=24, fps_den=1) == 1_000_000
    assert snap_video_tick(41660, ticks_per_second=1_000_000, fps_num=24, fps_den=1) == 41667
