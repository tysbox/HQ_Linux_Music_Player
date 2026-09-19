#!/usr/bin/env python3
"""非破壊メタテスト（Stage 0-5: 非破壊テスト基盤）

生成関数を明示的 out_path で呼んでも /tmp/camilladsp/active_dsp.yml が書き換えられないことを検証する。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_no_live_write -v
"""
import hashlib
import os
import sys
import tempfile
import unittest

# プロジェクトルートをパスに追加
_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.yaml_generator import generate_camilladsp_yaml  # noqa: E402
from backend.main import AudioConfig  # noqa: E402


LIVE_CONFIG_PATH = "/tmp/camilladsp/active_dsp.yml"


def _md5_file(path: str) -> str | None:
    """ファイルの md5 を返す。存在しない場合は None."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except FileNotFoundError:
        return None


class TestNoLiveWrite(unittest.TestCase):
    """生成関数がライブ設定を書き換えないことを検証."""

    def test_generate_with_explicit_outpath_does_not_write_live_config(self):
        """generate_camilladsp_yaml() を明示的 out_path で呼んでも live config が変わらない."""
        # ライブ設定の md5 を記録
        before_md5 = _md5_file(LIVE_CONFIG_PATH)
        self.assertIsNotNone(before_md5, f"Live config not found: {LIVE_CONFIG_PATH}")

        # テスト用設定で YAML 生成（デフォルトパスを使わない）
        config_dict = {
            "mode": "dsp",
            "device": "plughw:1,0",
            "volume": -12.0,
            "music_type": "classical",
            "eq_output": "studio-monitors",
            "crossfeed": "standard",
            "crossfeed_intensity": 50,
            "hum_noise": "60hz",
            "reverb": "hall",
            "reverb_intensity": 35,
        }
        cfg = AudioConfig(**config_dict)
        
        # 一時ファイルに出力
        with tempfile.NamedTemporaryFile(mode="w", suffix="_dsp.yml", delete=False) as f:
            tmp_path = f.name
        try:
            generate_camilladsp_yaml(cfg, out_path=tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        # ライブ設定の md5 が変わっていないことを確認
        after_md5 = _md5_file(LIVE_CONFIG_PATH)
        self.assertEqual(after_md5, before_md5,
            f"Live config was modified! before={before_md5}, after={after_md5}")

    def test_generate_multiple_times_with_explicit_outpath(self):
        """複数回生成しても live config が変わらない."""
        before_md5 = _md5_file(LIVE_CONFIG_PATH)
        self.assertIsNotNone(before_md5)

        config_dict = {
            "mode": "dsp",
            "device": "plughw:1,0",
            "volume": -12.0,
            "music_type": "none",
            "eq_output": "none",
            "crossfeed": "none",
            "crossfeed_intensity": 5,
            "hum_noise": "none",
            "reverb": "none",
            "reverb_intensity": 5,
        }
        cfg = AudioConfig(**config_dict)
        
        # 3回生成
        for _ in range(3):
            with tempfile.NamedTemporaryFile(mode="w", suffix="_dsp.yml", delete=False) as f:
                tmp_path = f.name
            try:
                generate_camilladsp_yaml(cfg, out_path=tmp_path)
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        after_md5 = _md5_file(LIVE_CONFIG_PATH)
        self.assertEqual(after_md5, before_md5,
            f"Live config was modified after multiple generations! before={before_md5}, after={after_md5}")


if __name__ == "__main__":
    unittest.main()
