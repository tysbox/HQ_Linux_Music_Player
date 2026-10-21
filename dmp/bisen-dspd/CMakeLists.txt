cmake_minimum_required(VERSION 3.16)
project(bisen-dspd CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
set(CMAKE_CXX_FLAGS_RELEASE "-O2")

add_compile_options(-Wall -Wextra)

# ── 本体: ALSA ループバック capture → DSP チェーン → DAC playback ──
add_executable(bisen-dspd
  src/main.cpp
  src/alsa_io.cpp
  src/control.cpp
  src/dsp/TubeModel.cpp
  src/dsp/RestorationEngine.cpp
  src/dsp/TruePeakLimiter.cpp
)
target_include_directories(bisen-dspd PRIVATE src)
target_link_libraries(bisen-dspd asound pthread)

# ── オフライン DSP 検証 (ALSA 不要・ゴールデンサンプル) ──
add_executable(test_dsp_chain
  tests/test_dsp_chain.cpp
  src/dsp/TubeModel.cpp
  src/dsp/RestorationEngine.cpp
  src/dsp/TruePeakLimiter.cpp
)
target_include_directories(test_dsp_chain PRIVATE src)
target_link_libraries(test_dsp_chain pthread)

enable_testing()
add_test(NAME dsp_chain COMMAND test_dsp_chain)
