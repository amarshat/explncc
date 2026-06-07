// A small per-iteration select. Vectorization is legal, but the SLP cost model
// finds it not profitable ("List vectorization was possible but not beneficial
// with cost C >= Treshold T"). A profitability rejection is not an alignment
// problem. (LLVM really does misspell the threshold key as "Treshold".)

void clamp_floor(float* a, const float* b, int n) {
#pragma clang loop vectorize(enable)
  for (int i = 0; i < n; ++i) {
    a[i] = b[i] > 0.0f ? a[i] : b[i];
  }
}

int main() {
  float a[64];
  float b[64];
  for (int i = 0; i < 64; ++i) {
    a[i] = static_cast<float>(i);
    b[i] = static_cast<float>(i - 32);
  }
  clamp_floor(a, b, 64);
  volatile float sink = a[3];
  return static_cast<int>(sink) & 1;
}
