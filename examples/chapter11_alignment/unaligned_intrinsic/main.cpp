#include <immintrin.h>

// Intentional unaligned AVX load — not necessarily a bug; documents unaligned access choice.

float sum_unaligned(const float* p, int n) {
  __m256 acc = _mm256_setzero_ps();
  for (int i = 0; i < n; i += 8) {
    __m256 v = _mm256_loadu_ps(p + i);
    acc = _mm256_add_ps(acc, v);
  }
  float tmp[8];
  _mm256_storeu_ps(tmp, acc);
  return tmp[0] + tmp[1] + tmp[2] + tmp[3] + tmp[4] + tmp[5] + tmp[6] + tmp[7];
}

int main() {
  float data[33];  // deliberately not 32-byte aligned end
  for (int i = 0; i < 33; ++i) {
    data[i] = static_cast<float>(i);
  }
  volatile float sink = sum_unaligned(data + 1, 32);
  return static_cast<int>(sink) & 1;
}
