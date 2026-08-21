// ProductionStudio — one-click production workspace

import React, { useState, useRef, useEffect } from "react";
import { useJobStore } from "@/state/jobStore";
import { api } from "@/api/jobs";
import type { ScannedProject } from "@/types/jobs";

const DEFAULT_WIDTH = 1080;
const DEFAULT_HEIGHT = 1920;

const BG_OPTIONS = [
  { label: "None", value: "none" },
  { label: "Epic", value: "epic" },
  { label: "Mystery", value: "mystery" },
  { label: "Romantic", value: "romantic" },
  { label: "Chill", value: "chill" },
];

const SFX_OPTIONS = [
  { label: "None", value: "none" },
  { label: "Wind", value: "wind" },
  { label: "Footsteps", value: "footsteps" },
  { label: "Sword Clash", value: "sword" },
  { label: "Magic", value: "magic" },
  { label: "Rain", value: "rain" },
  { label: "Thunder", value: "thunder" },
];

const ProductionStudio: React.FC = () => {
  const { createJob, subscribeSSE } = useJobStore();
  const [projects, setProjects] = useState<ScannedProject[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [inputFile, setInputFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"automatic" | "manual_review">("automatic");
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const [bgm, setBgm] = useState("none");
  const [sfx, setSfx] = useState("none");
  const [duration, setDuration] = useState(5.0);
  const [creating, setCreating] = useState(false);
  const [status, setStatus] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listProjects().then((res) => setProjects(res.projects)).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!inputFile && !selectedProject) {
      setStatus("Select a file or project first");
      return;
    }
    setCreating(true);
    setStatus("Uploading...");

    try {
      let inputPath = "";
      if (inputFile) {
        const upload = await api.uploadInput(inputFile, selectedProject || "default");
        inputPath = upload.path;
      } else {
        inputPath = selectedProject;
      }

      const job = await createJob({
        project_id: selectedProject || "default",
        input_path: inputPath,
        mode,
        width,
        height,
        shot_duration: duration,
        options: { bgm, sfx, style: "anime" },
      });

      subscribeSSE(job.id);
      setStatus(`Job ${job.id} created and queued`);
    } catch (e: any) {
      setStatus(`Error: ${e.message}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Production Studio</h1>

      {/* Input */}
      <section style={sectionStyle}>
        <h2 style={h2Style}>Input</h2>
        <div style={{ display: "flex", gap: 12 }}>
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md,.xml,.fountain"
            onChange={(e) => setInputFile(e.target.files?.[0] ?? null)}
            style={{ flex: 1, color: "var(--color-text-secondary)" }}
          />
        </div>
        {inputFile && (
          <div style={{ marginTop: 8, fontSize: 13, color: "var(--color-text-secondary)" }}>
            Selected: {inputFile.name} ({(inputFile.size / 1024).toFixed(0)} KB)
          </div>
        )}
        {projects.length > 0 && (
          <select
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
            style={selectStyle}
          >
            <option value="">-- Existing project --</option>
            {projects.map((p) => (
              <option key={p.name} value={p.source_path}>
                {p.name} ({p.file_count} files)
              </option>
            ))}
          </select>
        )}
      </section>

      {/* Settings */}
      <section style={sectionStyle}>
        <h2 style={h2Style}>Settings</h2>
        <div style={rowStyle}>
          <label style={labelStyle}>Mode</label>
          <select value={mode} onChange={(e) => setMode(e.target.value as any)} style={selectStyle}>
            <option value="automatic">Automatic</option>
            <option value="manual_review">Manual Review</option>
          </select>
        </div>
        <div style={rowStyle}>
          <label style={labelStyle}>Resolution</label>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="number"
              value={width}
              onChange={(e) => setWidth(Number(e.target.value))}
              style={inputStyle}
            />
            <span style={{ color: "var(--color-text-muted)" }}>×</span>
            <input
              type="number"
              value={height}
              onChange={(e) => setHeight(Number(e.target.value))}
              style={inputStyle}
            />
          </div>
        </div>
        <div style={rowStyle}>
          <label style={labelStyle}>Shot Duration (s)</label>
          <input
            type="number"
            value={duration}
            step={0.5}
            min={1}
            max={30}
            onChange={(e) => setDuration(Number(e.target.value))}
            style={inputStyle}
          />
        </div>
      </section>

      {/* Audio */}
      <section style={sectionStyle}>
        <h2 style={h2Style}>Audio</h2>
        <div style={rowStyle}>
          <label style={labelStyle}>BGM</label>
          <select value={bgm} onChange={(e) => setBgm(e.target.value)} style={selectStyle}>
            {BG_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div style={rowStyle}>
          <label style={labelStyle}>SFX</label>
          <select value={sfx} onChange={(e) => setSfx(e.target.value)} style={selectStyle}>
            {SFX_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </section>

      {/* Action */}
      <button
        onClick={handleCreate}
        disabled={creating}
        style={{
          width: "100%",
          padding: "12px 0",
          background: creating ? "var(--color-bg-tertiary)" : "var(--color-accent)",
          color: creating ? "var(--color-text-muted)" : "#fff",
          border: "none",
          borderRadius: "var(--radius-md)",
          fontSize: 15,
          fontWeight: 600,
          cursor: creating ? "not-allowed" : "pointer",
          marginTop: 8,
        }}
      >
        {creating ? "Creating..." : "Create Production Job"}
      </button>

      {status && (
        <div style={{ marginTop: 16, padding: "12px 16px", background: "var(--color-bg-secondary)", borderRadius: "var(--radius-md)", fontSize: 13, color: "var(--color-text-secondary)" }}>
          {status}
        </div>
      )}
    </div>
  );
};

// Styles
const sectionStyle: React.CSSProperties = {
  background: "var(--color-bg-secondary)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "20px",
  marginBottom: 16,
};

const h2Style: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 600,
  color: "var(--color-text-secondary)",
  marginBottom: 16,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: 12,
};

const labelStyle: React.CSSProperties = {
  fontSize: 13,
  color: "var(--color-text-primary)",
};

const inputStyle: React.CSSProperties = {
  width: 80,
  padding: "6px 10px",
  background: "var(--color-bg-tertiary)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-sm)",
  color: "var(--color-text-primary)",
  fontSize: 13,
};

const selectStyle: React.CSSProperties = {
  width: 160,
  padding: "6px 10px",
  background: "var(--color-bg-tertiary)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-sm)",
  color: "var(--color-text-primary)",
  fontSize: 13,
};

export default ProductionStudio;
