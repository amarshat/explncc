// Very small trip count: vectorization often rejected on cost / profitability grounds.

void bump(float* a, int n) {
  for (int i = 0; i < n; ++i) {
    a[i] += 1.0f;
  }
}

int main() {
  float xs[4] = {0.0f, 1.0f, 2.0f, 3.0f};
  bump(xs, 2);
  volatile float sink = xs[1];
  return static_cast<int>(sink) & 1;
}
