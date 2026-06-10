// Two loops every trading system has. One vectorizes. One never will.
// Compile:  clang++ -O3 -std=c++17 -fsave-optimization-record -c ema.cpp
// Then ask: explncc why ema.cpp:14

// Mid-price from bid/ask: every lane independent. SIMD-friendly.
void mid_price(float* mid, const float* bid, const float* ask, int n) {
    for (int i = 0; i < n; ++i)
        mid[i] = 0.5f * (bid[i] + ask[i]);
}

// Exponential moving average: every step reads the previous result.
void ema(float* out, const float* px, float alpha, int n) {
    for (int i = 1; i < n; ++i)
        out[i] = alpha * px[i] + (1.0f - alpha) * out[i - 1];
}
