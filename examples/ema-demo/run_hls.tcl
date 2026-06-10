# Real synthesis for anyone with Vitis HLS installed:
#   vitis_hls -f run_hls.tcl
# The report lands at ema_hls/solution1/syn/report/csynth.xml; point explncc at it:
#   explncc why ema_hls/solution1/syn/report/csynth.xml --toolchain hls
# Switch set_top to ema_kernel3 for the interleaved (II=1) version.
open_project -reset ema_hls
set_top ema_kernel
add_files ema_hls.cpp
open_solution -reset solution1
set_part xcu250-figd2104-2L-e
create_clock -period 3.33
csynth_design
exit
