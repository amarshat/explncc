# C/C++ examples for explncc

These programs exist to produce **real** Clang optimization remark YAML (`.opt.yaml`) on your machine. They are intentionally small so readers can map source lines to remark entries.

**Chapter 11:** see `chapter11_alignment/` for alignment-evidence case studies with bundled fixture remarks.

Build everything:

```bash
make examples
```

Outputs:

- `build/examples/<example-name>/<artifact>.opt.yaml`
- `build/examples/<example-name>/<binary>`

See [docs/examples.md](../docs/examples.md) for what each directory teaches.
