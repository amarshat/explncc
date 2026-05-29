# Local Classifier Labels

explncc's offline classifier maps each normalized compiler remark to exactly
one local label. Labels are deterministic, conservative heuristics layered on
top of authoritative compiler evidence — they describe *what the compiler
reported and why it likely matters*, not ground truth.

When evidence is weak, the classifier falls back to `insufficient_evidence` or
a `generic_*` label rather than overclaiming. Alignment labels only fire when
the command focus is alignment (e.g. `--focus alignment`). Target-specific
labels (wasm/neon/avx) require real target evidence (triple/cpu/march).

There are 20 labels.

## `vectorize_aliasing`

**Vectorization blocked by possible aliasing** (default severity: `medium`)

The compiler reported a loop-vectorization miss tied to memory independence: it could not prove that memory accesses are safe to reorder or widen.

- **Matching hints:** `cannot prove memory independence`, `may alias`, `memory dependence`, `aliasing`
- **Recommended actions:**
    - Inspect whether input/output buffers can overlap
    - Consider restrict/noalias contracts if semantically valid
    - Check call sites for overlapping ranges
- **Explanation template:**

    > The compiler attempted loop vectorization but could not prove memory independence. This usually means it could not prove that memory accesses in the loop are safe to reorder or widen without changing behavior if pointers happen to overlap.

## `vectorize_cost_rejected`

**Vectorization rejected by the cost model** (default severity: `low`)

The compiler decided vectorizing this loop was not profitable based on its cost model, not because it was unsafe.

- **Matching hints:** `cost`, `not beneficial`, `not profitable`, `threshold`
- **Recommended actions:**
    - Review scalar vs vector cost estimates in the remark
    - Consider loop structure, trip count, and body size
    - Avoid forcing vectorization unless benchmarks justify it
- **Explanation template:**

    > The compiler analyzed this loop and concluded that vectorizing it was not beneficial under its cost model. This is a profitability decision, not a correctness blocker: the loop could be vectorized but the compiler estimated no net win.

## `vectorize_call_in_loop`

**Vectorization blocked by a call in the loop** (default severity: `medium`)

A function call inside the loop body prevented vectorization because the compiler could not vectorize across the call.

- **Matching hints:** `call in loop`, `function call`, `cannot vectorize`
- **Recommended actions:**
    - Check whether the called function can be inlined
    - Consider hoisting or replacing the call with a vectorizable form
    - Look for vectorized math library variants if the call is a libm function
- **Explanation template:**

    > The compiler could not vectorize this loop because it contains a function call it cannot vectorize across. Calls usually act as barriers unless the callee can be inlined or has a vector variant.

## `vectorize_unknown_trip_count`

**Vectorization limited by unknown trip count** (default severity: `low`)

The compiler could not determine the loop trip count, which limited or blocked vectorization.

- **Matching hints:** `trip count`, `loop count`, `backedge taken`
- **Recommended actions:**
    - Make loop bounds compile-time constant where possible
    - Check whether runtime checks are being added or rejected
    - Inspect whether the loop count is derived from opaque inputs
- **Explanation template:**

    > The compiler could not establish the loop's trip count. Without a known or bounded iteration count it is harder to prove vectorization is safe and profitable, so the loop stayed scalar or required runtime checks.

## `vectorize_success`

**Loop vectorization succeeded** (default severity: `low`)

The compiler successfully vectorized this loop.

- **Matching hints:** `vectorized`, `vectorization width`
- **Recommended actions:**
    - Validate with benchmarks if performance is a concern
    - Inspect assembly to confirm the expected SIMD width
- **Explanation template:**

    > The compiler successfully vectorized this loop and emitted SIMD code. This is a positive outcome; confirm with benchmarks and assembly if performance regresses elsewhere.

## `inline_no_definition`

**Inlining blocked: callee definition unavailable** (default severity: `medium`)

The inliner could not inline a callee because its definition was not visible in this translation unit.

- **Matching hints:** `NoDefinition`, `definition is unavailable`, `definition unavailable`, `no definition`
- **Recommended actions:**
    - Place small hot definitions in headers, or compile sources together
    - Enable link-time optimization (LTO) to expose cross-TU definitions
    - Confirm the callee is not only declared but defined where it is used
- **Explanation template:**

    > The inliner could not merge the callee into the caller because the callee's body is not available in this translation unit. Inlining requires the optimizer to see the callee IR.

## `inline_too_costly`

**Inlining rejected as too costly** (default severity: `low`)

The inliner evaluated the callee against a cost threshold and rejected the expansion to limit code growth.

- **Matching hints:** `too costly`, `cost`, `threshold`
- **Recommended actions:**
    - Reduce callee size or split cold paths into outlined helpers
    - Use always_inline only when you accept binary growth
    - Review the reported cost vs threshold before forcing inlining
- **Explanation template:**

    > The inliner compared the callee's inline cost against a threshold and decided not to inline it. When cost exceeds the threshold the inliner declines to expand the call to avoid excessive code growth.

## `inline_success`

**Inlining succeeded** (default severity: `low`)

The inliner successfully inlined a callee into the caller.

- **Matching hints:** `inlined`, `Inlined`
- **Recommended actions:**
    - No action required; verify code size if many callees are inlined
- **Explanation template:**

    > The inliner successfully inlined the callee into the caller. This can improve performance by removing call overhead and enabling further optimization across the inlined body.

## `unroll_unknown_trip_count`

**Unrolling limited by unknown trip count** (default severity: `low`)

The compiler could not fully unroll the loop because the trip count was unknown or not a compile-time constant.

- **Matching hints:** `trip count`, `unknown trip`, `runtime trip count`
- **Recommended actions:**
    - Make loop bounds compile-time constant where possible
    - Consider splitting kernels with fixed iteration counts
    - Measure before adding unroll pragmas
- **Explanation template:**

    > The compiler did not fully unroll this loop because the trip count is unknown. Full unrolling typically requires a fixed, compile-time iteration count.

## `unroll_cost_rejected`

**Unrolling rejected by the cost model** (default severity: `low`)

The compiler decided unrolling this loop was not profitable or would grow code beyond a threshold.

- **Matching hints:** `cost`, `not beneficial`, `threshold`, `code size`
- **Recommended actions:**
    - Review whether code-size growth is acceptable
    - Consider partial unrolling or leaving the decision to the compiler
    - Measure before forcing unroll counts
- **Explanation template:**

    > The compiler analyzed this loop and decided unrolling was not profitable under its cost model or would exceed a size threshold. This is a profitability decision, not a correctness blocker.

## `alignment_explicit`

**Alignment explicitly referenced by the remark** (default severity: `medium`)

The remark text explicitly references alignment vocabulary (aligned/unaligned loads, alignment metadata, alignment intrinsics).

- **Matching hints:** `aligned`, `unaligned`, `misaligned`, `alignment`
- **Recommended actions:**
    - Inspect allocation guarantees and pointer alignment assumptions
    - Check IR alignment metadata on the relevant loads/stores
    - Compare assembly load/store forms (e.g. movaps vs movups)
- **Explanation template:**

    > The remark explicitly mentions alignment. The compiler's wording points to alignment of memory accesses; confirm allocation and pointer alignment guarantees before changing code.

## `alignment_plausible_not_proven`

**Alignment plausibly involved but not proven** (default severity: `low`)

Vectorization/SIMD is involved but the remark does not explicitly establish that alignment is the cause. Reported only when the command focus is alignment.

- **Matching hints:** `vectorized`, `simd`, `interleave`
- **Recommended actions:**
    - Inspect allocation guarantees and pointer arithmetic
    - Check IR alignment metadata before attributing a miss to alignment
    - Do not treat vectorization factor alone as proof of misalignment
- **Explanation template:**

    > SIMD or vectorization is involved here, but the remark does not prove that alignment is the issue. Treat alignment as a hypothesis to verify, not a conclusion.

## `target_specific_drift`

**Target-specific optimization difference** (default severity: `low`)

The remark suggests behavior that may differ across targets/ISAs. Reported conservatively; details are not invented.

- **Matching hints:** `target`, `triple`, `cpu`
- **Recommended actions:**
    - Confirm the active target triple and CPU before drawing conclusions
    - Compare the same source across the targets you ship
    - Avoid assuming a specific ISA without target evidence
- **Explanation template:**

    > This remark may reflect target-specific behavior. Optimization decisions can differ across instruction sets; verify the active target before attributing the difference to a specific ISA.

## `wasm_simd_limitation`

**WebAssembly SIMD limitation** (default severity: `low`)

The remark indicates a WebAssembly SIMD limitation. Reported only with explicit wasm/SIMD target evidence.

- **Matching hints:** `wasm`, `webassembly`, `wasm-simd`
- **Recommended actions:**
    - Confirm the wasm SIMD feature flags enabled at build time
    - Check whether the operation has a wasm SIMD equivalent
    - Compare against a native build to isolate the limitation
- **Explanation template:**

    > The remark points to a WebAssembly SIMD limitation. WebAssembly SIMD supports a narrower set of operations than native ISAs; some patterns cannot be expressed and stay scalar.

## `arm_neon_difference`

**ARM NEON-specific difference** (default severity: `low`)

The remark indicates an ARM/NEON-specific behavior. Reported only with explicit ARM/NEON target evidence.

- **Matching hints:** `neon`, `aarch64`, `arm`
- **Recommended actions:**
    - Confirm the ARM target and NEON/SVE feature flags
    - Compare against another ISA to isolate the difference
    - Check for NEON-specific intrinsics or lowering
- **Explanation template:**

    > The remark points to ARM NEON-specific behavior. NEON has different vector widths and operation support than x86 SIMD; verify the target before generalizing.

## `x86_avx_difference`

**x86 AVX-specific difference** (default severity: `low`)

The remark indicates an x86 AVX/SSE-specific behavior. Reported only with explicit x86 target evidence.

- **Matching hints:** `avx`, `sse`, `x86`
- **Recommended actions:**
    - Confirm the x86 target and AVX/SSE feature flags
    - Compare against another ISA to isolate the difference
    - Check whether wider AVX registers change the cost model outcome
- **Explanation template:**

    > The remark points to x86 AVX/SSE-specific behavior. Available vector width depends on enabled features (SSE/AVX/AVX-512); verify the target before generalizing.

## `insufficient_evidence`

**Insufficient evidence to classify** (default severity: `low`)

The remark matched a relevant area but the available evidence is too weak to assign a specific cause. The conservative fallback.

- **Recommended actions:**
    - Attach a source snippet around the debug location
    - Generate IR and assembly snippets for the function
    - Re-run classification after adding grounded compiler artifacts
- **Explanation template:**

    > There is not enough grounded evidence in this remark to assign a specific cause. Add source, IR, or assembly context and re-run before drawing conclusions.

## `generic_missed_optimization`

**Generic missed optimization** (default severity: `low`)

A missed optimization that does not match a more specific local label.

- **Recommended actions:**
    - Read the full remark message for the specific guard
    - Compare against a variant where the optimization applies
- **Explanation template:**

    > The compiler reported a missed optimization that does not match a more specific local category. Inspect the full remark message to understand the guard the compiler hit.

## `generic_analysis`

**Generic analysis remark** (default severity: `low`)

An analysis remark that reports compiler observations rather than a missed or applied optimization.

- **Recommended actions:**
    - Use as context; analysis remarks rarely require direct action
- **Explanation template:**

    > This is an analysis remark: the compiler is reporting an observation (such as a measurement) rather than a missed or applied optimization. It is usually contextual rather than directly actionable.

## `generic_passed`

**Generic applied optimization** (default severity: `low`)

An applied optimization that does not match a more specific local label.

- **Recommended actions:**
    - No action required; informational
- **Explanation template:**

    > The compiler applied an optimization here. This is informational and does not match a more specific local category.
