import tkinter as tk
from tkinter import ttk, messagebox, font as tkFont
import subprocess
import time
import threading
import json
import os
from tkinter import PhotoImage
from PIL import Image, ImageTk # Pillow をインポート
import io # バイトデータを扱うためにインポート
import requests # URLから画像を取得するためにインポート
from mpd import MPDClient, MPDError # python-mpd2 をインポート
import logging
from logging.handlers import RotatingFileHandler
import shutil
import tempfile
import re
import glob


LOG_FILE = os.path.expanduser("~/.sox_gui.log")

logger = logging.getLogger("sox_gui")
logger.setLevel(logging.INFO)

# ログファイル 1MB, 最大5ファイル保持
handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# --- 定数 ---
CONFIG_FILE = os.path.expanduser("~/.sox_gui_config.json")
RUN_SOX_FIFO_SH = "/home/tysbox/bin/run_sox_fifo.sh" # シェルスクリプトのパス
DEFAULT_ALBUM_ART_PATH = "/home/tysbox/bin/istockphoto-178572410-612x612.png" # デフォルト画像パス
ALBUM_ART_SIZE = (250, 250) # 表示するアルバムアートのサイズ

# MPD接続設定
MPD_HOST = 'localhost'
MPD_PORT = 6600
MPD_POLL_INTERVAL = 2 # MPDポーリング間隔（秒）

# --- 各種エフェクト、フィルタ、再生方法設定値 ---
DEFAULT_MUSIC_TYPES = ["jazz", "classical", "electronic", "vocal", "none"]
DEFAULT_EFFECTS_TYPES = ["Viena-Symphony-Hall", "Suntory-Music-Hall", "NewMorning-JazzClub",
                         "Wembley-Studium", "AbbeyRoad-Studio", "vinyl", "none"]
DEFAULT_EQ_OUTPUT_TYPES = ["studio-monitors", "JBL-Speakers", "planar-magnetic", "bt-earphones",
                           "Tube-Warmth", "Crystal-Clarity", "none"]
DEFAULT_OUTPUT_METHODS = ["aplay", "soxplay"]
DEFAULT_NOISE_FIR_TYPES = ["default", "light", "medium", "strong", "off"] # シェルスクリプトのcaseに合わせる
DEFAULT_HARMONIC_FIR_TYPES = ["dynamic", "dead", "base", "med", "high", "off"] # シェルスクリプトのcaseに合わせる

# Presets external file (effects/eq lists + optional named presets)
PRESETS_FILE = os.path.expanduser("/home/tysbox/bin/presets.json")

def load_presets():
    """Load global presets/effects/eq lists from PRESETS_FILE and return a dict with keys 'effects','eq_outputs','presets'.
    If file missing or invalid, create a default structure and return it."""
    defaults = {
        "effects": ["Viena-Symphony-Hall","Suntory-Music-Hall","NewMorning-JazzClub","Wembley-Studium","AbbeyRoad-Studio","vinyl","none"],
        "eq_outputs": ["studio-monitors","JBL-Speakers","planar-magnetic","bt-earphones","Tube-Warmth","Crystal-Clarity","Monitor-Sim","none"],
        "presets": {}
    }
    try:
        with open(PRESETS_FILE, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = defaults
        try:
            with open(PRESETS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Created default presets file: %s", PRESETS_FILE)
        except Exception as e:
            logger.warning("Could not create presets file: %s", e)
    data.setdefault('effects', defaults['effects'])
    data.setdefault('eq_outputs', defaults['eq_outputs'])
    data.setdefault('presets', {})
    return data

# --- 設定ファイルの読み書き ---
def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}

    # 各キーの存在確認とデフォルト値設定
    config.setdefault("music_types", DEFAULT_MUSIC_TYPES.copy())
    config.setdefault("music_type", "none")
    config.setdefault("effects_type", "none")
    config.setdefault("eq_output_type", "none")
    config.setdefault("gain", "-5")
    config.setdefault("output_method", "aplay")
    config.setdefault("noise_fir_type", "default") # 新しい設定
    config.setdefault("harmonic_fir_type", "base") # 新しい設定
    config.setdefault("fade_ms", "150") # フェードイン時間（ms）
    config.setdefault("output_device", "BlueALSA") # 新しい設定: 出力デバイス (デフォルト BlueALSA)
    config.setdefault("crossfeed_enabled", "false")
    config.setdefault("crossfeed_preset", "off")
    config.setdefault("presets", {})

    # 古いプリセット形式からの移行（もし必要なら）
    for name, preset in config["presets"].items():
        preset.setdefault("noise_fir_type", config["noise_fir_type"])
        preset.setdefault("harmonic_fir_type", config["harmonic_fir_type"])

    return config

def save_config(config):
    """Save config atomically to avoid corruption from partial writes.
    Creates a temp file on the same filesystem and replaces the real file.
    Falls back to direct write on failure but logs the exception.
    """
    dirpath = os.path.dirname(CONFIG_FILE) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dirpath)
    try:
        with os.fdopen(fd, 'w') as tf:
            json.dump(config, tf, indent=4)
            tf.flush()
            os.fsync(tf.fileno())
        os.replace(tmp_path, CONFIG_FILE)
        logger.info("Saved config to %s", CONFIG_FILE)
    except Exception as e:
        logger.exception("Failed to save config atomically: %s", e)
        # Fallback: try simple write (less safe)
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)
        except Exception:
            logger.exception("Fallback save also failed.")
            raise
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def validate_settings(config):
    """設定の妥当性を簡易チェックして、無効なキーをリストで返す。"""
    errors = []
    # music_type はデフォルトまたはカスタムプリセットに含まれること
    mt = config.get("music_type", "")
    if mt not in DEFAULT_MUSIC_TYPES and mt not in config.get("music_types", []):
        errors.append("music_type")
    if config.get("effects_type") not in DEFAULT_EFFECTS_TYPES:
        errors.append("effects_type")
    if config.get("eq_output_type") not in DEFAULT_EQ_OUTPUT_TYPES:
        errors.append("eq_output_type")
    if config.get("output_method") not in DEFAULT_OUTPUT_METHODS:
        errors.append("output_method")
    gain = str(config.get("gain", ""))
    if not re.match(r'^-?\d+(?:\.\d+)?$', gain):
        errors.append("gain")
    if config.get("noise_fir_type") not in DEFAULT_NOISE_FIR_TYPES:
        errors.append("noise_fir_type")
    if config.get("harmonic_fir_type") not in DEFAULT_HARMONIC_FIR_TYPES:
        errors.append("harmonic_fir_type")
    # fade_ms は 0-5000 の整数
    try:
        fm = int(config.get("fade_ms", "0"))
        if fm < 0 or fm > 5000:
            errors.append("fade_ms")
    except Exception:
        errors.append("fade_ms")
    return errors


# --- サービス再起動 ---
def restart_service():
    """サービスを安全に再起動する。まずユーザー単位で存在するか試し、無ければ sudo 経由でシステム単位を実行する。
    sudo は -n を使ってパスワード要求が発生しないようにし、必要な場合はユーザーに手動実行を促す。"""
    # time.sleep() 削除: ファイルはsudo経由で即座に書き込まれるため不要
    # 書き込み完了時間: <100ms
    
    # 事前ミュート: 再起動時のポップ音防止のため、短い無音を FIFO に書き込む
    def _write_silence_to_fifo(duration_s=0.2, rate=192000, channels=2, bitdepth=32):
        fifo = '/tmp/mpd.fifo'
        try:
            frames = int(rate * duration_s)
            frame_bytes = (bitdepth // 8) * channels
            to_write = b'\x00' * (frames * frame_bytes)
            with open(fifo, 'wb') as f:
                f.write(to_write)
                f.flush()
            logger.info("Wrote %s seconds of silence to %s", duration_s, fifo)
            return True
        except Exception as e:
            logger.warning("Could not write silence to FIFO %s: %s", fifo, e)
            return False

    # 試しに短い無音を書き込み（失敗しても再起動は続行）
    _write_silence_to_fifo(duration_s=0.1)  # 200ms → 100ms に短縮

    def _run_systemctl(args, use_sudo=False):
        if use_sudo:
            cmd = ["/usr/bin/sudo", "-n", "/usr/bin/systemctl"] + args
        else:
            cmd = ["/usr/bin/systemctl"] + args
        logger.info("実行コマンド: %s", ' '.join(cmd))
        try:
            res = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info("systemctl 成功: stdout=%s stderr=%s", res.stdout, res.stderr)
            return True, res
        except subprocess.CalledProcessError as e:
            logger.error("systemctl 失敗: rc=%s stdout=%s stderr=%s", e.returncode, e.stdout, e.stderr)
            return False, e
        except Exception as e:
            logger.exception("systemctl 実行例外: %s", e)
            return False, e

    # まずユーザーサービスとして存在するかを確認
    ok, _ = _run_systemctl(["--user", "status", "run_sox_fifo.service"], use_sudo=False)
    if ok:
        # restart コマンドで統一（reset-failed 不要）
        ok2, res = _run_systemctl(["--user", "restart", "run_sox_fifo.service"], use_sudo=False)
        if ok2:
            logger.info("ユーザー単位のサービスを再起動しました。")
            # schedule GUI update on main thread
            try:
                root.after(500, update_gui_from_config)
                root.after(500, display_settings)
            except Exception:
                pass
            return
        else:
            messagebox.showerror("エラー", f"ユーザーサービスの再起動に失敗しました: {res}")
            return

    # ユーザーサービスが見つからない/再起動できない場合は sudo 経由で試す（非対話）
    ok3, res3 = _run_systemctl(["restart", "run_sox_fifo.service"], use_sudo=True)
    if ok3:
        logger.info("システムサービスを sudo で再起動しました。")
        try:
            root.after(500, update_gui_from_config)
            root.after(500, display_settings)
        except Exception:
            pass
        return

    # 非対話で失敗した場合、ターミナルでパスワードを入力して再試行するか確認
    stderr = getattr(res3, 'stderr', '') or str(res3)
    logger.warning("非対話 sudo に失敗しました: %s", stderr)

    # 対話的なユーザー確認/再起動はメインスレッドでダイアログを表示する必要があるため、
    # root.after() でメインスレッドに処理を委譲する。
    def _interactive_restart():
        try:
            if messagebox.askyesno("パスワードが必要", "サービスの再起動には sudo のパスワードが必要です。\nターミナルでパスワードを入力して再試行しますか？"):
                try:
                    subprocess.run(["/usr/bin/sudo", "/usr/bin/systemctl", "restart", "run_sox_fifo.service"], check=True)
                    logger.info("sudo による再起動が成功しました（対話）。")
                    messagebox.showinfo("成功", "サービスを再起動しました。")
                    try:
                        root.after(500, update_gui_from_config)
                        root.after(500, display_settings)
                    except Exception:
                        pass
                    return
                except subprocess.CalledProcessError as e:
                    logger.error("対話 sudo による再起動が失敗しました: %s", e)
                    messagebox.showerror("エラー", f"対話モードでの再起動に失敗しました:\n{e}")
                    return
                except Exception as e:
                    logger.exception("対話 sudo 実行中に例外が発生しました: %s", e)
                    messagebox.showerror("エラー", f"再起動中に予期せぬエラーが発生しました: {e}")
                    return
            else:
                # ユーザーが拒否した場合は手動で実行するよう案内
                messagebox.showinfo("情報", "ターミナルで `sudo systemctl restart run_sox_fifo.service` を実行してください。")
                return
        except Exception as e:
            logger.exception("Interactive restart dialog failed: %s", e)

    try:
        root.after(0, _interactive_restart)
    except Exception:
        logger.exception("Could not schedule interactive restart; advise user to run sudo systemctl restart run_sox_fifo.service")
        logger.info("ターミナルで `sudo systemctl restart run_sox_fifo.service` を実行してください。")

# --- シェルスクリプト書き換え ---
def update_shell_script(config):
    """設定をシェルスクリプトに反映する（バックアップ作成、検証、原子書き換え）。"""
    if not os.path.isfile(RUN_SOX_FIFO_SH):
        messagebox.showerror("エラー", f"{RUN_SOX_FIFO_SH} が存在しません。")
        return False

    # 値の妥当性チェック
    errs = validate_settings(config)
    if errs:
        messagebox.showerror("設定エラー", "無効な設定: " + ", ".join(errs))
        return False

    timestamp = time.strftime('%Y%m%dT%H%M%S')
    bak_path = f"{RUN_SOX_FIFO_SH}.bak.{timestamp}"
    try:
        shutil.copy2(RUN_SOX_FIFO_SH, bak_path)
        logger.info("バックアップを作成しました: %s", bak_path)

        # バックアップ先ディレクトリ
        backup_dir = "/home/tysbox/bin/backups"
        os.makedirs(backup_dir, exist_ok=True)

        # バックアップディレクトリに移動
        bak_path = os.path.join(backup_dir, os.path.basename(bak_path))
        shutil.move(f"{RUN_SOX_FIFO_SH}.bak.{timestamp}", bak_path)
        logger.info("バックアップを移動しました: %s", bak_path)

        # バックアップディレクトリ内のバックアップファイル数を制限
        backup_files = sorted(glob.glob(os.path.join(backup_dir, f"{os.path.basename(RUN_SOX_FIFO_SH)}.bak.*")))
        max_backups = 10
        if len(backup_files) > max_backups:
            for old_backup in backup_files[:-max_backups]:
                os.remove(old_backup)
                logger.info("古いバックアップを削除しました: %s", old_backup)

        with open(RUN_SOX_FIFO_SH, 'r') as f:
            lines = f.readlines()

        new_lines = []
        settings_to_update = {
            "MUSIC_TYPE": config["music_type"],
            "EFFECTS_TYPE": config["effects_type"],
            "EQ_OUTPUT_TYPE": config["eq_output_type"],
            "GAIN": config["gain"],
            "NOISE_FIR_TYPE": config["noise_fir_type"],
            "HARMONIC_FIR_TYPE": config["harmonic_fir_type"],
            "OUTPUT_METHOD": config["output_method"],
            "FADE_MS": config.get("fade_ms", "150"),
            "OUTPUT_DEVICE": config.get("output_device", "BlueALSA"),
            "CROSSFEED_ENABLED": config.get("crossfeed_enabled", "false"),
            "CROSSFEED_PRESET": config.get("crossfeed_preset", "off")
        }

        for line in lines:
            updated = False
            for key, value in settings_to_update.items():
                if line.strip().startswith(f'{key}='):
                    # 値を安全にエスケープ（改行とダブルクォート、バックスラッシュを除去/エスケープ）
                    safe_val = str(value).replace('\n', '').replace('"', '\\"').replace('\\', '\\\\')
                    new_lines.append(f'{key}="{safe_val}"\n')
                    updated = True
                    break
            if updated:
                continue
            new_lines.append(line)

        # 原子的に書き込む
        dirpath = os.path.dirname(RUN_SOX_FIFO_SH) or '.'
        fd, tmp_path = tempfile.mkstemp(dir=dirpath)
        try:
            with os.fdopen(fd, 'w') as tf:
                tf.writelines(new_lines)
            shutil.copymode(RUN_SOX_FIFO_SH, tmp_path)

            # 書き込み後に bash の構文チェックを行う
            subprocess.run(['/bin/bash', '-n', tmp_path], check=True, capture_output=True, text=True)

            # 問題なければ差し替え
            os.replace(tmp_path, RUN_SOX_FIFO_SH)
            logger.info("%s を更新しました。バックアップ: %s", RUN_SOX_FIFO_SH, bak_path)
            return True
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    except subprocess.CalledProcessError as e:
        # 構文チェック失敗: バックアップから復元
        try:
            shutil.copy2(bak_path, RUN_SOX_FIFO_SH)
        except Exception:
            pass
        logger.error("スクリプトの構文チェックに失敗しました: %s", e.stderr)
        messagebox.showerror("エラー", f"スクリプトの構文チェックに失敗しました。変更を元に戻しました。\n{e.stderr}")
        return False
    except Exception as e:
        logger.exception("シェルスクリプト更新中にエラー: %s", e)
        messagebox.showerror("エラー", f"{RUN_SOX_FIFO_SH} の更新に失敗しました: {e}")
        return False

# --- デバイス設定ファイル書き込み（高速なデバイス再構成用）---
def write_device_conf(output_device):
    """OUTPUT_DEVICE を /tmp/sox_device.conf に書き込み、スクリプト側で動的に読み込まれる。
    これにより、サービス全体の再起動不要で、パイプラインのみ再起動される。"""
    device_conf = "/tmp/sox_device.conf"
    try:
        with open(device_conf, 'w') as f:
            f.write(f'OUTPUT_DEVICE={output_device}\n')
        os.chmod(device_conf, 0o666)  # スクリプトから読み込めるようにパーミッション設定
        logger.info("デバイス設定ファイルを更新: %s (OUTPUT_DEVICE=%s)", device_conf, output_device)
        return True
    except Exception as e:
        logger.error("デバイス設定ファイル更新失敗: %s", e)
        return False

# --- 設定適用 ---
def apply_settings():
    selected_music_type = music_listbox.get(tk.ACTIVE) if music_listbox.curselection() else config["music_type"]

    # プリセット適用 or 個別設定取得
    if selected_music_type in config["presets"]:
        preset = config["presets"][selected_music_type]
        config["music_type"] = selected_music_type
        # UI による個別変更がプリセットと異なる場合は UI の値を優先（手動オーバーライド）
        ui_values = {
            "effects_type": effects_var.get(),
            "eq_output_type": eq_var.get(),
            "gain": gain_var.get(),
            "noise_fir_type": noise_fir_var.get(),
            "harmonic_fir_type": harmonic_fir_var.get(),
            "output_method": output_method_var.get(),
            "fade_ms": fade_ms_var.get(),
            "crossfeed_enabled": crossfeed_enabled_var.get(),
            "crossfeed_preset": crossfeed_preset_var.get()
        }
        override = any(str(ui_values[k]) != str(preset.get(k, ui_values[k])) for k in ui_values)
        if override:
            logger.info("Preset '%s' overridden by UI values; applying manual settings", selected_music_type)
            config.update(ui_values)
        else:
            # プリセットの値をそのまま使用（プリセットに項目が無い場合は UI 値を使用）
            config["effects_type"] = preset.get("effects_type", ui_values["effects_type"])
            config["eq_output_type"] = preset.get("eq_output_type", ui_values["eq_output_type"])
            config["gain"] = preset.get("gain", ui_values["gain"])
            config["noise_fir_type"] = preset.get("noise_fir_type", ui_values["noise_fir_type"])
            config["harmonic_fir_type"] = preset.get("harmonic_fir_type", ui_values["harmonic_fir_type"])
            config["crossfeed_enabled"] = preset.get("crossfeed_enabled", ui_values["crossfeed_enabled"])
            config["crossfeed_preset"] = preset.get("crossfeed_preset", ui_values["crossfeed_preset"])
            config["output_method"] = ui_values["output_method"]
            config["fade_ms"] = ui_values["fade_ms"]
    else:
        config["music_type"] = selected_music_type
        config["effects_type"] = effects_var.get()
        config["eq_output_type"] = eq_var.get()
        config["gain"] = gain_var.get()
        config["noise_fir_type"] = noise_fir_var.get()
        config["harmonic_fir_type"] = harmonic_fir_var.get()
        config["output_method"] = output_method_var.get()
        config["fade_ms"] = fade_ms_var.get()
        config["crossfeed_enabled"] = crossfeed_enabled_var.get()
        config["crossfeed_preset"] = crossfeed_preset_var.get()

    # Note: output_device is managed via presets and edit dialog; no main-device combobox by default.

    # GUI表示を更新
    update_gui_from_config()
    display_settings() # 下部のテキスト表示も更新

    print("適用される設定:")
    print(json.dumps(config, indent=2))

    # 設定の妥当性を簡易チェックする
    errs = validate_settings(config)
    if errs:
        messagebox.showerror("設定エラー", "無効な設定: " + ", ".join(errs))
        return

    # === 高速化: OUTPUT_DEVICE のみ変更ケース ===
    # 出力デバイスのみが変更された場合は、コンフィグファイルに書き込むだけで
    # スクリプト側が自動的にパイプラインを再構成（サービス再起動不要）
    output_device = config.get("output_device", "BlueALSA")
    
    # 現在のシェルスクリプトから OUTPUT_DEVICE を抽出して判定
    prev_output_device = None
    try:
        with open(RUN_SOX_FIFO_SH, 'r') as f:
            for line in f:
                if line.strip().startswith('OUTPUT_DEVICE='):
                    prev_output_device = line.split('=', 1)[1].strip().strip('"')
                    break
    except Exception:
        prev_output_device = None
    
    # デバイス変更検出
    if prev_output_device and prev_output_device != output_device:
        # === 高速パス: OUTPUT_DEVICE のみ変更 ===
        logger.info("OUTPUT_DEVICE のみが変更されました。高速再構成開始: %s → %s", prev_output_device, output_device)
        if write_device_conf(output_device):
            # スクリプト側で自動検出・再構成
            messagebox.showinfo("デバイス変更", f"出力デバイスを切り替えました: {output_device}\\n(応答時間: <100ms)")
            save_config(config)
            return
    
    # === 通常パス: その他の設定が変更された ===
    if update_shell_script(config):
        save_config(config)
        
        # === 重要: デバイス設定ファイルにも常に最新の output_device を書き込む ===
        # これにより、フルスクリプト更新時でも /tmp/sox_device.conf が最新状態に保たれ、
        # メインループが即座にデバイス変更を検出できる
        write_device_conf(output_device)
        
        # サービス再起動を別スレッドで実行
        threading.Thread(target=restart_service, daemon=True).start()
        messagebox.showinfo("設定適用", "設定をシェルスクリプトに反映し、サービス再起動を開始しました。")

# --- GUI表示をconfigに基づいて更新 ---
def update_gui_from_config():
    # Music Type Listbox (選択状態を更新)
    try:
        idx = config["music_types"].index(config["music_type"])
        music_listbox.selection_clear(0, tk.END)
        music_listbox.selection_set(idx)
        music_listbox.activate(idx)
        music_listbox.see(idx)
    except ValueError:
        # music_typeがリストにない場合 (ありえないはずだが念のため)
        if config["music_types"]:
             music_listbox.selection_set(0)
             music_listbox.activate(0)
             music_listbox.see(0)


    effects_var.set(config["effects_type"])
    eq_var.set(config["eq_output_type"])
    gain_var.set(config["gain"])
    noise_fir_var.set(config["noise_fir_type"])
    harmonic_fir_var.set(config["harmonic_fir_type"])
    output_method_var.set(config["output_method"])
    try:
        fade_ms_var.set(config.get("fade_ms", "150"))
        crossfeed_enabled_var.set(config.get("crossfeed_enabled", "false"))
        crossfeed_preset_var.set(config.get("crossfeed_preset", "off"))
    except NameError:
        pass



    # main output device (existence check and set by display name)
    try:
        # find display name for configured device id
        configured = config.get("output_device", "")
        # no main output combobox present in simplified display; nothing to set here
    except NameError:
        pass



# --- プリセット編集 ---
def edit_preset():
    selected_index = music_listbox.curselection()
    if not selected_index:
        messagebox.showinfo("情報", "編集または新規作成の基にするMusic Typeを選択してください。")
        return
    base_music_type = music_listbox.get(selected_index[0])

    # 既存のプリセットか、現在の設定を初期値とする
    initial_preset = config["presets"].get(base_music_type, {
        "effects_type": effects_var.get(),
        "eq_output_type": eq_var.get(),
        "gain": gain_var.get(),
        "noise_fir_type": noise_fir_var.get(),
        "harmonic_fir_type": harmonic_fir_var.get()
    })
    initial_name = base_music_type if base_music_type not in DEFAULT_MUSIC_TYPES else ""

    edit_window = tk.Toplevel(root)
    edit_window.title("プリセット編集/新規作成")

    # --- プリセット名 ---
    name_frame = ttk.Frame(edit_window, padding="10")
    name_frame.pack(fill=tk.X)
    ttk.Label(name_frame, text="プリセット名:").pack(side=tk.LEFT, padx=5)
    preset_name_var = tk.StringVar(value=initial_name)
    preset_name_entry = ttk.Entry(name_frame, textvariable=preset_name_var, width=30)
    preset_name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # --- 各設定項目 (ttk.Notebook を使用) ---
    notebook = ttk.Notebook(edit_window, padding="10")
    notebook.pack(fill=tk.BOTH, expand=True)

    # エフェクトタブ
    effects_tab = ttk.Frame(notebook, padding="10")
    notebook.add(effects_tab, text="Effects")
    edit_effects_var = tk.StringVar(value=initial_preset["effects_type"])
    effects_lf = ttk.LabelFrame(effects_tab, text="Effects Type:", padding="10")
    effects_lf.pack(fill=tk.BOTH, expand=True)
    
    # 縦1列で表示
    for effect in DEFAULT_EFFECTS_TYPES:
        ttk.Radiobutton(effects_lf, text=effect, variable=edit_effects_var, value=effect).pack(anchor=tk.NW, padx=5, pady=2)


    # EQ/FIRタブ
    eq_fir_tab = ttk.Frame(notebook, padding="10")
    notebook.add(eq_fir_tab, text="EQ / FIR")
    eq_fir_tab.columnconfigure(0, weight=1)
    eq_fir_tab.columnconfigure(1, weight=1)

    # Noise FIR
    edit_noise_fir_var = tk.StringVar(value=initial_preset["noise_fir_type"])
    noise_fir_lf = ttk.LabelFrame(eq_fir_tab, text="Noise Reduction FIR", padding="10")
    noise_fir_lf.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
    for noise_fir in DEFAULT_NOISE_FIR_TYPES:
        ttk.Radiobutton(noise_fir_lf, text=noise_fir.capitalize(), variable=edit_noise_fir_var, value=noise_fir).pack(anchor=tk.NW, padx=5)

    # Harmonic FIR
    edit_harmonic_fir_var = tk.StringVar(value=initial_preset["harmonic_fir_type"])
    harmonic_fir_lf = ttk.LabelFrame(eq_fir_tab, text="Harmonic FIR", padding="10")
    harmonic_fir_lf.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
    for harm_fir in DEFAULT_HARMONIC_FIR_TYPES:
        ttk.Radiobutton(harmonic_fir_lf, text=harm_fir.capitalize(), variable=edit_harmonic_fir_var, value=harm_fir).pack(anchor=tk.NW, padx=5)

    # Output EQ
    edit_eq_var = tk.StringVar(value=initial_preset["eq_output_type"])
    eq_output_lf = ttk.LabelFrame(eq_fir_tab, text="Output EQ", padding="10")
    eq_output_lf.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
    # Output EQ項目が多い場合はスクロールフレーム化を検討
    col_count = 2 # 2列で表示
    for i, eq_out in enumerate(DEFAULT_EQ_OUTPUT_TYPES):
        rb = ttk.Radiobutton(eq_output_lf, text=eq_out, variable=edit_eq_var, value=eq_out)
        rb.grid(row=i // col_count, column=i % col_count, sticky=tk.W, padx=5)


    # ゲインタブ
    gain_tab = ttk.Frame(notebook, padding="10")
    notebook.add(gain_tab, text="Gain")
    edit_gain_var = tk.StringVar(value=initial_preset["gain"])
    gain_lf = ttk.LabelFrame(gain_tab, text="Gain (dB)", padding="10")
    gain_lf.pack(fill=tk.X)
    gain_entry = ttk.Entry(gain_lf, textvariable=edit_gain_var, width=10)
    gain_entry.pack(pady=5)

    # Output device selection is global (managed in Gain tab). Removed local preset-level output device control to avoid duplication.
    # --- 保存ボタン ---
    def save_preset_action():
        preset_name = preset_name_var.get().strip()
        if not preset_name:
            messagebox.showerror("エラー", "プリセット名を入力してください。", parent=edit_window)
            return
        if preset_name in DEFAULT_MUSIC_TYPES and preset_name != base_music_type:
             messagebox.showerror("エラー", f"'{preset_name}' はデフォルト名のため使用できません。", parent=edit_window)
             return

        # 新しいプリセットデータ
        new_preset_data = {
            "effects_type": edit_effects_var.get(),
            "eq_output_type": edit_eq_var.get(),
            "gain": edit_gain_var.get(),
            "noise_fir_type": edit_noise_fir_var.get(),
            "harmonic_fir_type": edit_harmonic_fir_var.get()
        }

        # 既存のプリセットを上書き、または新規追加
        config["presets"][preset_name] = new_preset_data

        # Music Typeリストを更新
        if preset_name not in config["music_types"]:
            config["music_types"].append(preset_name)
            music_listbox.insert(tk.END, preset_name)
        # もし名前変更した場合、古いカスタムプリセット名を削除
        if base_music_type != preset_name and base_music_type not in DEFAULT_MUSIC_TYPES:
             if base_music_type in config["presets"]:
                 del config["presets"][base_music_type]
             if base_music_type in config["music_types"]:
                 idx_to_del = config["music_types"].index(base_music_type)
                 config["music_types"].pop(idx_to_del)
                 music_listbox.delete(idx_to_del)


        save_config(config)
        print(f"プリセット '{preset_name}' を保存しました。")
        display_settings() # メインウィンドウの表示更新
        update_gui_from_config() # メインウィンドウの選択状態も更新
        edit_window.destroy()

    save_button = ttk.Button(edit_window, text="保存", command=save_preset_action)
    save_button.pack(pady=10)

# --- プリセット削除 ---
def delete_preset():
    selected_index = music_listbox.curselection()
    if not selected_index:
        messagebox.showinfo("情報", "削除するカスタムプリセットを選択してください。")
        return

    selected_music_type = music_listbox.get(selected_index[0])

    if selected_music_type in DEFAULT_MUSIC_TYPES:
        messagebox.showinfo("情報", "デフォルトのMusic Typeは削除できません。")
    elif selected_music_type in config["presets"]:
        if messagebox.askyesno("確認", f"カスタムプリセット '{selected_music_type}' を削除しますか？"):
            del config["presets"][selected_music_type]
            config["music_types"].remove(selected_music_type)
            music_listbox.delete(selected_index[0])
            save_config(config)
            print(f"プリセット '{selected_music_type}' を削除しました。")
            # 削除後はデフォルトを選択状態にするなど
            config["music_type"] = "none"
            update_gui_from_config()
            display_settings()
    else:
        # プリセットではないがリストに存在するカスタム名の場合（ありえないはずだが）
         if selected_music_type in config["music_types"]:
             if messagebox.askyesno("確認", f"Music Typeリストから '{selected_music_type}' を削除しますか？ (プリセットはありません)"):
                 config["music_types"].remove(selected_music_type)
                 music_listbox.delete(selected_index[0])
                 save_config(config)
                 print(f"Music Type '{selected_music_type}' を削除しました。")
                 config["music_type"] = "none"
                 update_gui_from_config()
                 display_settings()


# --- Presets 再読み込み ---
def reload_presets_action():
    try:
        pdata = load_presets()
        merged = False
        for pname, pvals in pdata.get('presets', {}).items():
            if pname not in config.get('presets', {}):
                config.setdefault('presets', {})[pname] = pvals
                merged = True
            if pname not in config.get('music_types', []):
                config.setdefault('music_types', []).append(pname)
                music_listbox.insert(tk.END, pname)
                merged = True
        if merged:
            save_config(config)
            messagebox.showinfo('完了', 'Presets を再読み込みして Music Type リストに反映しました。')
            display_settings()
        else:
            messagebox.showinfo('情報', '新しいプリセットは見つかりませんでした。')
    except Exception as e:
        logger.exception('reload_presets_action failed: %s', e)
        messagebox.showerror('エラー', f'Presets の再読込に失敗しました: {e}')


# --- 現在設定表示 ---

def display_settings():
    active_type = music_listbox.get(tk.ACTIVE) if music_listbox.curselection() else config["music_type"]
    settings_text = f"Music Type: {active_type}\n"
    settings_text += f"Noise FIR: {config['noise_fir_type']} | "
    settings_text += f"Harmonic FIR: {config['harmonic_fir_type']}\n"
    settings_text += f"Output EQ: {config['eq_output_type']}\n"
    settings_text += f"Effects: {config['effects_type']}\n"
    settings_text += f"Gain: {config['gain']} dB | "
    settings_text += f"Output: {config['output_method']}\n"
    settings_text += f"Crossfeed: {config.get('crossfeed_enabled','false')} ({config.get('crossfeed_preset','off')})"
    settings_label.config(text=settings_text)

# --- アルバムアート関連 ---
def extract_main_artist(artist_field):
    """
    複数アーティストが混在するartistフィールドから、検索に適したメインアーティスト名を抽出
    例:
      'CHICK COREA; Christian McBride, CHICK COREA' → 'CHICK COREA'
    """
    if not artist_field:
        return ""

    # セミコロンで区切られていたら、最初のアーティストを使う
    if ";" in artist_field:
        return artist_field.split(";")[0].strip()

    # カンマでも同様に分割
    if "," in artist_field:
        return artist_field.split(",")[0].strip()

    return artist_field.strip()

def fetch_album_art_from_itunes(artist, album):
    try:
        logger.debug("iTunes lookup: %s - %s", artist, album)
        query = f"{artist} {album}".replace(" ", "+")
        url = f"https://itunes.apple.com/search?term={query}&entity=album&limit=1"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        results = response.json().get("results")
        if results:
            art_url = results[0].get("artworkUrl100")
            if art_url:
                art_url = art_url.replace("100x100", "600x600")
                return fetch_art_from_url(art_url)
        logger.debug("iTunes: no artwork for %s - %s", artist, album)
    except Exception as e:
        logger.debug("iTunes lookup error: %s", e)
    return None


def fetch_album_art_from_musicbrainz(artist, album):
    try:
        logger.debug("MusicBrainz lookup: %s - %s", artist, album)
        headers = {"User-Agent": "sox-gui/1.0 (tysbox@example.com)"}
        query = f'"{album}" AND artist:"{artist}"'
        url = f"https://musicbrainz.org/ws/2/release/?query={query}&fmt=json&limit=1"
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        releases = data.get("releases", [])
        if not releases:
            logger.debug("MusicBrainz: no releases for %s - %s", artist, album)
            return None

        mbid = releases[0].get("id")
        logger.debug("MusicBrainz release id: %s", mbid)

        art_url = f"https://coverartarchive.org/release/{mbid}/front-500.jpg"
        return fetch_art_from_url(art_url)

    except Exception as e:
        logger.debug("MusicBrainz/CoverArt error: %s", e)
        return None

def fetch_album_art(mpd_client):
    try:
        status = mpd_client.status()
        song_id = status.get('songid')
        if not song_id:
            return None
        current_song = mpd_client.currentsong()
        if not current_song:
            return None

        logger.info(f"現在の曲情報: {current_song}")

        # 1. albumart タグ（最優先）
        if 'albumart' in current_song:
            art_uri = current_song['albumart']
            if art_uri.startswith('http'):
                return fetch_art_from_url(art_uri)
            elif os.path.exists(art_uri):
                return load_art_from_path(art_uri)

        # 2. アーティストとアルバムの取得＋整形
        artist_raw = current_song.get("artist")
        album = current_song.get("album")
        if not artist_raw or not album:
            return None

        # 🔧 複数アーティスト・作曲家混在時の対策
        artist = extract_main_artist(artist_raw)

        # 3. iTunes API を優先的に使う
        art = fetch_album_art_from_itunes(artist, album)
        if art:
            return art

        # 4. iTunesで見つからない → MusicBrainzを使う
        art = fetch_album_art_from_musicbrainz(artist, album)
        if art:
            return art

        # 見つからなかった場合
        logger.warning(f"アルバムアートが見つかりませんでした: {artist} - {album}")
        return None

    except MPDError as e:
        logger.error(f"MPDステータス取得エラー: {e}")
        return None
    except Exception as e:
        logger.error(f"アルバムアート取得中に予期せぬエラー: {e}", exc_info=True)
        return None

def fetch_art_from_url(url):
    try:
        logger.debug("Fetching album art URL: %s", url)
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        logger.debug("Fetched album art: status=%s size=%s", response.status_code, len(response.content))
        return process_image_data(response.content)
    except requests.exceptions.RequestException as e:
        logger.debug("fetch_art_from_url request error %s: %s", url, e)
        return None
    except Exception as e:
        logger.exception("fetch_art_from_url processing error: %s", e)
        return None
        
def load_art_from_path(path):
    try:
        with open(path, 'rb') as f:
            image_data = f.read()
        return process_image_data(image_data)
    except FileNotFoundError:
        logger.debug("Local album art file not found: %s", path)
        return None
    except Exception as e:
        logger.debug("load_art_from_path error: %s", e)
        return None


def process_image_data(image_data):
    try:
        img = Image.open(io.BytesIO(image_data)).convert('RGBA')
        w, h = img.size
        m = min(w, h)
        img = img.crop(((w-m)//2, (h-m)//2, (w+m)//2, (h+m)//2))
        tw = album_art_label.winfo_width()
        th = album_art_label.winfo_height()
        if tw < 10 or th < 10:
            size = 2500
        else:
            size = min(tw, th)
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        logger.info("画像リサイズ成功: %s", img.size)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        logger.exception("画像データ処理エラー: %s", e)
        return None
        
def update_album_art_display(photo_image):
    if photo_image:
        album_art_label.config(image=photo_image)
        album_art_label.image = photo_image # 参照を保持
    else:
        # デフォルト画像表示
        try:
            default_image = Image.open(DEFAULT_ALBUM_ART_PATH)
            target_width = album_art_label.winfo_width()
            target_height = album_art_label.winfo_height()
            if target_width < 10 or target_height < 10:
               size = 2500
            else:
               size = min(target_width, target_height)

            default_image = default_image.resize((size, size), Image.Resampling.LANCZOS)
            default_photo = ImageTk.PhotoImage(default_image)
            album_art_label.config(image=default_photo)
            album_art_label.image = default_photo

        except Exception as e:
             logger.warning("Default album art load failed: %s", e)
             album_art_label.config(image=None)
             album_art_label.image = None


def mpd_poller():
    global mpd_client, last_song_id
    while True:
        try:
            if mpd_client is None:
                logger.info("MPD connecting...")
                mpd_client = MPDClient()
                mpd_client.connect(MPD_HOST, MPD_PORT, timeout=5)
                logger.info("MPD connected (v%s)", mpd_client.mpd_version)
                last_song_id = None

            status = mpd_client.status()
            current_song_id = status.get('songid')
            if current_song_id != last_song_id:
                logger.debug("Detected song change: %s -> %s", last_song_id, current_song_id)
                new_art = fetch_album_art(mpd_client)
                root.after(0, update_album_art_display, new_art)
                last_song_id = current_song_id

            mpd_client.ping()

        except (MPDError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning("MPD connection error or disconnect: %s", e)
            if mpd_client:
                try:
                    mpd_client.close()
                    mpd_client.disconnect()
                except:
                    pass
            mpd_client = None
            last_song_id = None
            root.after(0, update_album_art_display, None)
            time.sleep(MPD_POLL_INTERVAL * 2)
            continue

        except Exception as e:
             logger.exception("Unexpected error during MPD polling: %s", e)
             time.sleep(MPD_POLL_INTERVAL * 2)
             continue


        time.sleep(MPD_POLL_INTERVAL)

# --- スクロール可能フレームクラス ---
class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # マウスホイールでのスクロールを有効にする (Linux/Windows)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units")) # Windows
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units")) # Linux (Up)
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units")) # Linux (Down)


# --- GUI ---
root = tk.Tk()
# --- ウィンドウ位置とペインサイズを保存/復元 ---
def save_window_state():
    config["window_geometry"] = root.geometry()

    try:
        total_width = main_paned_window.winfo_width()
        sash_pos = main_paned_window.sashpos(0)
        config["pane_ratio"] = sash_pos / total_width if total_width > 0 else 0.5
    except:
        config["pane_ratio"] = 0.5

    # Remove old right_vertical_ratio if exists
    config.pop("right_vertical_ratio", None)

    save_config(config)

root.protocol("WM_DELETE_WINDOW", lambda: (save_window_state(), root.destroy()))
root.title("SoX DSP Controller")

# フォント設定
default_font = tkFont.nametofont("TkDefaultFont")
default_font.configure(size=11) # 少し大きめに
label_font = tkFont.Font(family="Helvetica", size=12, weight="bold")
listbox_font = tkFont.Font(family="Helvetica", size=11)
button_font = tkFont.Font(family="Helvetica", size=12)
status_font = tkFont.Font(family="Courier", size=10)

# スタイル設定
style = ttk.Style()
style.configure("TLabel", font=default_font)
style.configure("TRadiobutton", font=default_font)
style.configure("TButton", font=button_font)
style.configure("TEntry", font=default_font)
style.configure("TListbox", font=listbox_font)
style.configure("TNotebook.Tab", font=default_font, padding=[5, 2])
style.configure("TLabelframe.Label", font=label_font)

# 設定読み込み
config = load_config()

# --- メインレイアウト (PanedWindow で左右に分割) ---
main_paned_window = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

# 左ペイン: 設定項目
left_frame = ttk.Frame(main_paned_window, padding="10")
main_paned_window.add(left_frame, weight=1) # 幅の比率

# 右ペイン: アルバムアートと状態表示を上下で分割できるようにする
right_paned_window = ttk.PanedWindow(main_paned_window, orient=tk.VERTICAL)
main_paned_window.add(right_paned_window, weight=4)

# 上：アルバムアート用フレーム
album_art_frame = ttk.Frame(right_paned_window, padding="10")
right_paned_window.add(album_art_frame, weight=3)

# 下：状態表示用フレーム (復旧)
settings_view_frame = ttk.Frame(right_paned_window, padding="10")
right_paned_window.add(settings_view_frame, weight=1)

# --- 左ペインの内容 ---
# Music Type / Preset List
music_lf = ttk.LabelFrame(left_frame, text="Music Type / Preset", padding="10")
music_lf.pack(fill=tk.X, pady=(0, 10))
music_listbox = tk.Listbox(music_lf, height=8, font=listbox_font, exportselection=False)
music_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
music_scrollbar = ttk.Scrollbar(music_lf, orient=tk.VERTICAL, command=music_listbox.yview)
music_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
music_listbox.config(yscrollcommand=music_scrollbar.set)

for item in config["music_types"]:
    music_listbox.insert(tk.END, item)
# Merge presets from external presets.json into config and the music list (if any)
try:
    pdata = load_presets()
    merged = False
    for pname, pvals in pdata.get('presets', {}).items():
        if pname not in config.get('presets', {}):
            config.setdefault('presets', {})[pname] = pvals
            merged = True
        if pname not in config.get('music_types', []):
            config.setdefault('music_types', []).append(pname)
            music_listbox.insert(tk.END, pname)
            merged = True
    if merged:
        save_config(config)
        logger.info("Merged %d external presets from %s into config/music list", len(pdata.get('presets', {})), PRESETS_FILE)
except Exception as e:
    logger.warning("Failed to merge external presets from %s: %s", PRESETS_FILE, e)

# Listbox選択変更時のイベント追加（オプション）
# music_listbox.bind('<<ListboxSelect>>', on_music_type_select)

# プリセット操作ボタン
preset_button_frame = ttk.Frame(music_lf)
preset_button_frame.pack(fill=tk.X, pady=(5,0))
edit_button = ttk.Button(preset_button_frame, text="編集/新規", command=edit_preset, width=12)
edit_button.pack(fill=tk.X, pady=2)
delete_button = ttk.Button(preset_button_frame, text="削除", command=delete_preset, width=12)
delete_button.pack(fill=tk.X, pady=2)
reload_button = ttk.Button(preset_button_frame, text="再読み込み", command=lambda: reload_presets_action(), width=12)
reload_button.pack(fill=tk.X, pady=2)


# --- 設定タブ ---
settings_notebook = ttk.Notebook(left_frame)
settings_notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

# FIRタブ
fir_tab = ttk.Frame(settings_notebook, padding="10")
settings_notebook.add(fir_tab, text="FIR Filters")
fir_tab.columnconfigure(0, weight=1)
fir_tab.columnconfigure(1, weight=1)

# Noise FIR
noise_fir_var = tk.StringVar(value=config["noise_fir_type"])
noise_lf = ttk.LabelFrame(fir_tab, text="Noise Reduction", padding="10")
noise_lf.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
for noise_type in DEFAULT_NOISE_FIR_TYPES:
    ttk.Radiobutton(noise_lf, text=noise_type.capitalize(), variable=noise_fir_var, value=noise_type).pack(anchor=tk.W, padx=5)

# Harmonic FIR
harmonic_fir_var = tk.StringVar(value=config["harmonic_fir_type"])
harmonic_lf = ttk.LabelFrame(fir_tab, text="Harmonics", padding="10")
harmonic_lf.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
for harm_type in DEFAULT_HARMONIC_FIR_TYPES:
    ttk.Radiobutton(harmonic_lf, text=harm_type.capitalize(), variable=harmonic_fir_var, value=harm_type).pack(anchor=tk.W, padx=5)

# EQタブ
eq_tab = ttk.Frame(settings_notebook, padding="10")
settings_notebook.add(eq_tab, text="Output EQ")
eq_var = tk.StringVar(value=config["eq_output_type"])
eq_lf = ttk.LabelFrame(eq_tab, text="Device EQ", padding="10")
eq_lf.pack(fill=tk.BOTH, expand=True)
# EQ項目を複数列で表示
col_count = 2
for i, eq_type in enumerate(DEFAULT_EQ_OUTPUT_TYPES):
    rb = ttk.Radiobutton(eq_lf, text=eq_type, variable=eq_var, value=eq_type)
    rb.grid(row=i // col_count, column=i % col_count, sticky=tk.W, padx=10, pady=2)


# Effectsタブ
effects_tab = ttk.Frame(settings_notebook, padding="10")
settings_notebook.add(effects_tab, text="Effects")
effects_var = tk.StringVar(value=config["effects_type"])
effects_lf = ttk.LabelFrame(effects_tab, text="Ambience & Dynamics", padding="10")
effects_lf.pack(fill=tk.BOTH, expand=True)
# Effects項目を縦1列で表示
for effect_type in DEFAULT_EFFECTS_TYPES:
     rb = ttk.Radiobutton(effects_lf, text=effect_type, variable=effects_var, value=effect_type)
     rb.pack(anchor=tk.W, padx=10, pady=2)

# --- Crossfeed (bs2b) セクション (Effectsタブ内に追加) ---
crossfeed_lf = ttk.LabelFrame(effects_tab, text="Crossfeed (bs2b)", padding="10")
crossfeed_lf.pack(fill=tk.X, pady=(10, 0))

crossfeed_enabled_var = tk.StringVar(value=config.get("crossfeed_enabled", "false"))
crossfeed_preset_var = tk.StringVar(value=config.get("crossfeed_preset", "off"))

ttk.Checkbutton(crossfeed_lf, text="Enable Crossfeed", variable=crossfeed_enabled_var, 
                onvalue="true", offvalue="false").pack(side=tk.LEFT, padx=5)

ttk.Label(crossfeed_lf, text="Preset:").pack(side=tk.LEFT, padx=(10, 5))
crossfeed_presets = ["default", "cmoy", "jmeier", "off"]
crossfeed_cb = ttk.Combobox(crossfeed_lf, textvariable=crossfeed_preset_var, values=crossfeed_presets, state="readonly", width=10)
crossfeed_cb.pack(side=tk.LEFT, padx=5)

# Gain/Outputタブ
gain_output_tab = ttk.Frame(settings_notebook, padding="10")
settings_notebook.add(gain_output_tab, text="Gain / Output")

# 各項目を縦一列に表示 (各項目を pack で順次配置)
# Gain
gain_var = tk.StringVar(value=config["gain"])
gain_lf = ttk.LabelFrame(gain_output_tab, text="Global Gain (dB)", padding="10")
gain_lf.pack(fill=tk.X, pady=(0, 10))
gain_entry = ttk.Entry(gain_lf, textvariable=gain_var, width=8, font=default_font)
gain_entry.pack(pady=5)

# Fade (ms)
try:
    fade_ms_var
except NameError:
    fade_ms_var = tk.StringVar(value=config.get("fade_ms", "150"))
fade_lf = ttk.LabelFrame(gain_output_tab, text="Fade-in (ms)", padding=6)
fade_lf.pack(fill=tk.X, pady=(0, 10))
fade_entry = ttk.Entry(fade_lf, textvariable=fade_ms_var, width=8)
fade_entry.pack(side=tk.LEFT, padx=5)

# Output Method
try:
    output_method_var
except NameError:
    output_method_var = tk.StringVar(value=config.get("output_method", "aplay"))
method_lf = ttk.LabelFrame(gain_output_tab, text="Output Method", padding=6)
method_lf.pack(fill=tk.X, pady=(0, 10))
for method in DEFAULT_OUTPUT_METHODS:
    ttk.Radiobutton(method_lf, text=method, variable=output_method_var, value=method).pack(side=tk.LEFT, padx=5)

# Output Device Section
device_lf = ttk.LabelFrame(gain_output_tab, text="Output Device", padding=10)
device_lf.pack(fill=tk.X)

# Local handler for main combobox
def _on_main_output_device_change(event):
    disp = main_output_device_combobox.get()
    did = main_output_device_combobox._device_map.get(disp, disp)
    config["output_device"] = did
    save_config(config)
    update_output_device(did)
    # Use fast path instead of full service restart: write config to /tmp/sox_device.conf
    # The shell monitoring (Option B) will detect the change and switch devices in <100ms
    threading.Thread(target=write_device_conf, args=(did,), daemon=True).start()

# Ensure the main output combobox is defined and bound
try:
    main_output_device_combobox
except NameError:
    main_output_device_var = tk.StringVar()
    main_output_device_frame = ttk.Frame(device_lf)
    main_output_device_frame.pack(pady=5, fill=tk.X)
    ttk.Label(main_output_device_frame, text="Device:").pack(side=tk.LEFT, padx=(0,6))
    main_output_device_combobox = ttk.Combobox(main_output_device_frame, textvariable=main_output_device_var, values=[], state="readonly", width=25)
    main_output_device_combobox.pack(side=tk.LEFT, padx=(0,6))
    refresh_btn = ttk.Button(main_output_device_frame, text="Refresh", command=lambda: _refresh_main_output_devices())
    refresh_btn.pack(side=tk.LEFT)
    def _refresh_main_output_devices():
        devices = [("BlueALSA","bluealsa")]
        cardnum = ""
        try:
            res = subprocess.run(["aplay","-l"], capture_output=True, text=True)
            for m in re.finditer(r'(?:card|カード)\s+(\d+):', res.stdout, re.IGNORECASE):
                start = m.end()
                next_m = re.search(r'(?:card|カード)\s+\d+:', res.stdout[start:], re.IGNORECASE)
                end = start + (next_m.start() if next_m else len(res.stdout) - start)
                block = res.stdout[start:end]
                if re.search(r'USB', block, re.IGNORECASE):
                    cardnum = m.group(1)
                    break
        except Exception:
            cardnum = ""
        if cardnum:
            devices.append((f"USB-DAC (hw:{cardnum})", f"hw:{cardnum}"))
        else:
            devices.append(("USB-DAC (not connected)", "USB-DAC"))
        devices.append(("HDMI (hw:0,3)", "hw:0,3"))
        devices.append(("PC Speakers (hw:0,0)", "hw:0,0"))
        display_names = [d[0] for d in devices]
        main_output_device_combobox['values'] = display_names
        main_output_device_combobox._device_map = {d[0]: d[1] for d in devices}
        cur_id = config.get("output_device", "")
        selected = None
        for disp, did in main_output_device_combobox._device_map.items():
            if did == cur_id or (isinstance(cur_id, str) and cur_id in disp):
                selected = disp
                break
        if not selected:
            selected = display_names[0] if display_names else ''
        main_output_device_combobox.set(selected)
    # initialize
    _refresh_main_output_devices()

main_output_device_combobox.bind("<<ComboboxSelected>>", _on_main_output_device_change)
# Backwards compatibility: if an old/minimal output combobox exists, bind it too so selection immediately applies
try:
    output_device_cb
    output_device_cb.bind("<<ComboboxSelected>>", lambda e: _on_main_output_device_change(e))
except NameError:
    pass
# The output device selection remains available in the preset edit dialog.



# --- 適用ボタン ---
apply_button_frame = ttk.Frame(left_frame, padding="5")
apply_button_frame.pack(fill=tk.X, side=tk.BOTTOM)
apply_button = ttk.Button(apply_button_frame, text="設定を適用", command=apply_settings)
apply_button.pack(expand=True, fill=tk.X)
# Ensure Apply button is visible on top and properly laid out
try:
    apply_button.lift()
    apply_button.update_idletasks()
except Exception:
    pass


# --- 右ペインの内容 ---
# アルバムアート表示
album_art_lf = ttk.LabelFrame(album_art_frame, text="Album Art", padding="5")
album_art_lf.pack(fill=tk.BOTH, expand=True)
# アルバムアート表示用ラベル (初期は空かデフォルト画像)
album_art_label = ttk.Label(album_art_lf, anchor=tk.CENTER)
album_art_label.pack(fill=tk.BOTH, expand=True, anchor=tk.CENTER)
# 初期デフォルト画像読み込み
update_album_art_display(None)

# 現在の設定表示エリア (別ペインに配置して垂直リサイズを復旧)
settings_lf = ttk.LabelFrame(settings_view_frame, text="Current Settings", padding="10")
settings_lf.pack(fill=tk.BOTH, expand=True)
settings_label = ttk.Label(settings_lf, text="", font=status_font, justify=tk.LEFT, anchor=tk.NW)
settings_label.pack(fill=tk.BOTH, expand=True)

# 起動時の位置と比率を復元
root.geometry(config.get("window_geometry", "2000x1500"))

def restore_panes():
    try:
        if "pane_ratio" in config:
            total_width = main_paned_window.winfo_width()
            if total_width > 0:
                main_paned_window.sashpos(0, int(config["pane_ratio"] * total_width))
    except:
        pass

    try:
        if "right_vertical_ratio" in config:
            total_height = right_paned_window.winfo_height()
            if total_height > 0:
                right_paned_window.sashpos(0, int(config["right_vertical_ratio"] * total_height))
    except:
        pass

# 最初にサイズが正しく取得されるタイミングで呼ぶ
root.after(500, restore_panes)

# --- 初期化 ---
update_gui_from_config() # GUIの初期状態を設定ファイルに合わせる
display_settings()      # 下部の設定表示を更新

# MPDポーリング用変数
mpd_client = None
last_song_id = None

def on_closing():
    """ウィンドウを閉じる際に現在のジオメトリとペイン比率を保存する"""
    try:
        config["window_geometry"] = root.geometry()
        
        # メインペイン（左右）の比率
        total_width = main_paned_window.winfo_width()
        if total_width > 0:
            config["pane_ratio"] = main_paned_window.sashpos(0) / total_width
            
        # 右ペイン（上下）の比率
        total_height = right_paned_window.winfo_height()
        if total_height > 0:
            config["right_vertical_ratio"] = right_paned_window.sashpos(0) / total_height
            
        save_config(config)
    except Exception as e:
        logger.error("ウィンドウ状態の保存に失敗しました: %s", e)
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

def update_output_device(device_id):
    """Apply the selected output device: update shell script, save to config and trigger service restart.

    device_id can be 'bluealsa', 'hw:0', or 'hw:X'.
    """
    try:
        # normalize
        did = str(device_id)
        config["output_device"] = did
        # Update shell script so the service picks it up
        update_shell_script(config)
        save_config(config)
        # Restart service to pick up new device
        threading.Thread(target=restart_service, daemon=True).start()
        messagebox.showinfo("情報", f"出力デバイスを {did} に設定し、サービスを再起動しました。")
    except Exception as e:
        logger.exception("出力デバイス適用に失敗しました: %s", e)
        messagebox.showerror("エラー", f"出力デバイスの適用に失敗しました: {e}")

# GUIループ (直接実行時のみ開始する)
if __name__ == "__main__":
    mpd_thread = threading.Thread(target=mpd_poller, daemon=True)
    mpd_thread.start()

    root.mainloop()
