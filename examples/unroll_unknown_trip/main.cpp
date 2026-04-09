// Trip count comes from a parameter loaded at runtime. Without profile data the
// compiler must treat the bound as unknown, which changes unrolling decisions.

void bump(volatile int* x, int n) {
  for (int i = 0; i < n; ++i) {
    *x += i;
  }
}

int main() {
  volatile int v = 0;
  int n = 16;
  bump(&v, n);
  return v & 1;
}
