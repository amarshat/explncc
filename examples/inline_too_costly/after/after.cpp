// "After" variant: same control structure, but the helper is tiny so the
// inliner has room to accept the callsite.

#include <cstdint>

static int tiny_helper(int x) { return (x * 31) ^ (x >> 3); }

int hot_caller(int seed) {
  int v = seed;
  for (int i = 0; i < 256; ++i) {
    v += tiny_helper(v + i);
  }
  return v;
}

int main() {
  volatile int sink = hot_caller(7);
  return sink & 1;
}
