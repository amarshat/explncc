# inline_miss_no_definition

Demonstrates a **missed inline** when the callee’s definition is not available in this translation unit (declaration-only use). The compiler cannot inline without the body.

After `make examples`, inspect `build/examples/inline_miss_no_definition/*.opt.yaml` with `explncc summary` and `explncc explain`.
