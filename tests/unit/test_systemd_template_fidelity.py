#!/usr/bin/env python3
"""systemd テンプレートの退行ガード（2026-10-02 追加）。

事故の経緯:
    `config/systemd/hq-api.service.template` に `Conflicts=` （旧 DSP/DMP サービス
    との同時起動防止）が反映されておらず、`install_systemd_units.sh --apply` が
    実機 unit を上書きするとこの安全指定が消失していた。
    実機 unit には 69498d4e で入っていたため、**テンプレートだけを信じた再適用**
    で安全指定が黙って失われる状態だった。

    同様に CamillaDSP の YAML パスも template / shell / Python の 3 箇所に
    重複しており、一部だけ直すと drift する。

本テストは「実機 unit に存在する重要な安全指定が、テンプレートgenerate された
成果物にも含まれること」を保証する。実機 unit が無い環境では skip する。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_systemd_template_fidelity -v
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ not in os.sys.path:
    os.sys.path.insert(0, _PROJ)

LIVE_UNIT_DIR = "/etc/systemd/system"

#: unit 上で省略してはならない意味的Pv大力な指令
#: key -> (必須发挥作用理由, 検証方法)
REQUIRED_DIRECTIVES = {
    "hq-api.service": {
        "Conflicts": "旧 DSP/DMP サービスとの同時起動防止 (69498d4e)",
    },
    "camilladsp.service": {
        "Restart": "CamillaDSP 異常終了時の自動復帰",
        "Environment": "HQ_DSP_YAML / CAMILLA_STATE_FILE の永続パス指定",
        "ExecStart": "設定ファイルパスの受け渡し",
    },
}


def _render(tpl_name: str, dest: str) -> str:
    """install_systemd_units.sh 同样的置換を最小構成で再現する。"""
    src = os.path.join(_PROJ, "config/systemd", tpl_name)
    with open(src, encoding="utf-8") as f:
        text = f.read()
    user = os.environ.get("USER", "tysbox")
    subs = {
        "@@HQM_ROOT@@": _PROJ,
        "@@HQM_USER@@": user,
        "@@HQM_GROUP@@": user,
        "@@HQM_HOME@@": os.path.expanduser("~"),
        "@@HQM_VENV@@": os.path.join(_PROJ, "backend/venv/bin/python3"),
        "@@HQ_API_PORT@@": "8003",
        "@@CAMILLA_BIN@@": shutil.which("camilladsp") or "/usr/local/bin/camilladsp",
        "@@CAMILLA_PORT@@": "1234",
        "@@CAMILLA_YAML@@": "/var/lib/camilladsp/active_dsp.yml",
        "@@CAMILLA_STATE@@": "/var/lib/camilladsp/state.yml",
        "@@CAMILLA_DIR@@": "/var/lib/camilladsp",
    }
    for k, v in subs.items():
        text = text.replace(k, v)
    self_path = os.path.join(dest, tpl_name.replace(".template", ""))
    with open(self_path, "w", encoding="utf-8") as f:
        f.write(text)
    return self_path


class TestSystemdTemplateFidelity(unittest.TestCase):
    """テンプレートの必須指令が欠落していないこと."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hqm-tpl-")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_template_contains_required_directives(self):
        """テンプレート本身に必須指令が含まれること（実機不要で確認可能）。"""
        for unit, directives in REQUIRED_DIRECTIVES.items():
            rendered = _render(f"{unit}.template", self.tmp)
            with open(rendered, encoding="utf-8") as f:
                text = f.read()
            for directive, reason in directives.items():
                with self.subTest(unit=unit, directive=directive):
                    self.assertTrue(
                        re.search(rf"^{directive}=", text, re.M),
                        f"{unit} テンプレートの {directive} が欠落しています ({reason})",
                    )

    @unittest.skipUnless(os.path.isdir(LIVE_UNIT_DIR), "実機 unit が存在しないため skip")
    def test_template_does_not_drop_live_safety_directives(self):
        """実機 unit の安全指定を template generate が落とさないこと。"""
        for unit, directives in REQUIRED_DIRECTIVES.items():
            live_path = os.path.join(LIVE_UNIT_DIR, unit)
            if not os.path.isfile(live_path):
                continue
            with open(live_path, encoding="utf-8") as f:
                live = f.read()
            rendered = _render(f"{unit}.template", self.tmp)
            with open(rendered, encoding="utf-8") as f:
                tpl = f.read()
            for directive, reason in directives.items():
                if not re.search(rf"^{directive}=", live, re.M):
                    continue
                with self.subTest(unit=unit, directive=directive):
                    self.assertTrue(
                        re.search(rf"^{directive}=", tpl, re.M),
                        f"{unit}: 実機には {directive} があるが template generate で消える ({reason})",
                    )

    @unittest.skipUnless(shutil.which("systemd-analyze"), "systemd-analyze 不在のため skip")
    def test_rendered_units_pass_systemd_verify(self):
        """生成された unit が systemd-analyze verify を通ること。"""
        for unit in REQUIRED_DIRECTIVES:
            with self.subTest(unit=unit):
                rendered = _render(f"{unit}.template", self.tmp)
                res = subprocess.run(
                    ["systemd-analyze", "verify", rendered],
                    capture_output=True, text=True,
                )
                # systemd-analyze は他のシステム unit の警告も出すため、
                # 検証対象 (レンダリングしたファイル) に起因するものだけを見る。
                own = [
                    ln for ln in (res.stderr or "").splitlines()
                    if ("Unknown key" in ln or "unknown lvalue" in ln)
                    and os.path.basename(rendered) in ln
                ]
                self.assertEqual(own, [], f"{unit}: {own}")


if __name__ == "__main__":
    unittest.main()
