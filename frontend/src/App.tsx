import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import StudioShell from "@/studio/StudioShell";
import ProjectCockpit from "@/studio/ProjectCockpit";
import StoryAssetsWorkspace from "@/studio/StoryAssetsWorkspace";
import StoryboardDirectorWorkspace from "@/studio/StoryboardDirectorWorkspace";
import AdvancedCanvasWorkspace from "@/studio/AdvancedCanvasWorkspace";
import TimelineQcWorkspace from "@/studio/TimelineQcWorkspace";
import { LEGACY_ROUTE_REDIRECTS } from "@/studio/studioNavigation";
import "@/styles/unified-studio.css";

const App: React.FC = () => (
  <Routes>
    <Route element={<StudioShell />}>
      <Route path="/project" element={<ProjectCockpit />} />
      <Route path="/story-assets" element={<StoryAssetsWorkspace />} />
      <Route path="/director" element={<StoryboardDirectorWorkspace />} />
      <Route path="/canvas" element={<AdvancedCanvasWorkspace />} />
      <Route path="/timeline" element={<TimelineQcWorkspace />} />
    </Route>

    {Object.entries(LEGACY_ROUTE_REDIRECTS).map(([from, to]) => (
      <Route key={from} path={from} element={<Navigate to={to} replace />} />
    ))}
    <Route path="/os/*" element={<Navigate to="/project" replace />} />
    <Route path="/" element={<Navigate to="/project" replace />} />
    <Route path="*" element={<Navigate to="/project" replace />} />
  </Routes>
);

export default App;
