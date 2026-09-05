"""UPnP HTTP トラック用メタデータキャッシュ — 後方互換ランブ.

Phase 1c で実体は hqmplayer_core.meta.cache に統合済み。
既存の `from app.services.meta_cache import store, enrich` などの import パスを
壊さないため、ここで re-export する。

永続化パスは以下のように変更された（マイグレーションは共通モジュール側で実行）:
  - 旧: /tmp/dmp_meta_cache.json
  - 新: ~/.config/hqmplayer/meta_cache.json
"""

from hqmplayer_core.meta import cache_store, cache_enrich


# 旧名との後方互換のためのエイリアス
def store(uri: str, title, artist, album, artwork_url) -> None:
    return cache_store(uri, title, artist, album, artwork_url)


def enrich(song: dict) -> dict:
    return cache_enrich(song)


__all__ = ["store", "enrich"]
