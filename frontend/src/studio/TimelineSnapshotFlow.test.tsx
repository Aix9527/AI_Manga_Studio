import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import TimelineSnapshotPanel from "@/studio/timeline/TimelineSnapshotPanel";
import TimelineInspector from "@/studio/timeline/TimelineInspector";
import type {
  TimelineClip,
  TimelineDraft,
  TimelineOutputProfile,
  TimelineQcStatus,
  TimelineSnapshot,
} from "@/types/timeline";

const draft: TimelineDraft = {
  timeline_id: "timeline-a",
  draft_id: "draft-a",
  project_id: "project-a",
  revision: 12,
  timebase_hz: 1_000_000,
  fps_num: 24,
  fps_den: 1,
  tracks: [
    {
      id: "v1",
      track_type: "video",
      role: "video.main",
      name: "V1",
      sort_index: 0,
      locked: false,
      muted: false,
      hidden: false,
      clips: [
        {
          id: "clip-1",
          track_id: "v1",
          artifact_id: 11,
          artifact_version: 1,
          clip_type: "video",
          timeline_start_tick: 0,
          duration_tick: 2_000_000,
          source_in_tick: 0,
          source_out_tick: 2_000_000,
          link_group_id: null,
          enabled: true,
          locked: false,
          shot_id: "shot_001",
          scene_id: "scene-a",
          media_url: "/assets/11",
        },
      ],
    },
    { id: "a1", track_type: "audio", role: "audio.dialogue", name: "A1", sort_index: 1, locked: false, muted: false, hidden: false, clips: [] },
    { id: "a2", track_type: "audio", role: "audio.bgm", name: "A2", sort_index: 2, locked: false, muted: false, hidden: false, clips: [] },
    { id: "s1", track_type: "subtitle", role: "subtitle.primary", name: "S1", sort_index: 3, locked: false, muted: false, hidden: false, clips: [] },
  ],
  subtitle_cues: [],
  transitions: [],
};

const snapshot: TimelineSnapshot = {
  id: "snapshot-2",
  timeline_id: "timeline-a",
  snapshot_no: 2,
  source_draft_revision: 12,
  state_sha256: "b".repeat(64),
  duration_tick: 2_000_000,
  created_at: "2026-09-05T00:00:00Z",
};

function qc(status: TimelineQcStatus["effective_status"]): TimelineQcStatus {
  return { snapshot_id: snapshot.id, effective_status: status, attempts: [] };
}

afterEach(cleanup);

describe("Timeline Snapshot formal workflow", () => {
  it("flushes pending edits before creating a Snapshot and renders Snapshot #N", async () => {
    const user = userEvent.setup();
    const calls: string[] = [];
    const flush = vi.fn(async () => { calls.push("flush"); });
    const create = vi.fn(async () => { calls.push("create"); return snapshot; });

    const { rerender } = render(
      <TimelineSnapshotPanel
        draft={draft}
        preflight={{ status: "ok", warnings: [] }}
        snapshots={[]}
        selectedSnapshotId={null}
        qcBySnapshot={{}}
        pendingSave
        onSelectSnapshot={vi.fn()}
        onFlush={flush}
        onCreateSnapshot={create}
        onRunQc={vi.fn()}
        onExportSnapshot={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "创建版本" }));
    expect(calls).toEqual(["flush", "create"]);

    rerender(
      <TimelineSnapshotPanel
        draft={draft}
        preflight={{ status: "ok", warnings: [] }}
        snapshots={[snapshot]}
        selectedSnapshotId={snapshot.id}
        qcBySnapshot={{ [snapshot.id]: qc("not_run") }}
        pendingSave={false}
        onSelectSnapshot={vi.fn()}
        onFlush={flush}
        onCreateSnapshot={create}
        onRunQc={vi.fn()}
        onExportSnapshot={vi.fn()}
      />,
    );
    expect(screen.getByText("Snapshot #2")).toBeInTheDocument();
    expect(screen.getByText(/QC.*未运行/)).toBeInTheDocument();
  });

  it("shows stale source integrity and sends the selected output profile only after passed QC", async () => {
    const user = userEvent.setup();
    const flush = vi.fn().mockResolvedValue(undefined);
    const exportSnapshot = vi.fn<(snapshotId: string, profile: TimelineOutputProfile) => Promise<void>>().mockResolvedValue(undefined);

    const { rerender } = render(
      <TimelineSnapshotPanel
        draft={draft}
        preflight={{ status: "ok", warnings: [] }}
        snapshots={[snapshot]}
        selectedSnapshotId={snapshot.id}
        qcBySnapshot={{ [snapshot.id]: qc("stale") }}
        pendingSave={false}
        onSelectSnapshot={vi.fn()}
        onFlush={flush}
        onCreateSnapshot={vi.fn()}
        onRunQc={vi.fn()}
        onExportSnapshot={exportSnapshot}
      />,
    );
    expect(screen.getByText(/源素材完整性已失效/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /导出 Snapshot/ })).toBeDisabled();

    rerender(
      <TimelineSnapshotPanel
        draft={draft}
        preflight={{ status: "ok", warnings: [] }}
        snapshots={[snapshot]}
        selectedSnapshotId={snapshot.id}
        qcBySnapshot={{ [snapshot.id]: qc("passed") }}
        pendingSave={false}
        onSelectSnapshot={vi.fn()}
        onFlush={flush}
        onCreateSnapshot={vi.fn()}
        onRunQc={vi.fn()}
        onExportSnapshot={exportSnapshot}
      />,
    );
    await user.selectOptions(screen.getByLabelText("导出分辨率"), "1920x1080");
    await user.selectOptions(screen.getByLabelText("导出帧率"), "30");
    await user.click(screen.getByRole("button", { name: /导出 Snapshot/ }));

    expect(flush).toHaveBeenCalled();
    expect(exportSnapshot).toHaveBeenCalledWith(snapshot.id, {
      width: 1920,
      height: 1080,
      fps_num: 30,
      fps_den: 1,
    });
  });
});

describe("Timeline Artifact upgrade controls", () => {
  it("never replaces automatically and exposes keep/current/all actions", async () => {
    const user = userEvent.setup();
    const critical = vi.fn();
    const selectedClip = draft.tracks[0].clips[0] as TimelineClip;

    render(
      <TimelineInspector
        draft={draft}
        selectedClip={selectedClip}
        artifactUpgrade={{ artifact_id: 21, version: 2 }}
        onCriticalOperation={critical}
      />,
    );

    expect(screen.getByText(/v1.*v2.*可用/)).toBeInTheDocument();
    expect(critical).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "保留旧版" }));
    expect(critical).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "替换当前" }));
    expect(critical).toHaveBeenCalledWith({
      type: "REPLACE_ARTIFACT_VERSION",
      clip_ids: ["clip-1"],
      artifact_id: 21,
    });

    critical.mockClear();
    await user.click(screen.getByRole("button", { name: "替换全部" }));
    expect(critical).toHaveBeenCalledWith({
      type: "REPLACE_ARTIFACT_VERSION",
      clip_ids: ["clip-1"],
      artifact_id: 21,
    });
  });
});
