#include <cstdio>
extern float helper(float x);   // no definition in this TU -> inline NoDefinition

float dot(const float* a, const float* b, int n) {
    float s = 0.f;
    for (int i = 0; i < n; ++i) s += a[i] * b[i];
    return s;
}

void scan(float* a, const float* b, int n) {
    for (int i = 1; i < n; ++i) a[i] = a[i-1] + b[i];
}

void saxpy(float* y, const float* x, float k, int n) {
    for (int i = 0; i < n; ++i) y[i] += k * x[i];
}

float use_helper(float v) {
    return helper(v) * 2.0f;
}
