import hashlib
import json

from backend.orchestration.database import OrchestrationDatabase
from backend.timeline.compiler import TimelineCompiler, TimelineOutputProfile
from backend.timeline.qc import TimelineQcService
from backend.timeline.repository import TimelineRepository
from backend.timeline.service import TimelineService


def _snapshot(tmp_path):
    projects_root = tmp_path / "projects"
    project_id = "project-a"
    media_dir = projects_root / project_id / "outputs"
    media_dir.mkdir(parents=True)
    media_path = media_dir / "shot_001.mp4"
    media_path.write_bytes(b"compiler-source")
    digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    with db.transaction() as conn:
        conn.execute("INSERT INTO jobs (id,project_id,status,input_path,input_type,settings,idempotency_key) VALUES ('job-1',?,'completed','','novel','{}','compiler-seed')", (project_id,))
        conn.execute("INSERT INTO job_steps (id,job_id,sequence,stage_key,shot_id,status) VALUES ('step-1','job-1',0,'video_generate','shot_001','completed')")
        conn.execute(
            """INSERT INTO artifacts
               (id,job_id,step_id,kind,path,sha256,metadata,active,project_id,version,
                stage_key,scene_id,shot_id,quality_status)
               VALUES (1,'job-1','step-1','video','outputs/shot_001.mp4',?,?,1,?,1,
                       'video_generate','scene-1','shot_001','passed')""",
            (digest, json.dumps({"duration_tick": 2_000_000}), project_id),
        )
    repo = TimelineRepository(db, projects_root=projects_root)
    service = TimelineService(repo)
    draft, _ = service.initialize_project(project_id)
    snapshot = service.create_snapshot(draft.timeline_id)
    qc = TimelineQcService(repo)
    assert qc.run(snapshot.id).status == "passed"
    return repo, snapshot


def test_same_snapshot_and_output_profile_compile_to_identical_sha(tmp_path):
    repo, snapshot = _snapshot(tmp_path)
    compiler = TimelineCompiler(repo)
    profile = TimelineOutputProfile(width=1080, height=1920, fps_num=24, fps_den=1)

    first = compiler.compile(snapshot.id, profile)
    second = compiler.compile(snapshot.id, profile)

    assert first.spec_sha256 == second.spec_sha256
    assert first.spec_json == second.spec_json
    assert first.snapshot_id == snapshot.id


def test_output_profile_changes_spec_sha(tmp_path):
    repo, snapshot = _snapshot(tmp_path)
    compiler = TimelineCompiler(repo)

    portrait = compiler.compile(snapshot.id, TimelineOutputProfile(width=1080, height=1920, fps_num=24, fps_den=1))
    landscape = compiler.compile(snapshot.id, TimelineOutputProfile(width=1920, height=1080, fps_num=24, fps_den=1))

    assert portrait.spec_sha256 != landscape.spec_sha256


def test_compiler_reverifies_frozen_source_sha(tmp_path):
    repo, snapshot = _snapshot(tmp_path)
    compiler = TimelineCompiler(repo)
    source = repo.projects_root / "project-a" / "outputs" / "shot_001.mp4"
    source.write_bytes(b"changed-after-qc")

    try:
        compiler.compile(snapshot.id, TimelineOutputProfile(width=1080, height=1920, fps_num=24, fps_den=1))
    except ValueError as error:
        assert "integrity" in str(error).lower() or "sha" in str(error).lower()
    else:
        raise AssertionError("compiler must fail closed when frozen source bytes change")
