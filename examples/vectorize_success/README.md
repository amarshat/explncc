# vectorize_success

A loop with **independent** memory accesses (e.g. `__restrict` in C++ via compiler extension, or separated buffers) so the vectorizer has a clear story at high optimization.

Compare against `vectorize_aliasing_fail`.
