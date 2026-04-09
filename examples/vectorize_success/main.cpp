// Independent streams: Clang supports __restrict on pointers in C++ mode as a
// non-standard extension; it communicates the absence of pointer aliasing the
// vectorizer needs for SIMD.

void scale_add(double* __restrict a, const double* __restrict b, int n) {
  for (int i = 0; i < n; ++i) {
    a[i] += 0.5 * b[i];
  }
}

int main() {
  double a[256];
  double b[256];
  for (int i = 0; i < 256; ++i) {
    a[i] = static_cast<double>(i);
    b[i] = static_cast<double>(i + 1);
  }
  scale_add(a, b, 256);
  volatile double sink = a[7];
  return static_cast<int>(sink) & 1;
}
