"""Parse Clang/LLVM YAML optimization record streams (.opt.yaml)."""

from __future__ import annotations

from typing import Any, cast

import yaml


def _mapping_with_kind(loader: yaml.SafeLoader, node: yaml.Node, kind: str) -> dict[str, Any]:
    if isinstance(node, yaml.MappingNode):
        mapping = loader.construct_mapping(node, deep=True)
        data = {str(k): v for k, v in mapping.items()}
    elif isinstance(node, yaml.ScalarNode):
        value = loader.construct_object(node, deep=True)  # type: ignore[no-untyped-call]
        data = {"value": cast(Any, value)}
    else:
        data = {}
    data["Kind"] = kind
    return data


class OptYamlLoader(yaml.SafeLoader):
    """YAML loader that preserves ``!Missed`` / ``!Passed`` / ``!Analysis`` tags."""


def _register_tags(loader: type[OptYamlLoader]) -> None:
    def register(tag: str, kind: str) -> None:
        def ctor(loader: yaml.SafeLoader, node: yaml.Node) -> dict[str, Any]:
            return _mapping_with_kind(loader, node, kind)

        loader.add_constructor(tag, ctor)

    register("!Missed", "missed")
    register("!Passed", "passed")
    register("!Analysis", "analysis")


_register_tags(OptYamlLoader)


def parse_opt_yaml_documents(text: str) -> list[dict[str, Any]]:
    """Parse a YAML *document stream* into plain dict documents."""

    documents: list[dict[str, Any]] = []
    for doc in yaml.load_all(text, Loader=OptYamlLoader):
        if doc is None:
            continue
        if not isinstance(doc, dict):
            documents.append({"Kind": None, "value": doc})
            continue
        documents.append(doc)
    return documents
