from __future__ import annotations

import hashlib
import json

from backend.workspace.models import (
    ProductionTemplateList,
    ProductionTemplateSaveRequest,
    ProductionTemplateVersion,
    PublishedProductionTemplate,
)
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.template_compiler import (
    CanonicalTemplateCompiler,
    TemplateValidationError,
    normalize_json,
)


class TemplateVersionNotFound(ValueError):
    code = "TEMPLATE_VERSION_NOT_FOUND"


class TemplatePublishConflict(ValueError):
    code = "TEMPLATE_PUBLISH_CONFLICT"


class ProductionTemplateService:
    def __init__(
        self,
        repo: WorkspaceRepository,
        compiler: CanonicalTemplateCompiler | None = None,
    ) -> None:
        self.repo = repo
        self.compiler = compiler or CanonicalTemplateCompiler()

    def save(
        self,
        project_id: str,
        request: ProductionTemplateSaveRequest,
    ) -> ProductionTemplateVersion:
        source = request.model_dump(mode="json")
        compiled = self.compiler.compile(source)
        content_json = normalize_json(source)
        compiled_json = normalize_json(compiled)
        payload: dict[str, object] = {
            "name": request.name,
            "schema_version": request.schema_version,
            "content_json": content_json,
            "content_sha256": _sha256_text(content_json),
            "compiled_json": compiled_json,
            "compiled_sha256": _sha256_text(compiled_json),
        }
        return self.repo.save_production_template_version(project_id, payload)

    def list(self, project_id: str) -> ProductionTemplateList:
        return self.repo.list_production_template_versions(project_id)

    def get(self, project_id: str, version: int) -> ProductionTemplateVersion:
        value = self.repo.get_production_template_version(project_id, version)
        if value is None:
            raise TemplateVersionNotFound("template version not found")
        return value

    def published(self, project_id: str) -> PublishedProductionTemplate:
        value = self.repo.get_published_production_template(project_id)
        if value is None:
            return PublishedProductionTemplate(project_id=project_id, published=False, template=None)
        self._verify_stored(value)
        return PublishedProductionTemplate(project_id=project_id, published=True, template=value)

    def publish(self, project_id: str, version: int) -> ProductionTemplateVersion:
        value = self.get(project_id, version)
        self._verify_stored(value)
        try:
            return self.repo.publish_production_template(project_id, version)
        except ValueError as error:
            raise TemplatePublishConflict(str(error)) from error

    def _verify_stored(self, value: ProductionTemplateVersion) -> None:
        if value.status == "archived":
            raise TemplatePublishConflict("archived template cannot be published")
        if _sha256_text(value.content_json) != value.content_sha256:
            raise TemplatePublishConflict("template source hash mismatch")
        if _sha256_text(value.compiled_json) != value.compiled_sha256:
            raise TemplatePublishConflict("template compiled hash mismatch")
        try:
            source = json.loads(value.content_json)
            compiled = json.loads(value.compiled_json)
        except json.JSONDecodeError as error:
            raise TemplatePublishConflict("template JSON is invalid") from error
        if not isinstance(source, dict) or not isinstance(compiled, dict):
            raise TemplatePublishConflict("template payload must be an object")
        if int(source.get("schema_version") or 0) != 1:
            raise TemplatePublishConflict("template schema is incompatible")
        try:
            rebuilt = self.compiler.compile(source)
        except TemplateValidationError as error:
            raise TemplatePublishConflict(error.message) from error
        if normalize_json(rebuilt) != normalize_json(compiled):
            raise TemplatePublishConflict("compiled template no longer matches source")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
