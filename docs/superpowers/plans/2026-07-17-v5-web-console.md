# V5 Persistent Web Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved Web console with a global task strip, one-click production workspace, task center, failure recovery and manual review controls whose state survives every route change and refresh.

**Architecture:** React Router owns page navigation while a route-independent external job store owns the current server job. The store performs one initial `/api/jobs/current` request, listens to SSE and falls back to polling without duplicating requests across pages. Small feature components render the approved dark production-console design using shared tokens and Ant Design primitives.

**Tech Stack:** React 18, TypeScript, Vite, React Router 6, Ant Design 5, Vitest, Testing Library, Browser/IAB

---

**Depends on:**

- `docs/superpowers/plans/2026-07-17-v5-durable-orchestrator.md`
- `docs/superpowers/plans/2026-07-17-v5-production-pipeline.md`

**Accepted visual source:** `.superpowers/brainstorm/windows-20260717084836354/content/web-layout.html`

## File structure

| Path | Responsibility |
|---|---|
| `docs/design/v5-web-console-desktop.png` | Approved production reference captured from the accepted layout |
| `docs/design/v5-web-console-failure.png` | Approved failure/recovery state reference |
| `frontend/src/styles/tokens.css` | Color, type, spacing, radius, elevation and motion tokens |
| `frontend/src/styles/app.css` | App shell and responsive layout |
| `frontend/src/api/client.ts` | Same-origin API client and error mapping |
| `frontend/src/api/jobs.ts` | Job queries, commands and SSE URL |
| `frontend/src/types/jobs.ts` | Backend job, step and artifact contracts |
| `frontend/src/state/jobStore.ts` | External current-job store with SSE/poll recovery |
| `frontend/src/state/JobProvider.tsx` | React bindings and action context |
| `frontend/src/components/layout/AppShell.tsx` | Global navigation and routed content |
| `frontend/src/components/jobs/GlobalTaskBar.tsx` | Always-visible current task strip |
| `frontend/src/components/jobs/StageTimeline.tsx` | Stage and shot progress |
| `frontend/src/components/jobs/FailurePanel.tsx` | Failure reason and recovery actions |
| `frontend/src/components/jobs/ReviewPanel.tsx` | Approve/edit/retry/rollback controls |
| `frontend/src/pages/ProductionStudio.tsx` | Input/configuration and one-click start |
| `frontend/src/pages/TaskCenter.tsx` | Current and historical jobs |
| `frontend/src/App.tsx` | Route composition only |
| `frontend/src/main.tsx` | Router, theme and provider setup |
| `frontend/src/**/*.test.tsx` | Component and navigation persistence tests |

### Task 1: Freeze the approved visual reference and implementation inventory

**Files:**
- Create: `docs/design/v5-web-console-desktop.png`
- Create: `docs/design/v5-web-console-failure.png`
- Create: `docs/design/v5-web-console-inventory.md`

- [ ] **Step 1: Generate polished reference states from the accepted layout**

Use the `imagegen` skill with the approved HTML screenshot as the structural reference. Generate two readable 1440×900 desktop concepts with identical visual system and exact approved copy:

```text
State A: global task strip running at 47%, left navigation, one-click creation form,
automatic/manual toggle, 5–15 second setting, custom 1080×1920 resolution,
right-side live stage chain.

State B: same shell with shot 07 video generation failed after retry 3/3,
completed upstream stages preserved, and actions for retry current step,
change workflow, roll back to first frame, and cancel.
```

Save the accepted outputs as the two files listed above. Do not add navigation, statistics, badges or product claims absent from the approved HTML.

- [ ] **Step 2: Obtain visual sign-off before writing UI code**

Show both reference states to the user. Continue only after the user confirms that the production references preserve the already approved information architecture.

- [ ] **Step 3: Record the design system inventory**

Create `docs/design/v5-web-console-inventory.md` with exact sampled values:

```markdown
# V5 Web Console Visual Inventory

- Viewport: 1440×900 desktop; 390×844 mobile acceptance viewport
- Background: #071019
- Primary surface: #0d1722
- Raised surface: #111f2d
- Border: #223447
- Primary text: #edf4f8
- Muted text: #90a6b8
- Accent: #55d7e8
- Success: #55dfa0
- Warning: #ffbd59
- Failure: #ff6b7e
- Review: #a58cff
- Radius: 10 / 14 / 18 px
- Spacing scale: 4 / 8 / 12 / 16 / 20 / 24 / 32 px
- Motion: 160 ms ease-out for hover; 240 ms ease-out for drawers
- Chrome typography: Inter, Microsoft YaHei, system-ui; 12–14 px
- Content typography: Inter, Microsoft YaHei, system-ui; 14–34 px
- Container model: fixed left rail, persistent top task strip, open main workspace,
  one right status panel; avoid nested card grids
```

- [ ] **Step 4: Commit the approved visual contract**

```powershell
git add docs/design
git commit -m "design: freeze V5 web console reference"
```

### Task 2: Add the frontend test harness and typed API client

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/types/jobs.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/jobs.ts`
- Test: `frontend/src/api/jobs.test.ts`

- [ ] **Step 1: Write a failing same-origin API test**

Create `frontend/src/api/jobs.test.ts`:

```typescript
import {afterEach, expect, it, vi} from "vitest";
import {getCurrentJob, uploadInput} from "./jobs";

afterEach(() => vi.restoreAllMocks());

it("uses the Vite same-origin proxy instead of a hardcoded host", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("null", {status: 200, headers: {"Content-Type": "application/json"}}),
  );
  await getCurrentJob();
  expect(fetchMock).toHaveBeenCalledWith("/api/jobs/current", expect.any(Object));
});

it("uploads through the same origin without forcing a JSON content type", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({path: "managed.txt", original_name: "story.txt", input_type: "novel", size: 5}), {
      status: 200, headers: {"Content-Type": "application/json"},
    }),
  );
  await uploadInput(new File(["story"], "story.txt"));
  const init = fetchMock.mock.calls[0][1] as RequestInit;
  expect(fetchMock.mock.calls[0][0]).toBe("/api/uploads");
  expect(init.body).toBeInstanceOf(FormData);
  expect(new Headers(init.headers).has("Content-Type")).toBe(false);
});
```

- [ ] **Step 2: Install and configure Vitest**

Add these dev dependencies and scripts to `frontend/package.json`:

```json
{
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/react": "^15.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/node": "^20.0.0",
    "jsdom": "^24.0.0",
    "vitest": "^1.6.0"
  },
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit"
  }
}
```

Create `frontend/vitest.config.ts`:

```typescript
import {defineConfig} from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {environment: "jsdom", setupFiles: ["./src/test/setup.ts"]},
});
```

Create `frontend/src/test/setup.ts`:

```typescript
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 3: Run the test and verify the API module is missing**

```powershell
cd frontend
npm install
npm test -- src/api/jobs.test.ts
```

Expected: FAIL because `./jobs` does not exist.

- [ ] **Step 4: Define job contracts**

Create `frontend/src/types/jobs.ts`:

```typescript
export type JobStatus =
  | "draft" | "queued" | "running" | "waiting_review" | "retry_wait"
  | "failed" | "paused" | "completed" | "cancelled";

export type StepStatus =
  | "pending" | "queued" | "running" | "waiting_review" | "retry_wait"
  | "failed" | "completed" | "invalidated" | "cancelled";

export interface JobStep {
  id: string;
  stage_key: string;
  shot_id?: string;
  status: StepStatus;
  attempt: number;
  progress: number;
  error_code: string;
  error_message: string;
  artifacts?: Array<{kind: string; path: string; metadata: Record<string, unknown>}>;
}

export interface Job {
  id: string;
  project_id: string;
  status: JobStatus;
  mode: "automatic" | "manual_review";
  desired_state: "running" | "paused" | "cancelled";
  current_stage: string;
  current_shot: string;
  progress: number;
  message: string;
  final_video: string;
  created_at: string;
  updated_at: string;
  steps: JobStep[];
}

export type JobSummary = Omit<Job, "steps">;

export interface CreateJobInput {
  project_id: string;
  input_path: string;
  input_type: "novel" | "script" | "storyboard";
  mode: "automatic" | "manual_review";
  shot_duration: number;
  width: number;
  height: number;
  fps: number;
  options: Record<string, unknown>;
  idempotency_key: string;
}

export interface UploadedInput {
  path: string;
  original_name: string;
  input_type: "novel" | "script" | "storyboard";
  size: number;
}

export interface RollbackPreview {
  step_id: string;
  invalidated_step_ids: string[];
}
```

- [ ] **Step 5: Implement the same-origin client and job commands**

Create `frontend/src/api/client.ts`:

```typescript
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(response.status, detail || response.statusText);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
```

Create `frontend/src/api/jobs.ts`:

```typescript
import {api} from "./client";
import type {CreateJobInput, Job, JobSummary, RollbackPreview, UploadedInput} from "../types/jobs";

export const getCurrentJob = () => api<Job | null>("/api/jobs/current", {method: "GET"});
export const getJob = (id: string) => api<Job>(`/api/jobs/${id}`, {method: "GET"});
export const listJobs = () => api<{items: JobSummary[]}>("/api/jobs", {method: "GET"});
export const createJob = (input: CreateJobInput) => api<Job>("/api/jobs", {
  method: "POST", body: JSON.stringify(input),
});
export const uploadInput = (file: File) => {
  const body = new FormData();
  body.append("file", file);
  return api<UploadedInput>("/api/uploads", {method: "POST", body});
};
export const pauseJob = (id: string) => api<Job>(`/api/jobs/${id}/pause`, {method: "POST"});
export const resumeJob = (id: string) => api<Job>(`/api/jobs/${id}/resume`, {method: "POST"});
export const retryJob = (id: string, stepId?: string) => api<Job>(`/api/jobs/${id}/retry`, {
  method: "POST", body: JSON.stringify({step_id: stepId ?? null, comment: ""}),
});
export const getRollbackPreview = (id: string, stepId: string) =>
  api<RollbackPreview>(`/api/jobs/${id}/rollback-preview?step_id=${encodeURIComponent(stepId)}`, {method: "GET"});
export const rollbackJob = (id: string, stepId: string, confirmed: string[]) => api<Job>(`/api/jobs/${id}/rollback`, {
  method: "POST", body: JSON.stringify({step_id: stepId, confirm_invalidated_step_ids: confirmed}),
});
export const reviewStep = (
  id: string, stepId: string, action: "approve" | "edit" | "retry" | "rollback",
  comment = "", patch: Record<string, unknown> = {},
) => api<Job>(`/api/jobs/${id}/steps/${stepId}/review`, {
  method: "POST", body: JSON.stringify({action, comment, patch}),
});
export const cancelJob = (id: string) => api<Job>(`/api/jobs/${id}/cancel`, {method: "POST"});
export const jobEventsUrl = (id: string) => `/api/jobs/${id}/events`;
```

- [ ] **Step 6: Run the API test and commit**

```powershell
npm test -- src/api/jobs.test.ts
git add package.json package-lock.json vitest.config.ts src/test src/api src/types
git commit -m "feat: add typed V5 job client"
```

Expected: 2 passed.

### Task 3: Create one global job store that survives navigation

**Files:**
- Create: `frontend/src/state/jobStore.ts`
- Create: `frontend/src/state/JobProvider.tsx`
- Test: `frontend/src/state/jobStore.test.ts`

- [ ] **Step 1: Write failing restoration and SSE tests**

Create `frontend/src/state/jobStore.test.ts`:

```typescript
import {afterEach, expect, it, vi} from "vitest";
import {createJobStore} from "./jobStore";

afterEach(() => vi.useRealTimers());

const eventSource = () => ({
  addEventListener: vi.fn(), close: vi.fn(), onopen: null, onerror: null,
} as unknown as EventSource);

it("loads the server current job only once for multiple subscribers", async () => {
  const getCurrent = vi.fn().mockResolvedValue({id: "job-1", status: "running", steps: []});
  const store = createJobStore({getCurrent, getJob: vi.fn(), eventSource});
  const first = store.subscribe(() => undefined);
  const second = store.subscribe(() => undefined);
  await store.start();
  expect(getCurrent).toHaveBeenCalledTimes(1);
  first(); second(); store.stop();
});

it("keeps the last job visible while a transient refresh fails", async () => {
  const getCurrent = vi.fn()
    .mockResolvedValueOnce({id: "job-1", status: "running", steps: []})
    .mockRejectedValueOnce(new Error("backend restart"));
  const store = createJobStore({getCurrent, getJob: vi.fn(), eventSource});
  await store.start();
  await store.refresh();
  expect(store.getSnapshot().job?.id).toBe("job-1");
  expect(store.getSnapshot().connection).toBe("reconnecting");
});

it("polls until the backend returns after a restart", async () => {
  vi.useFakeTimers();
  const restored = {id: "job-1", status: "running", steps: []};
  const getCurrent = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(restored);
  const store = createJobStore({getCurrent, getJob: vi.fn(), eventSource});
  await store.start();
  await vi.advanceTimersByTimeAsync(2000);
  expect(store.getSnapshot().job?.id).toBe("job-1");
  expect(store.getSnapshot().connection).toBe("online");
  store.stop();
});
```

- [ ] **Step 2: Run the tests and verify the store is missing**

```powershell
npm test -- src/state/jobStore.test.ts
```

Expected: FAIL during import.

- [ ] **Step 3: Implement an external store with one EventSource**

Create `frontend/src/state/jobStore.ts`:

```typescript
import {getCurrentJob, getJob, jobEventsUrl} from "../api/jobs";
import type {Job} from "../types/jobs";

type Snapshot = {job: Job | null; loading: boolean; connection: "online" | "reconnecting" | "offline"};
type Dependencies = {
  getCurrent: typeof getCurrentJob;
  getJob: typeof getJob;
  eventSource: (url: string) => EventSource;
};

const defaults: Dependencies = {
  getCurrent: getCurrentJob,
  getJob,
  eventSource: (url) => new EventSource(url),
};

export function createJobStore(deps: Dependencies = defaults) {
  let snapshot: Snapshot = {job: null, loading: true, connection: "offline"};
  const listeners = new Set<() => void>();
  let source: EventSource | null = null;
  let sourceJobId: string | null = null;
  let poll: number | null = null;
  let startPromise: Promise<void> | null = null;

  const emit = () => listeners.forEach((listener) => listener());
  const update = (next: Partial<Snapshot>) => {snapshot = {...snapshot, ...next}; emit();};
  const clearPolling = () => {
    if (poll !== null) window.clearInterval(poll);
    poll = null;
  };
  const beginPolling = () => {
    if (poll === null) poll = window.setInterval(() => void refresh(), 2000);
  };

  const connect = (job: Job) => {
    source?.close();
    source = deps.eventSource(jobEventsUrl(job.id));
    sourceJobId = job.id;
    source.addEventListener("job", () => void refreshJob(job.id));
    source.onopen = () => {clearPolling(); update({connection: "online"});};
    source.onerror = () => {
      source?.close(); source = null; sourceJobId = null;
      update({connection: "reconnecting"});
      beginPolling();
    };
  };

  const refreshJob = async (id: string) => {
    try {
      const job = await deps.getJob(id);
      clearPolling(); update({job, connection: "online"});
    } catch {
      update({connection: "reconnecting"}); beginPolling();
    }
  };

  const refresh = async () => {
    try {
      const job = await deps.getCurrent();
      update({job, loading: false, connection: "online"});
      clearPolling();
      if (job && (!source || sourceJobId !== job.id)) connect(job);
      if (!job) {source?.close(); source = null; sourceJobId = null;}
    } catch {
      update({loading: false, connection: "reconnecting"}); beginPolling();
    }
  };

  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) {listeners.add(listener); return () => listeners.delete(listener);},
    start() {startPromise ??= refresh(); return startPromise;},
    refresh,
    setJob(job: Job | null) {
      update({job});
      if (job) connect(job);
      else {source?.close(); source = null; sourceJobId = null;}
    },
    stop() {source?.close(); clearPolling(); source = null; sourceJobId = null;},
  };
}

export const jobStore = createJobStore();
```

- [ ] **Step 4: Bind the store and actions to React**

Create `frontend/src/state/JobProvider.tsx`:

```tsx
import {createContext, useContext, useEffect, useMemo, useSyncExternalStore} from "react";
import {cancelJob, pauseJob, resumeJob, retryJob} from "../api/jobs";
import {jobStore} from "./jobStore";

const Actions = createContext({
  pause: async () => undefined,
  resume: async () => undefined,
  retry: async (_stepId?: string) => undefined,
  cancel: async () => undefined,
});

export function JobProvider({children}: {children: React.ReactNode}) {
  useEffect(() => {void jobStore.start(); return () => jobStore.stop();}, []);
  const snapshot = useSyncExternalStore(jobStore.subscribe, jobStore.getSnapshot);
  const id = snapshot.job?.id;
  const actions = useMemo(() => ({
    pause: async () => {if (id) jobStore.setJob(await pauseJob(id));},
    resume: async () => {if (id) jobStore.setJob(await resumeJob(id));},
    retry: async (stepId?: string) => {if (id) jobStore.setJob(await retryJob(id, stepId));},
    cancel: async () => {if (id) jobStore.setJob(await cancelJob(id));},
  }), [id]);
  return <Actions.Provider value={actions}>{children}</Actions.Provider>;
}

export const useJob = () => useSyncExternalStore(jobStore.subscribe, jobStore.getSnapshot);
export const useJobActions = () => useContext(Actions);
```

- [ ] **Step 5: Run store tests and commit**

```powershell
npm test -- src/state/jobStore.test.ts
git add src/state
git commit -m "feat: keep current production job across routes"
```

Expected: 3 passed; a transient backend restart does not clear the displayed job and initial offline startup reconnects automatically.

### Task 4: Build the approved app shell and global task strip

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/app.css`
- Create: `frontend/src/components/layout/AppShell.tsx`
- Create: `frontend/src/components/jobs/GlobalTaskBar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/src/components/layout/AppShell.test.tsx`

- [ ] **Step 1: Write a failing route-persistence test**

Create `frontend/src/components/layout/AppShell.test.tsx`:

```tsx
import {render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter} from "react-router-dom";
import {vi} from "vitest";

vi.mock("../../state/JobProvider", () => ({
  useJob: () => ({
    connection: "online",
    loading: false,
    job: {
      id: "job-1", project_id: "归墟觉醒", status: "running", mode: "automatic",
      desired_state: "running",
      current_stage: "首尾帧视频生成", current_shot: "镜头 07 / 16", progress: 0.47,
      message: "正在生成", final_video: "", created_at: "2026-07-17T00:00:00Z",
      updated_at: "2026-07-17T00:00:00Z", steps: [],
    },
  }),
  useJobActions: () => ({pause: vi.fn(), resume: vi.fn(), retry: vi.fn(), cancel: vi.fn()}),
}));

import App from "../../App";

it("keeps the current task strip visible after navigation", async () => {
  render(<MemoryRouter initialEntries={["/production"]}><App /></MemoryRouter>);
  expect(await screen.findByText(/镜头 07/)).toBeVisible();
  await userEvent.click(screen.getByRole("link", {name: "算力监控"}));
  expect(screen.getByText(/镜头 07/)).toBeVisible();
});
```

- [ ] **Step 2: Run the test and verify the old tab-switching App fails**

```powershell
npm test -- src/components/layout/AppShell.test.tsx
```

Expected: FAIL because the current `App` has no routes or global task store.

- [ ] **Step 3: Create exact shared tokens**

Create `frontend/src/styles/tokens.css`:

```css
:root {
  color-scheme: dark;
  --bg: #071019; --surface: #0d1722; --surface-raised: #111f2d;
  --border: #223447; --text: #edf4f8; --muted: #90a6b8;
  --accent: #55d7e8; --success: #55dfa0; --warning: #ffbd59;
  --danger: #ff6b7e; --review: #a58cff;
  --r-sm: 10px; --r-md: 14px; --r-lg: 18px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 20px; --space-6: 24px; --space-8: 32px;
  font-family: Inter, "Microsoft YaHei", system-ui, sans-serif;
}
body {margin: 0; min-width: 320px; background: var(--bg); color: var(--text);}
```

- [ ] **Step 4: Implement the global task strip**

Create `frontend/src/components/jobs/GlobalTaskBar.tsx`:

```tsx
import {Button, Progress} from "antd";
import {Link} from "react-router-dom";
import {useJob, useJobActions} from "../../state/JobProvider";

export function GlobalTaskBar() {
  const {job, connection} = useJob();
  const actions = useJobActions();
  if (!job) return <div className="global-task empty">当前没有运行任务</div>;
  const running = ["queued", "running", "retry_wait"].includes(job.status);
  const pausing = job.status === "running" && job.desired_state === "paused";
  return (
    <section className={`global-task status-${job.status}`} aria-label="当前制作任务">
      <div className="task-copy">
        <strong>{job.project_id}</strong>
        <span>{job.current_shot || "准备中"} · {pausing ? "当前步骤完成后暂停" : (job.current_stage || job.message)}</span>
      </div>
      <Progress percent={Math.round(job.progress * 100)} showInfo={false} />
      <span className="connection">{connection === "online" ? "实时" : "正在恢复连接"}</span>
      {running && !pausing ? <Button onClick={() => void actions.pause()}>暂停</Button> : null}
      {pausing ? <Button onClick={() => void actions.resume()}>取消暂停请求</Button> : null}
      {job.status === "paused" ? <Button onClick={() => void actions.resume()}>继续</Button> : null}
      <Button><Link to="/tasks">任务中心</Link></Button>
    </section>
  );
}
```

- [ ] **Step 5: Replace tab state with route composition**

Create `AppShell` with a semantic `<nav>`, React Router `NavLink` items (never plain `<a href>` navigation), and `<Outlet>`. Configure these routes in `App.tsx`:

```tsx
<Routes>
  <Route element={<AppShell />}>
    <Route path="/" element={<Navigate to="/production" replace />} />
    <Route path="/production" element={<ProductionStudio />} />
    <Route path="/tasks" element={<TaskCenter />} />
    <Route path="/monitor" element={<Monitor />} />
    <Route path="/shots" element={<ShotManager />} />
    <Route path="/exports" element={<Download />} />
  </Route>
</Routes>
```

`AppShell` renders `<GlobalTaskBar />` above the route content, so the bar never belongs to `ProductionStudio`.

Wrap `App` in `BrowserRouter` and `JobProvider` inside `frontend/src/main.tsx`.

- [ ] **Step 6: Implement responsive shell CSS**

Create `frontend/src/styles/app.css` with fixed desktop rail, sticky task strip and mobile collapse:

```css
.app-shell {min-height: 100vh; display: grid; grid-template-columns: 220px minmax(0, 1fr);}
.app-nav {position: sticky; top: 0; height: 100vh; padding: 24px 16px; background: #08131e; border-right: 1px solid var(--border);}
.app-main {min-width: 0;}
.global-task {position: sticky; top: 0; z-index: 20; min-height: 64px; display: grid; grid-template-columns: minmax(240px, 1fr) minmax(180px, 320px) auto auto auto; gap: 16px; align-items: center; padding: 10px 24px; background: rgba(13,23,34,.96); border-bottom: 1px solid var(--border); backdrop-filter: blur(14px);}
.route-content {padding: 24px; max-width: 1440px; margin: 0 auto;}
@media (max-width: 760px) {
  .app-shell {grid-template-columns: 1fr;}
  .app-nav {position: static; height: auto; overflow-x: auto; display: flex; padding: 10px 12px;}
  .global-task {grid-template-columns: 1fr auto; padding: 10px 12px;}
  .global-task .ant-progress {grid-column: 1 / -1;}
  .route-content {padding: 14px;}
}
```

- [ ] **Step 7: Run the shell test and commit**

```powershell
npm test -- src/components/layout/AppShell.test.tsx
git add src/App.tsx src/main.tsx src/components/layout src/components/jobs/GlobalTaskBar.tsx src/styles
git commit -m "feat: add persistent V5 application shell"
```

Expected: navigation changes route content while the same current task remains visible.

### Task 5: Build the one-click production workspace

**Files:**
- Create: `frontend/src/pages/ProductionStudio.tsx`
- Create: `frontend/src/components/production/ProductionForm.tsx`
- Create: `frontend/src/components/production/LiveStagePanel.tsx`
- Test: `frontend/src/pages/ProductionStudio.test.tsx`

- [ ] **Step 1: Write failing input, duration and resolution tests**

Create `frontend/src/pages/ProductionStudio.test.tsx`:

```tsx
import {render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter} from "react-router-dom";
import {expect, it, vi} from "vitest";

import {ProductionStudio} from "./ProductionStudio";

const {createJobMock, uploadInputMock} = vi.hoisted(() => ({
  createJobMock: vi.fn().mockResolvedValue({id: "job-1"}),
  uploadInputMock: vi.fn().mockResolvedValue({
    path: "D:/AI_Manga_Studio/storage/uploads/source.csv",
    original_name: "shots.csv", input_type: "storyboard", size: 5,
  }),
}));
vi.mock("../api/jobs", () => ({createJob: createJobMock, uploadInput: uploadInputMock}));
vi.mock("../state/jobStore", () => ({jobStore: {setJob: vi.fn()}}));

function renderStudio() {
  return render(<MemoryRouter><ProductionStudio /></MemoryRouter>);
}


it("creates a manual-review storyboard job with custom resolution", async () => {
  renderStudio();
  await userEvent.upload(screen.getByLabelText("创作文件"), new File(["shots"], "shots.csv"));
  await userEvent.type(screen.getByLabelText("项目名称"), "归墟觉醒");
  await userEvent.click(screen.getByRole("radio", {name: "人工审核模式"}));
  await userEvent.clear(screen.getByLabelText("单镜头时长"));
  await userEvent.type(screen.getByLabelText("单镜头时长"), "12");
  await userEvent.click(screen.getByLabelText("分辨率"));
  await userEvent.click(screen.getByRole("option", {name: "自定义分辨率"}));
  await userEvent.clear(screen.getByLabelText("宽度"));
  await userEvent.type(screen.getByLabelText("宽度"), "1080");
  await userEvent.clear(screen.getByLabelText("高度"));
  await userEvent.type(screen.getByLabelText("高度"), "1920");
  await userEvent.click(screen.getByRole("button", {name: "生成制作计划并开始"}));
  expect(createJobMock).toHaveBeenCalledWith(expect.objectContaining({
    input_path: "D:/AI_Manga_Studio/storage/uploads/source.csv",
    input_type: "storyboard", mode: "manual_review", shot_duration: 12,
    width: 1080, height: 1920,
  }));
});
```

- [ ] **Step 2: Run the test and verify the production workspace is missing**

```powershell
npm test -- src/pages/ProductionStudio.test.tsx
```

Expected: FAIL during import or missing accessible controls.

- [ ] **Step 3: Implement the production form**

`ProductionForm` must use Ant Design `Upload.Dragger`, `Radio.Group`, `InputNumber`, `Select` and `Switch`. Define resolution presets at module scope:

```typescript
const RESOLUTIONS = [
  {label: "竖屏 1080 × 1920", value: "1080x1920"},
  {label: "横屏 1920 × 1080", value: "1920x1080"},
  {label: "电影宽屏 2560 × 1080", value: "2560x1080"},
  {label: "自定义分辨率", value: "custom"},
];
```

On submit, upload the selected file first, use the server-returned managed `path` and detected `input_type`, call `createJob`, then `jobStore.setJob(job)`. Generate the idempotency key once per submit using `crypto.randomUUID()`:

```tsx
const handleFinish = async (values: FormValues) => {
  if (!sourceFile) throw new Error("请选择创作文件");
  const uploaded = await uploadInput(sourceFile);
  const [width, height] = values.resolution === "custom"
    ? [values.width, values.height]
    : values.resolution.split("x").map(Number);
  const job = await createJob({
    project_id: values.projectName.trim(),
    input_path: uploaded.path,
    input_type: uploaded.input_type,
    mode: values.mode,
    shot_duration: values.shotDuration,
    width, height, fps: values.fps,
    options: COMPLETE_SOUND_OPTIONS,
    idempotency_key: crypto.randomUUID(),
  });
  jobStore.setJob(job);
};
```

Define the complete sound/no-fallback options at module scope:

```typescript
const COMPLETE_SOUND_OPTIONS = {
  tts_enabled: true,
  lipsync_enabled: true,
  subtitles_enabled: true,
  sfx_enabled: true,
  bgm_enabled: true,
  forbid_fallback_artifacts: true,
} as const;
```

- [ ] **Step 4: Implement the approved two-column workspace**

`ProductionStudio` renders the form in the open main area and `LiveStagePanel` in the right rail. Use this DOM shape so desktop and mobile layouts remain predictable:

```tsx
<div className="production-grid">
  <main className="production-canvas">
    <h1>开始一部新短剧</h1>
    <p>系统自动识别小说、剧本或分镜表，并生成统一制作计划。</p>
    <ProductionForm />
  </main>
  <aside className="live-stage-rail" aria-label="实时制作链路">
    <LiveStagePanel />
  </aside>
</div>
```

Add CSS:

```css
.production-grid {display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 20px;}
.production-canvas, .live-stage-rail {background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg);}
.production-canvas {padding: 28px;}.live-stage-rail {padding: 20px;}
@media (max-width: 1000px) {.production-grid {grid-template-columns: 1fr;}}
```

- [ ] **Step 5: Run workspace tests and commit**

```powershell
npm test -- src/pages/ProductionStudio.test.tsx
git add src/pages/ProductionStudio.tsx src/components/production src/styles/app.css
git commit -m "feat: build one-click short drama workspace"
```

Expected: the submitted request carries all selected settings and enables the complete sound chain.

### Task 6: Add task center, failure recovery and manual review

**Files:**
- Create: `frontend/src/pages/TaskCenter.tsx`
- Create: `frontend/src/components/jobs/StageTimeline.tsx`
- Create: `frontend/src/components/jobs/FailurePanel.tsx`
- Create: `frontend/src/components/jobs/ReviewPanel.tsx`
- Test: `frontend/src/components/jobs/FailurePanel.test.tsx`
- Test: `frontend/src/components/jobs/ReviewPanel.test.tsx`

- [ ] **Step 1: Write failing failure-action tests**

Create `frontend/src/components/jobs/FailurePanel.test.tsx`:

```tsx
import {render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, it, vi} from "vitest";

import {FailurePanel} from "./FailurePanel";

const retryMock = vi.fn();

it("retries the failed step without restarting the job", async () => {
  render(<FailurePanel
    jobId="job-1"
    step={{
      id: "failed-step-7", stage_key: "shot_video", shot_id: "shot-07",
      status: "failed", attempt: 4, progress: 0, error_code: "COMFY_NO_OUTPUT",
      error_message: "视频模型节点缺失",
    }}
    onRetry={retryMock}
    onCancel={vi.fn()}
  />);
  expect(screen.getByText("已完成成果将保留")).toBeVisible();
  await userEvent.click(screen.getByRole("button", {name: "修复后从本步骤继续"}));
  expect(retryMock).toHaveBeenCalledWith("failed-step-7");
});
```

Create `frontend/src/components/jobs/ReviewPanel.test.tsx`:

```tsx
import {render, screen} from "@testing-library/react";
import {expect, it, vi} from "vitest";

import {ReviewPanel} from "./ReviewPanel";
import type {JobStep, StepStatus} from "../../types/jobs";

const step = (status: StepStatus): JobStep => ({
  id: "step-1", stage_key: "storyboard", status, attempt: 0,
  progress: 1, error_code: "", error_message: "",
});

it("shows review controls only for waiting_review", () => {
  const {rerender} = render(<ReviewPanel jobId="job-1" step={step("running")} onReview={vi.fn()} />);
  expect(screen.queryByRole("button", {name: "批准并继续"})).not.toBeInTheDocument();
  rerender(<ReviewPanel jobId="job-1" step={step("waiting_review")} onReview={vi.fn()} />);
  expect(screen.getByRole("button", {name: "批准并继续"})).toBeVisible();
});
```

- [ ] **Step 2: Run the tests and verify the components are missing**

```powershell
npm test -- src/components/jobs/FailurePanel.test.tsx src/components/jobs/ReviewPanel.test.tsx
```

Expected: FAIL during import.

- [ ] **Step 3: Implement stage and shot progress**

`StageTimeline` groups job steps by `stage_key`, derives status during render, and displays completed count, active shot and retry count. Build a `Map` once with `useMemo` when the steps array changes; do not chain repeated `filter` calls for every stage.

Use these user-facing status labels:

```typescript
const STATUS_LABEL: Record<StepStatus, string> = {
  pending: "等待", queued: "排队中", running: "正在进行",
  waiting_review: "等待人工审核", retry_wait: "等待重试", failed: "失败",
  completed: "已完成", invalidated: "需要重做", cancelled: "已取消",
};
```

- [ ] **Step 4: Implement explicit failure recovery**

`FailurePanel` renders only when `job.status === "failed"`. Include:

```tsx
import {useState} from "react";
import {Alert, Button, Modal, Select} from "antd";
import type {JobStep} from "../../types/jobs";

type FailurePanelProps = {
  jobId: string;
  step: JobStep;
  onRetry: (stepId: string) => Promise<void> | void;
  onCancel: () => Promise<void> | void;
  onChangeWorkflow?: (workflowId: string) => Promise<void> | void;
  onPreviewRollback?: (stepId: string) => Promise<string[]>;
  onRollback?: (stepId: string, affected: string[]) => Promise<void> | void;
};

export function FailurePanel({step, onRetry, onCancel, onChangeWorkflow, onPreviewRollback, onRollback}: FailurePanelProps) {
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const [rollbackOpen, setRollbackOpen] = useState(false);
  const [rollbackStepIds, setRollbackStepIds] = useState<string[]>([]);
  const [workflow, setWorkflow] = useState("wan22");
  const openRollback = async () => {
    const affected = await onPreviewRollback?.(step.id) ?? [step.id];
    setRollbackStepIds(affected);
    setRollbackOpen(true);
  };

  return <section aria-label="故障处理">
<Alert type="error" message={`${step.stage_key} · ${step.shot_id ?? "项目阶段"}`} description={step.error_message} />
<p>已自动重试 {Math.max(0, step.attempt - 1)}/3；已完成成果将保留。</p>
<Button type="primary" onClick={() => void onRetry(step.id)}>修复后从本步骤继续</Button>
<Button onClick={() => setWorkflowOpen(true)}>更换工作流</Button>
<Button onClick={() => void openRollback()}>回退到上一步</Button>
<Button danger onClick={() => void onCancel()}>取消任务</Button>
<Modal open={workflowOpen} title="更换视频工作流" onCancel={() => setWorkflowOpen(false)} onOk={() => void onChangeWorkflow?.(workflow)}>
  <Select aria-label="视频工作流" value={workflow} onChange={setWorkflow} options={[
    {label: "Wan 2.2 首尾帧", value: "wan22"}, {label: "LTX 2.3 首尾帧", value: "ltx23"},
  ]} />
</Modal>
<Modal open={rollbackOpen} title="确认回退" onCancel={() => setRollbackOpen(false)} onOk={() => void onRollback?.(step.id, rollbackStepIds)}>
  <p>以下步骤将失效并重新生成：</p><ul>{rollbackStepIds.map((id) => <li key={id}>{id}</li>)}</ul>
</Modal>
</section>;
}
```

The rollback modal first calls the preview endpoint and lists every step that will become invalid. Only then send the exact confirmed IDs to `/rollback`.

- [ ] **Step 5: Implement manual review controls**

`ReviewPanel` appears only for `waiting_review` and offers `批准并继续`, `编辑参数`, `重做当前阶段`, and `回退上游`. Send actions to:

```typescript
POST /api/jobs/{jobId}/steps/{stepId}/review
{action: "approve" | "edit" | "retry" | "rollback", comment, patch}
```

Implement the component with this contract:

```tsx
import {Button, Input, Space} from "antd";
import {useState} from "react";
import type {JobStep} from "../../types/jobs";

type ReviewAction = "approve" | "edit" | "retry" | "rollback";
type ReviewPanelProps = {
  jobId: string;
  step: JobStep;
  onReview: (action: ReviewAction, comment: string, patch: Record<string, unknown>) => Promise<void> | void;
};

export function ReviewPanel({step, onReview}: ReviewPanelProps) {
  const [comment, setComment] = useState("");
  if (step.status !== "waiting_review") return null;
  return <section aria-label="人工审核">
    <Input.TextArea aria-label="审核意见" value={comment} onChange={(event) => setComment(event.target.value)} />
    <Space wrap>
      <Button type="primary" onClick={() => void onReview("approve", comment, {})}>批准并继续</Button>
      <Button onClick={() => void onReview("edit", comment, {open_editor: true})}>编辑参数</Button>
      <Button onClick={() => void onReview("retry", comment, {})}>重做当前阶段</Button>
      <Button danger onClick={() => void onReview("rollback", comment, {})}>回退上游</Button>
    </Space>
  </section>;
}
```

Do not keep editable production parameters only in component state after submit; the response job replaces the global store snapshot.

- [ ] **Step 6: Implement task history**

`TaskCenter` calls `listJobs()` once on entry and renders a table with project, status, current stage, progress, updated time and open action. Selecting a row loads `/api/jobs/{id}` and renders `StageTimeline`, `FailurePanel` and `ReviewPanel` in a detail drawer. Wire `FailurePanel.onPreviewRollback` to `(await getRollbackPreview(jobId, stepId)).invalidated_step_ids`, `onRollback` to `rollbackJob`, and `onChangeWorkflow` to `reviewStep(jobId, stepId, "edit", "更换工作流", {options: {video_workflow: workflowId}})`. Wire `ReviewPanel.onReview` to `reviewStep`. Every command response replaces the global store snapshot.

- [ ] **Step 7: Run component tests and commit**

```powershell
npm test -- src/components/jobs/FailurePanel.test.tsx src/components/jobs/ReviewPanel.test.tsx
git add src/pages/TaskCenter.tsx src/components/jobs src/api/jobs.ts src/styles/app.css
git commit -m "feat: add failure recovery and manual review UI"
```

Expected: recovery retries the exact failed step; review controls never appear during normal automatic execution.

### Task 7: Complete accessibility, responsive behavior and bundle checks

**Files:**
- Create: `frontend/eslint.config.mjs`
- Modify: `frontend/package.json`
- Modify: `frontend/src/styles/app.css`
- Test: all frontend tests

- [ ] **Step 1: Create a valid ESLint configuration**

Create `frontend/eslint.config.mjs`:

```javascript
import tseslint from "@typescript-eslint/eslint-plugin";
import parser from "@typescript-eslint/parser";

export default [{
  files: ["src/**/*.{ts,tsx}"],
  languageOptions: {parser, parserOptions: {ecmaVersion: "latest", sourceType: "module", ecmaFeatures: {jsx: true}}},
  plugins: {"@typescript-eslint": tseslint},
  rules: {
    "@typescript-eslint/no-explicit-any": "error",
    "@typescript-eslint/no-unused-vars": ["error", {argsIgnorePattern: "^_"}],
  },
}];
```

Change the lint script to `eslint src`.

- [ ] **Step 2: Run static and unit checks**

```powershell
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

Expected: all commands exit 0. Record the emitted JS bundle size; if the main chunk exceeds 700 kB gzip-uncompressed, lazy-load Monitor, ShotManager and Download with `React.lazy`.

- [ ] **Step 3: Verify desktop and mobile layout in Browser/IAB**

The flow under test is: `/production` → start or restore a running job → navigate to `/monitor` and `/tasks` → the global task strip remains visible and consistent.

Use Browser/IAB and check:

1. URL and title identify the V5 app;
2. DOM snapshot contains “开始一部新短剧” and the global task strip;
3. console has no relevant warnings or errors;
4. desktop screenshot at 1440×900 has no clipping or overflow;
5. mobile screenshot at 390×844 has collapsed navigation and readable controls;
6. navigation interaction keeps the same job ID and progress visible;
7. failed job state shows retry/change-workflow/rollback/cancel;
8. `waiting_review` shows review actions, while automatic running state does not.

- [ ] **Step 4: Compare reference and implementation with `view_image`**

Capture the latest Browser screenshots outside committed source, then inspect both the accepted concept and browser render with `view_image` at native size. Maintain a mismatch ledger for:

```text
global strip height and spacing
left rail width and selected state
main/right column ratio
surface, border and semantic colors
type scale and Chinese line wrapping
form control density
failure action hierarchy
mobile collapse and overflow
```

Fix every material mismatch and repeat Browser reload, console, screenshot and `view_image` comparison until no material mismatch remains.

- [ ] **Step 5: Commit the verified Web console**

```powershell
git add frontend
git commit -m "feat: complete verified V5 production console"
```

## Plan verification checkpoint

Run:

```powershell
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

Browser acceptance must prove:

- the same task strip remains visible after every navigation and refresh;
- server state, not component-local state, restores progress;
- transient backend restart shows “正在恢复连接” without clearing the last job;
- a failed job remains on the fault step and preserves completed work;
- manual controls appear only in manual review mode;
- the rendered desktop and mobile screens faithfully match the approved concept after direct `view_image` comparison.
