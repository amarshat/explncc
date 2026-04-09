// "Before" variant: a hot path calls a helper that is intentionally large. The
// inliner may reject it based on cost/size heuristics even when the call site
// is hot.

#include <cstdint>

static int big_helper(int x) {
  int acc = x;
  for (int i = 0; i < 64; ++i) {
    acc = (acc * 1103515245 + 12345) & 0x7fffffff;
  }
  return acc;
}

int hot_caller(int seed) {
  int v = seed;
  for (int i = 0; i < 256; ++i) {
    v += big_helper(v + i);
  }
  return v;
}

int main() {
  volatile int sink = hot_caller(7);
  return sink & 1;
}
