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


def _kind_from_tag(tag: str) -> str:
    """Map a YAML tag like ``!AnalysisFPCommute`` to a normalized kind.

    LLVM emits more than three tags: alongside ``!Missed`` / ``!Passed`` /
    ``!Analysis`` it produces analysis variants such as ``!AnalysisFPCommute``
    and ``!AnalysisAliasing``. Anything in that family is treated as analysis;
    any other custom tag degrades to ``unknown`` rather than crashing the parse.
    """

    lowered = tag.lstrip("!").lower()
    if lowered.startswith("missed"):
        return "missed"
    if lowered.startswith("passed"):
        return "passed"
    if lowered.startswith("analysis"):
        return "analysis"
    return "unknown"


class OptYamlLoader(yaml.SafeLoader):
    """YAML loader that preserves ``!Missed`` / ``!Passed`` / ``!Analysis`` tags.

    Also handles analysis variants (``!AnalysisFPCommute``, ``!AnalysisAliasing``,
    ...) and degrades any other ``!``-prefixed tag to kind ``unknown`` instead of
    raising, so a newer LLVM emitting an unfamiliar remark tag never breaks a run.
    """


def _register_tags(loader: type[OptYamlLoader]) -> None:
    def register(tag: str, kind: str) -> None:
        def ctor(loader: yaml.SafeLoader, node: yaml.Node) -> dict[str, Any]:
            return _mapping_with_kind(loader, node, kind)

        loader.add_constructor(tag, ctor)

    register("!Missed", "missed")
    register("!Passed", "passed")
    register("!Analysis", "analysis")

    def multi_ctor(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> dict[str, Any]:
        return _mapping_with_kind(loader, node, _kind_from_tag(tag_suffix))

    # Catch every other ``!...`` tag (e.g. !AnalysisFPCommute, !AnalysisAliasing).
    loader.add_multi_constructor("!", multi_ctor)  # type: ignore[no-untyped-call]


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
