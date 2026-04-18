from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .backend import ALLOWED_DOCUMENT_KINDS, ResearchBackend


JSONDict = dict[str, Any]
ToolHandler = Callable[[ResearchBackend, JSONDict], JSONDict]


class ToolValidationError(ValueError):
    """Raised when tool arguments do not match the contract schema."""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    title: str
    description: str
    input_schema: JSONDict
    handler: ToolHandler

    def to_mcp_tool(self) -> JSONDict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "readOnlyHint": True,
                "idempotentHint": True,
            },
        }


def dumps_payload(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def build_tool_registry() -> dict[str, ToolSpec]:
    tools = (
        ToolSpec(
            name="search",
            title="Search Documents",
            description="Search canonical persisted documents globally.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_handle_search,
        ),
        ToolSpec(
            name="fetch",
            title="Fetch Document",
            description="Fetch one canonical document by document ID.",
            input_schema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
                "additionalProperties": False,
            },
            handler=_handle_fetch,
        ),
        ToolSpec(
            name="list_notebooks",
            title="List Notebooks",
            description="List canonical notebook summaries.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=_handle_list_notebooks,
        ),
        ToolSpec(
            name="get_notebook",
            title="Get Notebook",
            description="Fetch one canonical notebook by notebook ID.",
            input_schema={
                "type": "object",
                "properties": {"notebook_id": {"type": "string"}},
                "required": ["notebook_id"],
                "additionalProperties": False,
            },
            handler=_handle_get_notebook,
        ),
        ToolSpec(
            name="list_notebook_documents",
            title="List Notebook Documents",
            description="List canonical documents for one notebook.",
            input_schema={
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string"},
                    "document_kind": {
                        "type": "string",
                        "enum": list(ALLOWED_DOCUMENT_KINDS),
                    },
                },
                "required": ["notebook_id"],
                "additionalProperties": False,
            },
            handler=_handle_list_notebook_documents,
        ),
        ToolSpec(
            name="search_notebook",
            title="Search Notebook",
            description="Search canonical documents within one notebook.",
            input_schema={
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string"},
                    "query": {"type": "string"},
                    "document_kind": {
                        "type": "string",
                        "enum": list(ALLOWED_DOCUMENT_KINDS),
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["notebook_id", "query"],
                "additionalProperties": False,
            },
            handler=_handle_search_notebook,
        ),
        ToolSpec(
            name="get_sync_status",
            title="Get Sync Status",
            description="Return sync status for one notebook or the whole store.",
            input_schema={
                "type": "object",
                "properties": {"notebook_id": {"type": "string"}},
                "additionalProperties": False,
            },
            handler=_handle_get_sync_status,
        ),
    )
    return {tool.name: tool for tool in tools}


def validate_tool_arguments(arguments: Mapping[str, Any] | None, schema: Mapping[str, Any]) -> JSONDict:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise ToolValidationError("Tool arguments must be a JSON object.")

    payload = dict(arguments)
    properties = dict(schema.get("properties", {}))
    required = set(schema.get("required", []))
    additional_allowed = schema.get("additionalProperties", True)

    missing = [name for name in required if name not in payload]
    if missing:
        raise ToolValidationError(f"Missing required field(s): {', '.join(sorted(missing))}.")

    if not additional_allowed:
        extras = [name for name in payload if name not in properties]
        if extras:
            raise ToolValidationError(
                f"Unexpected field(s): {', '.join(sorted(extras))}."
            )

    for field_name, field_schema in properties.items():
        if field_name not in payload:
            continue
        _validate_field(field_name, payload[field_name], field_schema)

    return payload


def tool_result_text(payload: Any) -> JSONDict:
    return {
        "content": [
            {
                "type": "text",
                "text": dumps_payload(payload),
            }
        ],
        "isError": False,
    }


def _validate_field(field_name: str, value: Any, schema: Mapping[str, Any]) -> None:
    field_type = schema.get("type")
    if field_type == "string":
        if not isinstance(value, str):
            raise ToolValidationError(f"Field '{field_name}' must be a string.")
    elif field_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ToolValidationError(f"Field '{field_name}' must be an integer.")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            raise ToolValidationError(
                f"Field '{field_name}' must be greater than or equal to {minimum}."
            )
        if maximum is not None and value > maximum:
            raise ToolValidationError(
                f"Field '{field_name}' must be less than or equal to {maximum}."
            )
    else:
        raise ToolValidationError(f"Unsupported schema type for '{field_name}': {field_type}.")

    allowed_values = schema.get("enum")
    if allowed_values is not None and value not in allowed_values:
        raise ToolValidationError(
            f"Field '{field_name}' must be one of: {', '.join(allowed_values)}."
        )


def _handle_search(backend: ResearchBackend, arguments: JSONDict) -> JSONDict:
    return tool_result_text({"results": list(backend.search(arguments["query"]))})


def _handle_fetch(backend: ResearchBackend, arguments: JSONDict) -> JSONDict:
    document = dict(backend.fetch(arguments["id"]))
    return tool_result_text(
        {
            "id": document["id"],
            "title": document["title"],
            "text": document["text"],
            "url": document["url"],
            "metadata": dict(document["metadata"]),
        }
    )


def _handle_list_notebooks(backend: ResearchBackend, arguments: JSONDict) -> JSONDict:
    return tool_result_text(list(backend.list_notebooks()))


def _handle_get_notebook(backend: ResearchBackend, arguments: JSONDict) -> JSONDict:
    return tool_result_text(dict(backend.get_notebook(arguments["notebook_id"])))


def _handle_list_notebook_documents(
    backend: ResearchBackend, arguments: JSONDict
) -> JSONDict:
    return tool_result_text(
        list(
            backend.list_notebook_documents(
                notebook_id=arguments["notebook_id"],
                document_kind=arguments.get("document_kind"),
            )
        )
    )


def _handle_search_notebook(backend: ResearchBackend, arguments: JSONDict) -> JSONDict:
    return tool_result_text(
        list(
            backend.search_notebook(
                notebook_id=arguments["notebook_id"],
                query=arguments["query"],
                document_kind=arguments.get("document_kind"),
                limit=arguments.get("limit", 10),
            )
        )
    )


def _handle_get_sync_status(backend: ResearchBackend, arguments: JSONDict) -> JSONDict:
    return tool_result_text(dict(backend.get_sync_status(arguments.get("notebook_id"))))
