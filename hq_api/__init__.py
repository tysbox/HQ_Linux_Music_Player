"""HQ Linux Music Player — 統合バックエンド (Phase 3a スケルトン).

DSP (port 8000) と DMP (port 8001) を 1 プロセスに統合する。
当面は port 8002 で並行稼働し、旧 backend は生かしたまま検証する。
"""
__version__ = "0.1.0-phase3a"
