# C/C++ examples for explncc

These programs exist to produce **real** Clang optimization remark YAML (`.opt.yaml`) on your machine. They are intentionally small so readers can map source lines to remark entries.

Build everything:

```bash
make examples
```

Outputs:

- `build/examples/<example-name>/<artifact>.opt.yaml`
- `build/examples/<example-name>/<binary>`

See [docs/examples.md](../docs/examples.md) for what each directory teaches.
