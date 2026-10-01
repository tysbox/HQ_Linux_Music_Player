"""ISO 226 等ラウドネス補正の CamillaDSP パラメータ変換.

2026-10-02 点検で見つかった既存実装の問題:
    旧実装 (`loudness_enabled` 経路) は CamillaDSP の `Loudness` フィルタを
    使わず、独自モデル `delta = loudness_ref + volume` で Lowshelf/Highshelf を
    生成していた。これは次の欠陥を持つ。

      1. 音量操作と EQ が結合していた
         volume を下げると EQ 曲線が変化するため、老百姓が volume ダイヤルを
         触るたびにトーンが変わる。ラウドネス補正は本来「絶対レベル」基準で
         あるべきで、volume 操作と切り離されている必要がある。
      2. ISO 226 の等ラウドネス曲線ではなく、単なる傾き補正
         低域 +8dB / 高域 +4dB の 2 本の shelf であり、聴感の等ラウドネス
         特性と対応していない。

CamillaDSP 4.1.3 は `Loudness` フィルタを内蔵しており、Fader/Volume の設定値から
補正強度を内部計算する。本モジュールはその正しい利用のための変換のみを担う。

CamillaDSP の仕様 (実機 `camilladsp --check` で検証済み):
    filters:
      iso226:
        type: Loudness
        parameters:
          reference_level: <float>   # 0 <= x < 20
          high_boost: <f32>
          low_boost: <f32>
          fader: Main | Aux1 | Aux2 | Aux3 | Aux4
          attenuate_mid: <bool>

    注意: reference_level は 20 以上で
    "Reference level must be less than 20" により起動失敗する。
    dB SPL を直接渡すことはできないため変換が必要。

GUI が保持する `loudness_ref` は従来どおり dB SPL (60/80/100 程度) を表す。
本モジュールはそれを CamillaDSP の 0-20 域へ写像する。
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# 変換定数
# ─────────────────────────────────────────────────────────────────────────────
#: GUI 側 dB SPL の下限/上限。0 dB SPL は物理的に無音なので下限を 20 とする。
DB_SPL_MIN = 20.0
DB_SPL_MAX = 100.0

#: CamillaDSP Loudness.reference_level の許容域 (両端とも exclusive for 20)
REFERENCE_LEVEL_MIN = 0.0
REFERENCE_LEVEL_MAX = 20.0

#: 補正強度の既定値。
#: 低域を多少強くする点は ISO 226 の低ラウドネス帯の性質に合致し、
#: かつ旧実装 (low 8dB / high 4dB) の低域寄りの印象とも方向が一致する。
DEFAULT_LOW_BOOST = 8.0
DEFAULT_HIGH_BOOST = 4.0

#: Fader 名。CamillaDSP の Fader/Aux 定義のうち Main を使う。
#: `Loudness.fader` は Main/Aux1..Aux4 を参照でき、実機検証済み。
DEFAULT_FADER = "Main"

#: 音量 stage に置く `Volume` フィルタの fader 名。
#: `Volume.fader` も Aux1..Aux4 のみを受け付ける（Main は不可）。
#: Main は音量そのものを担うため、Volume は Aux1 に分離する。
#: Loudness は Main を参照することで、音olume changes を検出する。
VOLUME_FADER = "Aux1"

#: `Volume` フィルタのランプ時間 [s]。既存 DSP 設定の 0.05s に合わせる。
VOLUME_RAMP_TIME = 0.05

#: `Volume.limit` は f32（秒）で指定する（bool は不可）。
VOLUME_LIMIT_SECONDS = 1.0


def build_volume_filter(
    fader: str = VOLUME_FADER,
    ramp_time: float = VOLUME_RAMP_TIME,
    limit: float = VOLUME_LIMIT_SECONDS,
) -> dict:
    """音量 stage の `Volume` フィルタを返す。

    `Loudness` フィルタは Fader の値を参照して補正強度を計算するため、
    音量制御は `Volume` フィルタ (fader=Aux1) として pipeline に置く。
    既存の `set_main_volume` は Fader を直接操作するため Main を使い、
    Volume と役割が重複しないよう分離している。

    Returns:
        filters セクションにそのまま置ける dict
    """
    return {
        "type": "Volume",
        "parameters": {
            "ramp_time": float(ramp_time),
            "fader": fader,
            "limit": float(limit),
        },
    }


def spl_to_reference_level(loudness_ref: float) -> float:
    """GUI の基準ラウドネス [dB SPL] を CamillaDSP の reference_level に変換する。

    線形写像: dB SPL 20 -> 0.0, 60 -> 10.0, 80 -> 15.0, 100 -> 20.0 (上限)。

    CamillaDSP は `reference_level` に対して 20 以上を拒否するため、
    変換結果を必ず 0 <= x <= 20 に収める。丸め誤差で 20.0 を超えるのを
    避けるため 19.999 を上限とする。

    Args:
        loudness_ref: 基準ラウドネス [dB SPL]

    Returns:
        CamillaDSP の reference_level (0 <= x < 20)
    """
    ref = max(DB_SPL_MIN, min(float(loudness_ref), DB_SPL_MAX))
    span = DB_SPL_MAX - DB_SPL_MIN
    level = (ref - DB_SPL_MIN) / span * (REFERENCE_LEVEL_MAX - REFERENCE_LEVEL_MIN)
    # 20.0 ちょうどは CamillaDSP に拒否されるため、余裕を持たせてクランプする
    return min(max(level, REFERENCE_LEVEL_MIN), 19.999)


def build_loudness_filter(
    loudness_ref: float,
    low_boost: float | None = None,
    high_boost: float | None = None,
    fader: str = DEFAULT_FADER,
    attenuate_mid: bool = False,
) -> dict:
    """CamillaDSP `Loudness` フィルタの YAML フィルタ定義を返す。

    Args:
        loudness_ref: 基準ラウドネス [dB SPL] (GUI の値)
        low_boost: 低域補正量 [dB]。None で既定値
        high_boost: 高域補正量 [dB]。None で既定値
        fader: 対象の Fader 名
        attenuate_mid: 中域を減衰するか

    Returns:
        filters セクションにそのまま置ける dict
    """
    return {
        "type": "Loudness",
        "parameters": {
            "reference_level": spl_to_reference_level(loudness_ref),
            "high_boost": DEFAULT_HIGH_BOOST if high_boost is None else float(high_boost),
            "low_boost": DEFAULT_LOW_BOOST if low_boost is None else float(low_boost),
            "fader": fader,
            "attenuate_mid": bool(attenuate_mid),
        },
    }
