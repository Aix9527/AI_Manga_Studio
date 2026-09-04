export interface ProductionTemplateVersion {
  id: string;
  project_id: string;
  version: number;
  name: string;
  schema_version: number;
  content_json: string;
  content_sha256: string;
  compiled_json: string;
  compiled_sha256: string;
  status: "active" | "archived" | string;
  created_at: string;
  published_at: string | null;
}

export interface ProductionTemplateList {
  project_id: string;
  latest_version: number;
  published_version: number | null;
  versions: ProductionTemplateVersion[];
}

export interface PublishedProductionTemplate {
  project_id: string;
  published: boolean;
  template: ProductionTemplateVersion | null;
}

export interface ProductionTemplateSaveRequest {
  name: string;
  schema_version: 1;
  canvas: {
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
  };
  production: {
    shot_duration: number;
    width: number;
    height: number;
    fps: number;
    options: {
      style: string;
      local_first: boolean;
    };
  };
  stage_policy: {
    stages: Array<Record<string, unknown>>;
  };
}

export interface CompiledProductionTemplate {
  schema_version?: number;
  production?: {
    shot_duration?: number;
    width?: number;
    height?: number;
    fps?: number;
    options?: {
      style?: string;
      local_first?: boolean;
    };
  };
  canonical_stages?: string[];
  stage_policy?: Array<Record<string, unknown>>;
}
