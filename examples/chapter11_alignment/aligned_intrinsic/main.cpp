#include <immintrin.h>

// Explicit aligned AVX load intrinsic — alignment is visible in source.

float sum_aligned(const float* p, int n) {
  __m256 acc = _mm256_setzero_ps();
  for (int i = 0; i < n; i += 8) {
    __m256 v = _mm256_load_ps(p + i);
    acc = _mm256_add_ps(acc, v);
  }
  alignas(32) float tmp[8];
  _mm256_store_ps(tmp, acc);
  return tmp[0] + tmp[1] + tmp[2] + tmp[3] + tmp[4] + tmp[5] + tmp[6] + tmp[7];
}

int main() {
  alignas(32) float data[32];
  for (int i = 0; i < 32; ++i) {
    data[i] = static_cast<float>(i);
  }
  volatile float sink = sum_aligned(data, 32);
  return static_cast<int>(sink) & 1;
}
