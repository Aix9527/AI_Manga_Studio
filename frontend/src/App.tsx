import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import WorkbenchShell from "@/components/workbench/WorkbenchShell";
import ProjectOverview from "@/pages/ProjectOverview";
import AssetLibrary from "@/pages/AssetLibrary";
import StoryCharacterWorkspace from "@/pages/StoryCharacterWorkspace";
import StoryboardDirector from "@/pages/StoryboardDirector";
import TaskWorkspace from "@/pages/TaskWorkspace";
import QualityWorkspace from "@/pages/QualityWorkspace";
import ExportStudio from "@/pages/ExportStudio";
import AICreatorStudio from "@/pages/AICreatorStudio";
import StudioDashboard from "@/pages/StudioDashboard";
import DirectorEvolutionCenter from "@/pages/DirectorEvolutionCenter";
import IndustrialStudio from "@/pages/IndustrialStudio";
import PromptStudio from "@/pages/PromptStudio";
import ProductionConsole from "@/pages/ProductionConsole";
import PromptOS from "@/pages/PromptOS";
import ProductionIntelligence from "@/pages/ProductionIntelligence";
import KnowledgeGraph from "@/pages/KnowledgeGraph";
import DigitalTwin from "@/pages/DigitalTwin";
import CommandCenter from "@/pages/CommandCenter";
import ProducerAgent from "@/pages/ProducerAgent";
import WorkflowVisualizer from "@/pages/WorkflowVisualizer";
import SOPCenter from "@/pages/SOPCenter";
import ProductionStudioV1 from "@/pages/ProductionStudioV1";
import "@/styles/workspace-pages.css";
import "@/styles/assets.css";
import "@/styles/task-quality.css";
import "@/styles/export.css";
import "@/styles/creator.css";
import "@/styles/studio.css";
import CoreOSShell from "@/core_os/layout/AppShell";
import CoreProjectCenter from "@/core_os/pages/ProjectCenter";
import CoreCreativeStudio from "@/core_os/pages/CreativeStudio";
import CoreProductionStudio from "@/core_os/pages/ProductionStudio";
import CoreAssetBrowser from "@/core_os/pages/AssetBrowser";
import CoreReviewCenter from "@/core_os/pages/ReviewCenter";
import CoreExportCenter from "@/core_os/pages/ExportCenter";
import CoreSettings from "@/core_os/pages/Settings";

const App: React.FC = () => (
  <Routes>
    <Route element={<WorkbenchShell />}>
      <Route path="/overview" element={<ProjectOverview />} />
      <Route path="/story" element={<StoryCharacterWorkspace />} />
      <Route path="/director" element={<StoryboardDirector />} />
      <Route path="/creator" element={<AICreatorStudio />} />
      <Route path="/assets" element={<AssetLibrary />} />
      <Route path="/tasks" element={<TaskWorkspace manageLifecycle={false} />} />
      <Route path="/quality" element={<QualityWorkspace />} />
      <Route path="/studio" element={<StudioDashboard />} />
      <Route path="/evolution" element={<DirectorEvolutionCenter />} />
      <Route path="/industrial" element={<IndustrialStudio />} />
      <Route path="/prompt-studio" element={<PromptStudio />} />
      <Route path="/production-console" element={<ProductionConsole />} />
      <Route path="/prompt-os" element={<PromptOS />} />
      <Route path="/production-intelligence" element={<ProductionIntelligence />} />
      <Route path="/knowledge-graph" element={<KnowledgeGraph />} />
      <Route path="/digital-twin" element={<DigitalTwin />} />
      <Route path="/command-center" element={<CommandCenter />} />
      <Route path="/producer-agent" element={<ProducerAgent />} />
      <Route path="/workflow" element={<WorkflowVisualizer />} />
      <Route path="/sop-center" element={<SOPCenter />} />
      <Route path="/production-studio-v1" element={<ProductionStudioV1 />} />
      <Route path="/export" element={<ExportStudio />} />
    </Route>
    <Route path="/os" element={<CoreOSShell />}>
      <Route path="projects" element={<CoreProjectCenter />} />
      <Route path="creative" element={<CoreCreativeStudio />} />
      <Route path="production" element={<CoreProductionStudio />} />
      <Route path="assets" element={<CoreAssetBrowser />} />
      <Route path="review" element={<CoreReviewCenter />} />
      <Route path="export" element={<CoreExportCenter />} />
      <Route path="settings" element={<CoreSettings />} />
    </Route>
    <Route path="/" element={<Navigate to="/overview" replace />} />
    <Route path="/characters" element={<Navigate to="/story" replace />} />
    <Route path="/story-graph" element={<Navigate to="/story" replace />} />
    <Route path="/storyboard" element={<Navigate to="/director" replace />} />
    <Route path="/pipeline" element={<Navigate to="/tasks" replace />} />
    <Route path="*" element={<Navigate to="/overview" replace />} />
  </Routes>
);

export default App;
