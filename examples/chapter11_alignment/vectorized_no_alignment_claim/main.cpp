// Independent streams: vectorization succeeds; remark usually does not mention alignment.

void scale_add(float* __restrict out, const float* __restrict in, int n) {
  for (int i = 0; i < n; ++i) {
    out[i] += 0.5f * in[i];
  }
}

int main() {
  float a[256];
  float b[256];
  for (int i = 0; i < 256; ++i) {
    a[i] = static_cast<float>(i);
    b[i] = static_cast<float>(i + 1);
  }
  scale_add(a, b, 256);
  volatile float sink = a[7];
  return static_cast<int>(sink) & 1;
}
