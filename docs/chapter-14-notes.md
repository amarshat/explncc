# Notes for Chapter 14 (visualizing IR with explanations — trees, graphs, commentary)

Chapter outline: *Visualizing IR with Explanations: From Trees to Vectors* — pairing compiler artifacts with diagrams and LLM commentary: opt-viewer-style workflows, Mermaid (and similar) for **annotated** graphs, and how to merge **static** IR or remark views with **dynamic** model text. Advanced (~10 pages). explncc stays on **YAML remark data**; full LLVM IR graphs belong to **clang**, **opt**, **LLVM-** tools, or viewers such as **opt-viewer** — the chapter shows how to **join** those worlds.

## What explncc adds for this chapter

| Heading | Reader learns to DO | explncc support |
|---------|---------------------|-----------------|
| **Tools to visualize LLVM IR and passes** | Use LLVM/clang outputs (bitcode, `-print-after-all`, opt-viewer) alongside remark files. | No IR parser in-repo: document **join on (file, line)** or TU name; `viz --format json` includes `join_hints` for downstream scripts. |
| **Rendering DAGs and trees with annotations** | Build diagrams from structured data; label nodes with counts and locations. | `explncc viz` → **Mermaid** `flowchart` / subgraphs: `pass-summary`, `missed-top`, `pass-remark` (synthetic pass→remark edges for **triage**, not LLVM pass pipeline order). |
| **Merging IR state with AI output** | Keep compiler facts and model prose in separate layers; merge in HTML or JSON consumers. | `viz --format html` + `--explain-file` or `--explain-backend …` embeds escaped explanation beside the diagram; `json` adds an `explanation` field when present. |
| **Inline explanations and tooltips** | Design UIs where hover/expand shows grounded text. | JSON bundle carries `mermaid` + `explanation` + counts for React/D3/wiki macros; tooltips are **your** renderer (explncc does not ship a GUI). |
| **Building visual debugging interfaces** | Prototype PR dashboards or local HTML pages quickly. | `viz --format html` loads Mermaid from jsDelivr (offline/air-gapped: vendor the script locally and swap the template in your fork). |

## Trust and limitations (say this in prose)

- **Diagram semantics:** `pass-remark` edges are **derived from remark statistics**, not the LLVM pass manager DAG. Say so in figure captions to avoid misleading experts.
- **IR is out of scope** for explncc core: visualize IR with **opt-viewer**, **LLVM GraphViewer**, or custom LLVM passes; use explncc for **remark-centric** overlays and AI captions keyed to source locations.
- **Mermaid in CI:** rendering is browser- or Node-based; in CI, usually emit `.mmd` or `json` and upload as an artifact rather than screenshotting headless browsers (unless you already have that stack).
- **XSS / HTML:** generated labels sanitize `<>` and `&` for labels; HTML wrapper strips `</script`-style breaks — still treat merged `--explain-file` as **trusted** input if you allow untrusted uploads.

## Example commands (copy into the book)

```bash
# Mermaid source for top passes (paste into GitHub, Notion, or a .mmd file)
python -m explncc viz build/examples/ --style pass-summary --format mermaid --top 12 -o remarks-by-pass.mmd

# Top missed remarks as a horizontal subgraph (good for slides)
python -m explncc viz build/app.opt.yaml --style missed-top --format mermaid --top 15

# Synthetic pass → remark_name edges (triage “where is the noise?”)
python -m explncc viz build/app.opt.yaml --style pass-remark --format mermaid --top 20

# Standalone HTML: diagram + rule-based explanation block
python -m explncc viz build/examples/inline_miss_no_definition/main.opt.yaml \
  --style missed-top --format html --explain-backend rule -o viz.html

# JSON for a custom web UI or opt-viewer overlay script
python -m explncc viz build/app.opt.yaml --style pass-summary --format json -o viz-bundle.json
```

## External tools (teach alongside explncc)

- **opt-viewer** — HTML reports from YAML optimization records (different pipeline from explncc, overlapping goals).
- **clang -emit-llvm -S**, **llvm-dis**, **opt -dot-cfg** — IR and CFG artifacts to align with remarks on `DebugLoc` / line tables.
- **Mermaid.js** — what `viz --format html` loads by default for quick prototypes.

## Repository / module map

- `src/explncc/viz.py` — Mermaid builders, HTML shell, JSON bundle, parsers for `--style` / `--format`
- `src/explncc/cli.py` — `viz` subcommand (`--explain-file`, `--explain-backend`, filters)

## Skills ↔ chapter outcomes

1. **Choose the right artifact** — IR/CFG vs `.opt.yaml` vs merged HTML for an audience.
2. **Generate diagram sources from remarks** — Mermaid and JSON from the same normalized records as `summary` / `report`.
3. **Layer AI commentary** — file-based or backend-generated text next to diagrams without conflating with compiler ground truth.
4. **Integrate with LLVM ecosystem** — name opt-viewer, Graphviz/dot, and join strategies explicitly.
5. **Ship a minimal visual aid** — one HTML file or CI artifact for a regression or tutorial.
