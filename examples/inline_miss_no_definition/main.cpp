// This TU calls a function whose definition lives elsewhere. The inliner cannot
// legally inline across a missing body, so remarks often show a missed inline
// opportunity for the call site below.

extern int callee(int x);

int main() {
  return callee(42);
}
