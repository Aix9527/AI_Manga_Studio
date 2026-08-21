import pytest

from backend.novel_video.models import RunStatus, ShotStatus
from backend.novel_video.state_machine import InvalidTransition, transition_run, transition_shot


@pytest.mark.parametrize("status", [RunStatus.CANCELLED, RunStatus.COMPLETED])
def test_terminal_run_cannot_return_to_rendering(status):
    with pytest.raises(InvalidTransition):
        transition_run(status, RunStatus.RENDERING)


def test_interrupted_run_can_only_resume_at_a_recovery_stage():
    assert transition_run(RunStatus.INTERRUPTED, RunStatus.PLANNING) is RunStatus.PLANNING

    with pytest.raises(InvalidTransition):
        transition_run(RunStatus.INTERRUPTED, RunStatus.MIXING)


def test_included_shot_cannot_return_to_running():
    with pytest.raises(InvalidTransition):
        transition_shot(ShotStatus.INCLUDED, ShotStatus.RUNNING)
