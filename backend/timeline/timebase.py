from __future__ import annotations


def _round_half_up(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("timebase values must be non-negative and denominator positive")
    return (numerator * 2 + denominator) // (2 * denominator)


def frame_index_to_tick(
    frame_index: int,
    *,
    ticks_per_second: int,
    fps_num: int,
    fps_den: int,
) -> int:
    if frame_index < 0 or ticks_per_second <= 0 or fps_num <= 0 or fps_den <= 0:
        raise ValueError("invalid frame/timebase values")
    return _round_half_up(frame_index * ticks_per_second * fps_den, fps_num)


def tick_to_nearest_frame_index(
    tick: int,
    *,
    ticks_per_second: int,
    fps_num: int,
    fps_den: int,
) -> int:
    if tick < 0 or ticks_per_second <= 0 or fps_num <= 0 or fps_den <= 0:
        raise ValueError("invalid tick/timebase values")
    return _round_half_up(tick * fps_num, ticks_per_second * fps_den)


def snap_video_tick(
    tick: int,
    *,
    ticks_per_second: int,
    fps_num: int,
    fps_den: int,
) -> int:
    frame_index = tick_to_nearest_frame_index(
        tick,
        ticks_per_second=ticks_per_second,
        fps_num=fps_num,
        fps_den=fps_den,
    )
    return frame_index_to_tick(
        frame_index,
        ticks_per_second=ticks_per_second,
        fps_num=fps_num,
        fps_den=fps_den,
    )
