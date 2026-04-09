// Possible aliasing between a and b prevents the vectorizer from proving that
// iterations are independent when both pointers could refer to the same
// underlying object.

void scale_add(double* a, const double* b, int n) {
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
