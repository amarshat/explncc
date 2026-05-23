// Base pointer offset: layout may affect alignment, but the remark alone does not prove misalignment.

float accumulate_offset(const float* input, int n) {
  const float* p = input + 1;
  float sum = 0.0f;
  for (int i = 0; i < n; ++i) {
    sum += p[i];
  }
  return sum;
}

int main() {
  alignas(32) float data[64];
  for (int i = 0; i < 64; ++i) {
    data[i] = static_cast<float>(i);
  }
  volatile float sink = accumulate_offset(data, 60);
  return static_cast<int>(sink) & 1;
}
