# 旧クロスフィード・距離・クロストーク打ち消しパラメータ（Stage 1-3 で削除・退避）

**削除日**: 2026-09-19
**削除元**: `backend/dsp/apply_logic.py:22-106`
**理由**: F-2 より呼び出し元ゼロ。`AudioConfig` に角度・距離フィールドが無い。Stage 4 で再設計するため退避。

---

## CROSSFEED_ANGLE_PARAMS

```python
CROSSFEED_ANGLE_PARAMS = {
    "none": {"delay_ms": 0.0, "gain_db": 0.0, "label": "OFF"},
    "15": {"delay_ms": 0.11, "gain_db": -3.0, "label": "15°"},
    "30": {"delay_ms": 0.22, "gain_db": -6.0, "label": "30°"},
    "60": {"delay_ms": 0.44, "gain_db": -10.0, "label": "60°"},
    "90": {"delay_ms": 0.66, "gain_db": -14.0, "label": "90°"},
}
```

## DISTANCE_PARAMS

```python
DISTANCE_PARAMS = {
    0.0: {"label": "0.5m (ニア)", "delay_ms": 1.5, "gain_db": -2.0},
    0.5: {"label": "3m (中間)", "delay_ms": 8.7, "gain_db": -8.0},
    1.0: {"label": "20m (ファー)", "delay_ms": 58.0, "gain_db": -20.0},
}
```

## CROSSTALK_CANCEL_PARAMS

```python
CROSSTALK_CANCEL_PARAMS = {
    "none": {"delay_ms": 0.0,  "gain_db": 0.0,  "label": "OFF", "inverted": False},
    "15":  {"delay_ms": 0.11, "gain_db": -3.0,  "label": "15°", "inverted": True},
    "30":  {"delay_ms": 0.22, "gain_db": -6.0,  "label": "30°", "inverted": True},
    "60":  {"delay_ms": 0.44, "gain_db": -10.0, "label": "60°", "inverted": True},
    "90":  {"delay_ms": 0.66, "gain_db": -14.0, "label": "90°", "inverted": True},
}
```

---

## 削除された関数（呼び出し元なし）

- `compute_crossfeed_params(angle, intensity)` - 角度・強度からパラメータ計算
- `compute_distance_params(distance_ratio)` - 距離比からパラメータ計算
- `apply_crossfeed(config)` - クロスフィード適用（戻り値のみ返す）
- `apply_crosstalk_cancel(config)` - クロストーク打ち消し適用（戻り値のみ返す）

これらは Stage 4（クロスフィード 4経路配線）で Woodworth 近似等の物理ベース計算に置き換えて再実装予定。
