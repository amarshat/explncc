// Trip count is a small compile-time constant (8). Loop passes can reason about
// full unrolling or aggressive unrolling without runtime profiling.

void bump(volatile int* x) {
  for (int i = 0; i < 8; ++i) {
    *x += i;
  }
}

int main() {
  volatile int v = 0;
  bump(&v);
  return v & 1;
}
