// Definition compiled separately so main.cpp's TU does not contain the callee
// body. Optimization remarks for main.cpp are emitted when it is compiled
// alone with -c.

int callee(int x) { return x + 1; }
