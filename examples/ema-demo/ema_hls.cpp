// Vitis HLS kernels for the EMA demo. Synthesize with: vitis_hls -f run_hls.tcl
//
// ema_kernel: the naive recurrence. PIPELINE II=1 is requested, but the
// floating-point multiply-add takes several cycles and each iteration reads
// the accumulator the previous iteration wrote, so the schedule cannot
// overlap iterations: the report comes back II=3 (IINotAchieved).
//
// ema_kernel3: the classic fix. Three independent streams (think three
// symbols, round-robin) interleaved through one pipeline. Each stream's
// recurrence now has three cycles between its read and its write, which
// covers the adder latency, and the same loop hits II=1.

extern "C" void ema_kernel(float* out, const float* px, float alpha, int n) {
#pragma HLS INTERFACE m_axi port = out bundle = gmem0
#pragma HLS INTERFACE m_axi port = px bundle = gmem1
    float acc = out[0];
EMA_LOOP:
    for (int i = 1; i < n; ++i) {
#pragma HLS PIPELINE II = 1
        acc = alpha * px[i] + (1.0f - alpha) * acc;
        out[i] = acc;
    }
}

extern "C" void ema_kernel3(float* out, const float* px, float alpha, int n) {
#pragma HLS INTERFACE m_axi port = out bundle = gmem0
#pragma HLS INTERFACE m_axi port = px bundle = gmem1
    float acc[3] = {out[0], out[1], out[2]};
#pragma HLS ARRAY_PARTITION variable = acc complete
EMA_LOOP:
    for (int i = 3; i < n; ++i) {
#pragma HLS PIPELINE II = 1
        int s = i % 3;
        acc[s] = alpha * px[i] + (1.0f - alpha) * acc[s];
        out[i] = acc[s];
    }
}
