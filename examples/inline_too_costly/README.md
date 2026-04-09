# inline_too_costly

Contains **`before/`** and **`after/`** variants of a hot path calling a helper. The **before** helper is intentionally large enough that the inliner may reject it for size/cost; the **after** variant is simplified so inline becomes plausible.

Use `explncc diff` between the two generated `.opt.yaml` files to see remark-level deltas.
