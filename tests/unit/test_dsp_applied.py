#!/usr/bin/env python3
"""DSP applied フィールドテスト（Stage 1-5: 重複・死コード整理）

/api/apply のレスポンスに applied フィールドが含まれることを検証。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_applied -v
"""
import unittest
from unittest.mock import patch, MagicMock
import sys

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.apply_logic import apply_audio as apply_audio_impl
from backend.main import AudioConfig


class TestDspApplied(unittest.TestCase):
    """apply_audio のレスポンスに applied フィールドがあることを確認."""

    def test_apply_returns_applied_true_on_success(self):
        """成功時は applied: true が返る."""
        config = AudioConfig(
            mode="dsp",
            device="plughw:1,0",
            volume=-12.0,
            music_type="none",
            eq_output="none",
            crossfeed="none",
            crossfeed_intensity=5,
            hum_noise="none",
            reverb="none",
            reverb_intensity=5,
        )
        
        # モック関数
        def mock_generate_yaml(cfg):
            return "/tmp/test_dsp.yml"
        
        def mock_normalize(cfg, requested_mode=None):
            return cfg
        
        def mock_ensure_prereqs(cfg):
            pass
        
        def mock_requires_restart(cfg, last):
            return False  # 再起動不要
        
        def mock_load_last():
            return {"volume": -12.0}
        
        def mock_save_last(cfg_dict):
            pass
        
        with patch('backend.dsp.apply_logic.CamillaClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.volume.main_volume.return_value = -12.0
            mock_client_class.return_value = mock_client
            
            result = apply_audio_impl(
                config,
                mock_generate_yaml,
                mock_normalize,
                mock_ensure_prereqs,
                mock_requires_restart,
                mock_load_last,
                mock_save_last,
            )
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["restarted"], False)
        self.assertEqual(result["applied"], True)

    def test_apply_returns_applied_false_on_error(self):
        """エラー時は applied: false が返る."""
        config = AudioConfig(
            mode="dsp",
            device="plughw:1,0",
            volume=-12.0,
            music_type="none",
            eq_output="none",
            crossfeed="none",
            crossfeed_intensity=5,
            hum_noise="none",
            reverb="none",
            reverb_intensity=5,
        )
        
        def mock_generate_yaml(cfg):
            raise RuntimeError("YAML generation failed")
        
        def mock_normalize(cfg, requested_mode=None):
            return cfg
        
        def mock_ensure_prereqs(cfg):
            pass
        
        def mock_requires_restart(cfg, last):
            return True
        
        def mock_load_last():
            return {"volume": -12.0}
        
        def mock_save_last(cfg_dict):
            pass
        
        result = apply_audio_impl(
            config,
            mock_generate_yaml,
            mock_normalize,
            mock_ensure_prereqs,
            mock_requires_restart,
            mock_load_last,
            mock_save_last,
        )
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["applied"], False)
        self.assertIn("message", result)

    def test_apply_returns_applied_true_when_restarted(self):
        """再起動が必要で成功した場合も applied: true."""
        config = AudioConfig(
            mode="dsp",
            device="plughw:1,0",
            volume=-12.0,
            music_type="jazz",  # 設定変更で再起動必要
            eq_output="studio-monitors",
            crossfeed="none",
            crossfeed_intensity=5,
            hum_noise="none",
            reverb="none",
            reverb_intensity=5,
        )
        
        def mock_generate_yaml(cfg):
            return "/tmp/test_dsp.yml"
        
        def mock_normalize(cfg, requested_mode=None):
            return cfg
        
        def mock_ensure_prereqs(cfg):
            pass
        
        def mock_requires_restart(cfg, last):
            return True  # 再起動必要
        
        def mock_load_last():
            return {"volume": -12.0, "music_type": "none", "eq_output": "none"}
        
        def mock_save_last(cfg_dict):
            pass
        
        with patch('backend.dsp.apply_logic.CamillaClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.volume.main_volume.return_value = -12.0
            mock_client_class.return_value = mock_client
            
            with patch('backend.dsp.apply_logic.subprocess.Popen') as mock_popen:
                result = apply_audio_impl(
                    config,
                    mock_generate_yaml,
                    mock_normalize,
                    mock_ensure_prereqs,
                    mock_requires_restart,
                    mock_load_last,
                    mock_save_last,
                )
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["restarted"], True)
        self.assertEqual(result["applied"], True)


if __name__ == "__main__":
    unittest.main()
