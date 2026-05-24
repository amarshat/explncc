# Extending explncc

Each extension must preserve trust constraints: deterministic core first, no invented compiler fields, backends never read raw YAML.

## Add a new backend

| Step | Location |
|------|----------|
| Implement chat/API call | `src/explncc/explain/backends.py` |
| Return `ExplanationResult` | `src/explncc/explain/contracts.py` |
| Wire CLI | `explncc explain --backend …` |
| Tests | `tests/test_backends.py`, `tests/test_chapter13.py` (mock HTTP) |

Constraints: consume normalized JSON or `EvidencePack`; fallback to rule on failure unless `--strict-explain`.

## Add a new report format

| Step | Location |
|------|----------|
| Builder function | `src/explncc/ci_report.py` or new module |
| Register in `render_report()` | `ci_report.py` |
| CLI | `explncc report --format …` |
| Tests | `tests/test_ci_report.py` |

Constraints: escape HTML; label model sections; do not mutate policy fields from model output.

## Add a normalized field

| Step | Location |
|------|----------|
| Schema | `models.py` |
| Extraction | `normalizer.py` |
| Identity hash | `record_identity.py` if part of canonical record |
| Export | `exporters.py` (via `model_dump`) |
| Tests | `tests/test_normalizer.py`, `tests/test_chapter13.py` |

Constraints: missing stays `null`; preserve `args_raw`.

## Add a new check / policy threshold

| Step | Location |
|------|----------|
| Counter logic | `checks.py` → `build_policy_result()` |
| CLI flags | `cli.py` (`report`, `check`) |
| Tests | `tests/test_checks.py` |

Constraints: deterministic only; never depend on model output.

## Add a new evidence pack type

| Step | Location |
|------|----------|
| Pack builder | `evidence.py` (`pack_type`) |
| Output | `evidence_output.py` |
| CLI | `explncc evidence` or domain command |
| Tests | `tests/test_evidence.py` |

Constraints: populate `missing_context`; compute `evidence_hash` deterministically.

## Add a prompt template

| Step | Location |
|------|----------|
| Template body | `prompt_templates.py` or registry |
| Metadata | `prompt_registry.py` (`PromptTemplateSpec`) |
| Tests | `tests/test_prompt_templates.py`, hash stability in `test_chapter13.py` |

Constraints: declare `template_version`; include grounding constraints.

## Add a toolchain adapter

| Step | Location |
|------|----------|
| Interface | `toolchains/base.py` |
| Implementation | `toolchains/your_toolchain.py` |
| Register | `get_adapter()` in adapter module |
| Tests | adapter unit tests + CLI smoke |

Constraints: do not claim support until parser exists; default remains `clang`.
