// A loop-carried memory dependence: a[i] reads a[i-1] written last iteration.
// The vectorizer refuses on legality, not alignment: it cannot prove the
// iterations are independent ("unsafe dependent memory operations ... Backward
// loop carried data dependence"). Modern Clang resolves pure pointer aliasing
// with a runtime check and vectorizes anyway, so the real, reproducible
// "memory-reason miss that is not alignment" is this backward dependence.

void accumulate(float* a, const float* b, int n) {
  for (int i = 1; i < n; ++i) {
    a[i] = a[i - 1] + b[i];
  }
}

int main() {
  float a[256];
  float b[256];
  for (int i = 0; i < 256; ++i) {
    a[i] = static_cast<float>(i);
    b[i] = static_cast<float>(i + 1);
  }
  accumulate(a, b, 256);
  volatile float sink = a[7];
  return static_cast<int>(sink) & 1;
}
