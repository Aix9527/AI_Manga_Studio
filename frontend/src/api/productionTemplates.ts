import { request } from "@/api/client";
import type {
  ProductionTemplateList,
  ProductionTemplateSaveRequest,
  ProductionTemplateVersion,
  PublishedProductionTemplate,
} from "@/types/productionTemplates";

const basePath = (projectId: string) => `/workspace/${encodeURIComponent(projectId)}`;

export function saveProductionTemplate(
  projectId: string,
  value: ProductionTemplateSaveRequest,
): Promise<ProductionTemplateVersion> {
  return request<ProductionTemplateVersion>(`${basePath(projectId)}/production-templates`, {
    method: "POST",
    body: JSON.stringify(value),
  });
}

export function listProductionTemplates(projectId: string): Promise<ProductionTemplateList> {
  return request<ProductionTemplateList>(`${basePath(projectId)}/production-templates`);
}

export function getProductionTemplate(
  projectId: string,
  version: number,
): Promise<ProductionTemplateVersion> {
  return request<ProductionTemplateVersion>(`${basePath(projectId)}/production-templates/${version}`);
}

export function publishProductionTemplate(
  projectId: string,
  version: number,
): Promise<ProductionTemplateVersion> {
  return request<ProductionTemplateVersion>(`${basePath(projectId)}/production-templates/${version}/publish`, {
    method: "POST",
  });
}

export function getPublishedProductionTemplate(projectId: string): Promise<PublishedProductionTemplate> {
  return request<PublishedProductionTemplate>(`${basePath(projectId)}/production-template/published`);
}
