# vectorize_aliasing_fail

A loop where stores and loads may alias through pointers. **Loop-vectorize** often skips SIMD when independence cannot be proven.

Pair with `vectorize_success` to contrast remark patterns.
