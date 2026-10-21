#!/usr/bin/env python3
"""DSP 設定パスの整合性ガード（2026-10-02 追加）。

事故の経緯:
    `HQ_DSP_YAML` / `CAMILLA_STATE_FILE` が `/tmp/camilladsp/` を指していた。
    `/tmp` は tmpfs のため OS リブートで必ず消え、CamillaDSP は毎回
    "Could not open config file" で起動失敗し、8003 `/health` が
    `dsp: disconnected` になっていた（＝リブートごとに DSP 機能が失われる）。

    パスが Python / shell / systemd テンプレート / env 例の 4 箇所に
    重複していたことが、修正時に一部分だけ直して drift する構造だった。

本テストは以下を保証する:
  1. 既定パスが tmpfs (/tmp, /run, /var/tmp) を参照しない
  2. backend/dsp/paths.py (Python) == scripts/install_systemd_units.sh (shell)
  3. backend/dsp/paths.py == config/systemd/hqmplayer.env.example
  4. テスト/ツール内にハードコードされた旧パスが残っていない

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_paths_consistency -v
"""
import os
import re
import unittest

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ not in os.sys.path:
    os.sys.path.insert(0, _PROJ)

from backend.dsp.paths import (  # noqa: E402
    DEFAULT_DSP_STATE,
    DEFAULT_DSP_YAML,
    DSP_STATE_DIR,
    dsp_state_path,
    dsp_yaml_path,
)

#: tmpfs 上の領域。CamillaDSP の設定/状態を置くには不適。
VOLATILE_PREFIXES = ("/tmp", "/run", "/var/tmp", "/dev/shm")


def _read(rel: str) -> str:
    with open(os.path.join(_PROJ, rel), encoding="utf-8") as f:
        return f.read()


class TestDspPathsConsistency(unittest.TestCase):
    """CamillaDSP 設定パスの単一ソース整合性."""

    def test_defaults_are_not_on_tmpfs(self):
        """既定パスが tmpfs を参照しないこと（リブートで消えない）。"""
        for label, path in (("yaml", DEFAULT_DSP_YAML), ("state", DEFAULT_DSP_STATE)):
            with self.subTest(path=path):
                self.assertFalse(
                    path.startswith(VOLATILE_PREFIXES),
                    f"{label} 既定が揮発領域を指しています: {path}",
                )

    def test_defaults_live_under_state_dir(self):
        """既定パスがすべて DSP_STATE_DIR 配下にあること。"""
        for path in (DEFAULT_DSP_YAML, DEFAULT_DSP_STATE):
            with self.subTest(path=path):
                self.assertTrue(
                    path.startswith(DSP_STATE_DIR + "/"),
                    f"{path} が {DSP_STATE_DIR} 配下ではありません",
                )

    def test_env_unset_resolves_to_defaults(self):
        """環境変数が無ければ既定値が使われること。"""
        saved = {k: os.environ.pop(k, None) for k in ("HQ_DSP_YAML", "CAMILLA_STATE_FILE")}
        try:
            self.assertEqual(dsp_yaml_path(), DEFAULT_DSP_YAML)
            self.assertEqual(dsp_state_path(), DEFAULT_DSP_STATE)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_env_override_is_honoured(self):
        """環境変数による上書きが優先されること。"""
        saved_yaml = os.environ.get("HQ_DSP_YAML")
        os.environ["HQ_DSP_YAML"] = "/tmp/sentinel/dsp.yml"
        try:
            self.assertEqual(dsp_yaml_path(), "/tmp/sentinel/dsp.yml")
        finally:
            if saved_yaml is None:
                os.environ.pop("HQ_DSP_YAML", None)
            else:
                os.environ["HQ_DSP_YAML"] = saved_yaml

    def test_installer_shell_defaults_match_python(self):
        """install_systemd_units.sh の既定値が Python と一致すること。"""
        src = _read("scripts/install_systemd_units.sh")
        m_yaml = re.search(r'CAMILLA_YAML="\$\{CAMILLA_YAML:-(.+?)\}"', src)
        m_state = re.search(r'CAMILLA_STATE="\$\{CAMILLA_STATE:-(.+?)\}"', src)
        self.assertIsNotNone(m_yaml, "CAMILLA_YAML の既定値を検出できません")
        self.assertIsNotNone(m_state, "CAMILLA_STATE の既定値を検出できません")
        self.assertEqual(m_yaml.group(1), DEFAULT_DSP_YAML, "shell と Python の YAML パスが不一致")
        self.assertEqual(m_state.group(1), DEFAULT_DSP_STATE, "shell と Python の state パスが不一致")

    def test_env_example_matches_python(self):
        """hqmplayer.env.example が Python の既定値と一致すること。"""
        src = _read("config/systemd/hqmplayer.env.example")
        # コメント行 (先頭 #) を除外して実効値だけを見る
        effective = {
            m.group(1): m.group(2)
            for m in re.finditer(r'^\s*(?!#)\s*(HQ_DSP_YAML|CAMILLA_STATE_FILE)\s*=\s*(\S+)', src, re.M)
        }
        self.assertIn("HQ_DSP_YAML", effective, "env 例に HQ_DSP_YAML が未設定 (コメントアウト) されています")
        self.assertIn("CAMILLA_STATE_FILE", effective, "env 例に CAMILLA_STATE_FILE が未設定です")
        self.assertEqual(effective["HQ_DSP_YAML"], DEFAULT_DSP_YAML)
        self.assertEqual(effective["CAMILLA_STATE_FILE"], DEFAULT_DSP_STATE)

    def test_no_hardcoded_volatile_path_remains(self):
        """テスト/設定ファイルに旧 tmpfs パスのハードコードが残っていないこと。"""
        offenders = []
        targets = [
            "tests/unit/test_no_live_write.py",
            "tests/unit/test_bluetooth_rate_adjust.py",
            "tests/tools/dsp_probe.py",
            "config/systemd/camilladsp.service.template",
            "config/systemd/hqmplayer.env.example",
            "backend/scripts/switch_audio.sh",
        ]
        for rel in targets:
            for i, line in enumerate(_read(rel).splitlines(), 1):
                # コメント/docstring 内の言及は許容。実効的な代入行だけを違反とみなす。
                stripped = line.strip()
                if stripped.startswith("#") or "VOLATILE" in stripped:
                    continue
                if re.search(r'["\']/tmp/camilladsp/', stripped) and "=" in stripped:
                    offenders.append(f"{rel}:{i}: {stripped}")
        self.assertEqual(offenders, [], "tmpfs パスへのハードコードが残存しています")


if __name__ == "__main__":
    unittest.main()
