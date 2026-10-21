"""Info ルータ (Bisen移植 Phase 2 / Step 2-3) — LISTENING WIKI 情報エンジン.

Bisen-DSP-System Android の 3 ソース統合を完全移植:

  MusicBrainz (rank 3) > Discogs (rank 2) > MB Release (rank 1) > Wikipedia (rank 0)

移植元 (対応関係):
  MusicBrainzClient.java  → _mb_*   (searchRecording / getRecordingDetail /
                            getReleaseDetail / url-rels Discogs 抽出)
  WikipediaClient.java    → _wiki_* (fetchArticle: 検索→wikitext infobox→要約 /
                            fetchSummary: アーティスト bio + 非音楽家拒否)
  DiscogsClient.java      → _discogs_* (searchReleases / scoreMatch+levenshtein /
                            normalizeRole / extractCredits)
  MetadataParser.java     → _parse_relations / _parse_infobox_facts /
                            _classify_credits / _sanitize / _normalize_title
  MetadataCoordinator.resolve() → _fetch_credits (Tier 1-5 の逐次統合)

MusicBrainz 運用規約: UA 必須 / 最大 1 req/sec (本ルータは 1.1s 強制)。
Discogs: 未認証 60 req/min / UA 必須 (Bisen と同じ無トークン運用)。
応答は ~/.cache/audiophile/musicbrainz/ に永続キャッシュ (オフライン再利用)。

テスト: tests.unit.test_phase2_info (実 API 叩かず fixture)
"""
import hashlib
import json
import logging
import os
import re
import time
from typing import Optional

import requests
from fastapi import APIRouter, Query

from hq_api.errors import service_unavailable, unprocessable_entity

logger = logging.getLogger(__name__)

router = APIRouter()

MB_BASE = "https://musicbrainz.org/ws/2"
WIKI_HOSTS = ["en.wikipedia.org", "ja.wikipedia.org"]
DISCOGS_BASE = "https://api.discogs.com"

RANK_MB = 3
RANK_DISCOGS = 2
RANK_ALBUM = 1
RANK_WIKI = 0

CACHE_DIR = os.path.expanduser("~/.cache/audiophile/musicbrainz")
CACHE_TTL_SEC = 30 * 24 * 3600
MB_TIMEOUT = 8.0
WIKI_TIMEOUT = 8.0
DISCOGS_TIMEOUT = 10.0
MB_MIN_INTERVAL = 1.1  # MusicBrainz 規約: 最大 1 req/sec + 余裕

_UA_MB = "HQ-Linux-Music-Player/1.0 ( https://github.com/tysbox/HQ_Linux_Music_Player )"
_UA_DISCOGS = "HQ-Linux-Music-Player/1.0 (+https://github.com/tysbox/HQ_Linux_Music_Player)"

_last_mb_request = {"t": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# MetadataParser.java 移植
# ─────────────────────────────────────────────────────────────────────────────
def _sanitize(s: str) -> str:
    """MetadataParser.sanitize — 括弧内・[unknown]・先頭番号・拡張子・MinimServer装飾除去。"""
    if not s:
        return ""
    lower = s.lower()
    if "$" in s or "%" in s or "unknown" in lower or "various" in lower:
        return ""
    s = re.sub(r"(?i)[\(\[].*?[\)\]]", "", s)
    s = re.sub(r"(?i)\[unknown\]", " ", s)
    s = re.sub(r"^[0-9\s.-]+", "", s)
    s = re.sub(r"###\w+$", "", s)
    # 注: Python 3.13 はパターン中段の (?i) を許容しないため flags 引数で指定
    s = re.sub(r"\.(?:dsf|dff|flac|wav|mp3|m4a|aac|ogg|opus)$", "",
               s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def _normalize_title(title: str) -> str:
    """MetadataParser.normalizeTitle — remaster/live/edition 等タグ除去。"""
    if not title:
        return ""
    s = re.sub(r"^[0-9\s.-]+", "", title)
    # Bisen から改善: 閉じ括弧まで確実に消す (旧式 `.*?[\)\]]?` は閉じ残しが発生)
    s = re.sub(
        r"\s*[\(\[-](?:remastered|remaster|live|deluxe|expanded|anniversary|"
        r"special|edition|bonus|version|digital|mono|stereo|\d{4})"
        r"[^\)\]]*[\)\]]*", "", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def _credit_hash(name: str) -> str:
    """MetadataParser.getCreditHash — "Miles Davis" → "davis, m" (重複判定用)。"""
    clean = re.sub(r"\(.*?\)", "", name).strip()
    parts = clean.split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0].lower()
    last = parts[-1]
    first = parts[0]
    return f"{last}, {first[:1] if first else ''}".lower()


def _classify_credits(target: dict, category: str, name: str) -> None:
    """MetadataParser.classifyCredits — ハッシュ重複排除付きクレジット分類。"""
    if not name or target is None:
        return
    existing = target.get(category, "")
    if _credit_hash(name).lower() in existing.lower():
        return
    target[category] = name if not existing else f"{existing}, {name}"


def _parse_relations(detail: dict, target: dict) -> None:
    """MetadataParser.parseRelations — MusicBrainz relations → カテゴリ分類。

    producers / engineers / studios / performers(役割付) / composers
    """
    rels = detail.get("relations") or []
    for rel in rels:
        rtype = (rel.get("type") or "").lower()
        art = rel.get("artist") or {}
        name = art.get("name") or ""
        if not name:
            continue
        if "producer" in rtype:
            _classify_credits(target, "producers", name)
        elif "engineer" in rtype or "mix" in rtype or "mastering" in rtype:
            _classify_credits(target, "engineers", name)
        elif "studio" in rtype or "recorded at" in rtype:
            _classify_credits(target, "studios", name)
        elif ("performer" in rtype or "instrument" in rtype
              or "vocal" in rtype):
            attrs = rel.get("attributes") or []
            role = f" ({attrs[0]})" if attrs else f" ({rtype})"
            _classify_credits(target, "performers", name + role)
        elif "writer" in rtype or "composer" in rtype:
            _classify_credits(target, "composers", name)


def _clean_wiki(s: str) -> str:
    """MetadataParser.cleanWiki — wikimarkup 除去 + 220 文字丸め。"""
    if not s:
        return ""
    s = re.sub(r"\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"'''?", "", s)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"\s*<!--.*?-->\s*", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    brk = s.find("<br")
    if brk > 0:
        s = s[:brk].strip()
    if len(s) > 220:
        s = s[:220].strip() + "..."
    return s


def _fill_infobox(scope: str, field: str, key: str, target: dict) -> None:
    m = re.search(r"\|\s*" + field + r"\s*=\s*(.+)", scope)
    if m:
        val = _clean_wiki(m.group(1).strip())
        if val:
            _classify_credits(target, key, val)


def _parse_infobox_facts(wikitext: str, target: dict) -> None:
    """MetadataParser.parseInfoboxFacts — Wikipedia infobox から制作情報を採掘。"""
    pos = wikitext.find("Infobox album")
    if pos < 0:
        pos = wikitext.find("Infobox musical artist")
    if pos < 0:
        pos = wikitext.find("Infobox")
    scope = wikitext[pos:] if pos >= 0 else wikitext
    _fill_infobox(scope, "producer", "producers", target)
    _fill_infobox(scope, "studio", "studios", target)
    _fill_infobox(scope, "recorded", "recordedAt", target)
    _fill_infobox(scope, "engineer", "engineers", target)
    _fill_infobox(scope, "label", "label", target)
    _fill_infobox(scope, "genre", "genre", target)


def _ranked_merge(target: dict, source: dict, source_rank: int) -> None:
    """MetadataCoordinator.rankedMerge — 高ランクが低ランクを上書き (空値無視)。"""
    if not source:
        return
    for key, incoming in source.items():
        if key.endswith("_rank"):
            continue
        if not isinstance(incoming, str) or not incoming:
            continue
        existing_rank = target.get(key + "_rank", 0)
        if source_rank >= existing_rank:
            target[key] = incoming
            target[key + "_rank"] = source_rank


# ─────────────────────────────────────────────────────────────────────────────
# MusicBrainzClient.java 移植
# ─────────────────────────────────────────────────────────────────────────────
def _mb_rate_limit() -> None:
    wait = MB_MIN_INTERVAL - (time.monotonic() - _last_mb_request["t"])
    if wait > 0:
        time.sleep(wait)
    _last_mb_request["t"] = time.monotonic()


def _mb_get(path: str, params: dict) -> Optional[dict]:
    """MusicBrainz GET (UA + レート制限 + 503 リトライ = fetchWithRetry 相当)。"""
    url = f"{MB_BASE}{path}"
    for attempt in range(3):
        _mb_rate_limit()
        try:
            resp = requests.get(
                url, params=params, headers={"User-Agent": _UA_MB},
                timeout=MB_TIMEOUT)
            if resp.status_code == 503:
                time.sleep(1.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.RequestException as e:
            logger.warning("MusicBrainz fetch failed (%s): %s", url, e)
            return None
    return None


def _mb_search_recording(query: str) -> Optional[dict]:
    """searchRecording — limit=1 (Bisen と同一)。"""
    return _mb_get("/recording", {"query": query, "fmt": "json", "limit": 1})


def _mb_recording_detail(rec_id: str) -> Optional[dict]:
    """getRecordingDetail — Bisen と同一 inc。
    注: inc 名は MusicBrainz 仕様の "artist-rels" 系 (旧実装の誤りを修正)。
    """
    return _mb_get(f"/recording/{rec_id}", {
        "inc": "artist-rels+work-rels+work-level-rels+place-rels+releases",
        "fmt": "json",
    })


def _mb_release_detail(release_id: str) -> Optional[dict]:
    """getReleaseDetail — labels/recordings/url-rels 込み (Bisen と同一)。"""
    return _mb_get(f"/release/{release_id}", {
        "inc": "artist-rels+place-rels+labels+recordings+url-rels",
        "fmt": "json",
    })


def _extract_discogs_ids(entity: dict) -> tuple[Optional[str], Optional[str]]:
    """url-rels から Discogs release id / master id を抽出 (Bisen 準拠)。"""
    release_id = None
    master_id = None
    for rel in entity.get("url-rels") or []:
        rtype = (rel.get("type") or "").lower()
        target = rel.get("target") or ""
        if "discogs" not in rtype:
            continue
        if "discogs.com/release/" in target:
            part = target.split("/release/")[1].split("-")[0]
            if part.isdigit():
                release_id = part
        elif "discogs.com/master/" in target:
            part = target.split("/master/")[1].split("-")[0]
            if part.isdigit():
                master_id = part
    return release_id, master_id


def _mb_search_tiers(clean_artist: str, clean_title: str) -> Optional[dict]:
    """MetadataCoordinator Tier 1 — 3 段階クエリフォールバック。"""
    unknown = (not clean_artist
               or clean_artist.lower() in ("unknown artist", "various artists"))
    artist_clause = "" if unknown else f'artist:"{clean_artist}" AND '
    artist_plain = "" if unknown else f"{clean_artist} "

    search = _mb_search_recording(
        f'{artist_clause}recording:"{clean_title}"')
    if not (search or {}).get("recordings"):
        artist_q = "" if unknown else f"artist:{clean_artist} AND "
        search = _mb_search_recording(f"{artist_q}recording:{clean_title}")
    if not (search or {}).get("recordings"):
        search = _mb_search_recording(f"{artist_plain}{clean_title}".strip())
    recs = (search or {}).get("recordings") or []
    return recs[0] if recs else None


# ─────────────────────────────────────────────────────────────────────────────
# WikipediaClient.java 移植
# ─────────────────────────────────────────────────────────────────────────────
def _wiki_fetch_json(url: str) -> Optional[dict]:
    try:
        resp = requests.get(url, headers={"User-Agent": _UA_MB},
                            timeout=WIKI_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _wiki_fetch_article(query: str, credits: dict) -> Optional[str]:
    """fetchArticle — 記事検索 (en→ja) → wikitext infobox 採掘 → 冒頭要約。"""
    import urllib.parse
    for host in WIKI_HOSTS:
        search_url = (
            f"https://{host}/w/api.php?action=query&format=json&formatversion=2"
            f"&list=search&srlimit=1&srsearch={urllib.parse.quote(query)}")
        s = _wiki_fetch_json(search_url)
        if not s:
            continue
        hits = (s.get("query") or {}).get("search") or []
        if not hits:
            continue
        page_title = hits[0].get("title", "")
        if not page_title:
            continue

        # infobox 採掘 (制作事実)
        parse_url = (
            f"https://{host}/w/api.php?action=parse&format=json&formatversion=2"
            f"&prop=wikitext&redirects=1&page={urllib.parse.quote(page_title)}")
        p = _wiki_fetch_json(parse_url)
        if p:
            wikitext = (p.get("parse") or {}).get("wikitext", "")
            if wikitext:
                _parse_infobox_facts(wikitext, credits)

        # 冒頭要約 (exintro / 420 文字)
        sum_url = (
            f"https://{host}/w/api.php?action=query&format=json&formatversion=2"
            f"&prop=extracts&exintro=1&explaintext=1&redirects=1&exchars=420"
            f"&titles={urllib.parse.quote(page_title)}")
        summ = _wiki_fetch_json(sum_url)
        if summ:
            pages = (summ.get("query") or {}).get("pages") or []
            if pages:
                extract = pages[0].get("extract", "")
                if extract:
                    return extract.strip()
    return None


_NON_MUSICIAN_KEYWORDS = [
    "politician", "member of parliament", "congress", "senator", "mayor",
    "governor", "footballer", "soccer", "baseball", "basketball", "athlete",
    "olympic", "actor", "actress", "film", "movie", "television", "tv series",
    "author", "writer", "novelist", "poet", "scientist", "professor",
    "researcher", "businessman", "entrepreneur", "ceo", "executive",
]

_MUSICIAN_KEYWORDS = [
    "musician", "singer", "composer", "pianist", "guitarist", "violinist",
    "band", "album", "song", "record", "music", "jazz", "classical",
    "orchestra", "concert", "perform", "vocals", "instrumental",
    "songwriter", "producer", "arranger", "conductor",
]


def _is_non_musician(snippet: str, title: str) -> bool:
    text = f"{snippet} {title}".lower()
    return any(kw in text for kw in _NON_MUSICIAN_KEYWORDS)


def _is_musician_bio(extract: str) -> bool:
    text = extract.lower()
    return sum(1 for kw in _MUSICIAN_KEYWORDS if kw in text) >= 2


def _wiki_fetch_summary(artist_name: str) -> Optional[str]:
    """fetchSummary — アーティスト bio (バリエーション検索 + 非音楽家拒否)。"""
    import urllib.parse
    subject = artist_name
    variants = [artist_name]
    for suffix in (" musician", " band", " singer"):
        variants.append(artist_name + suffix)
    for variant in variants:
        for host in WIKI_HOSTS:
            search_url = (
                f"https://{host}/w/api.php?action=query&format=json"
                f"&formatversion=2&list=search&srlimit=1"
                f"&srsearch={urllib.parse.quote(variant)}")
            s = _wiki_fetch_json(search_url)
            if not s:
                continue
            hits = (s.get("query") or {}).get("search") or []
            if not hits:
                continue
            page_title = hits[0].get("title", "")
            if not page_title or _is_non_musician(
                    hits[0].get("snippet", ""), page_title):
                continue
            sum_url = (
                f"https://{host}/w/api.php?action=query&format=json"
                f"&formatversion=2&prop=extracts&exintro=1&explaintext=1"
                f"&redirects=1&exchars=420"
                f"&titles={urllib.parse.quote(page_title)}")
            summ = _wiki_fetch_json(sum_url)
            if not summ:
                continue
            pages = (summ.get("query") or {}).get("pages") or []
            if pages:
                extract = pages[0].get("extract", "")
                if extract and _is_musician_bio(extract):
                    return extract.strip()
    del subject
    return None


# ─────────────────────────────────────────────────────────────────────────────
# DiscogsClient.java 移植
# ─────────────────────────────────────────────────────────────────────────────
def _discogs_get(path: str, params: dict = None) -> Optional[dict]:
    try:
        resp = requests.get(
            f"{DISCOGS_BASE}{path}", params=params or {},
            headers={"User-Agent": _UA_DISCOGS,
                     "Accept": "application/json"},
            timeout=DISCOGS_TIMEOUT)
        if resp.status_code == 429:
            logger.warning("Discogs rate limited (429)")
            return None
        if resp.status_code >= 400:
            return None
        return resp.json()
    except Exception as e:
        logger.warning("Discogs fetch failed: %s", e)
        return None


def _discogs_normalize_role(role: str) -> str:
    """DiscogsClient.normalizeRole — 役割名 → 標準キー。"""
    if not role:
        return "other"
    r = role.lower().strip()
    if "producer" in r or "production" in r:
        return "producer"
    if "engineer" in r:
        return "engineer"
    # Bisen から改善: "Mixed By" (Discogs 定番役割) を拾う
    # (Bisen は "mix "/"mixing" のみで "mixed" を取りこぼしていた)
    if "mixing" in r or "mix " in r or "mixed" in r:
        return "mixing_engineer"
    if "mastering" in r or "master " in r:
        return "mastering_engineer"
    if "recording" in r:
        return "recording_engineer"
    if "arranger" in r:
        return "arranger"
    if "composer" in r:
        return "composer"
    if "lyricist" in r or "lyrics" in r:
        return "lyricist"
    if "conductor" in r:
        return "conductor"
    if "vocals" in r or "vocal" in r:
        return "vocals"
    if "guitar" in r:
        return "guitar"
    if "bass" in r:
        return "bass"
    if "drums" in r or "drummer" in r:
        return "drums"
    if "piano" in r or "keyboard" in r:
        return "keyboards"
    if "sax" in r:
        return "saxophone"
    if "trumpet" in r:
        return "trumpet"
    # Bisen WikiModal が表示する行 (violin / cello) を含む役割も拾う
    if "violin" in r:
        return "violin"
    if "cello" in r:
        return "cello"
    if "photography" in r or "photo" in r:
        return "photography"
    if "design" in r or "artwork" in r or "art " in r:
        return "artwork"
    if "management" in r or "manager" in r:
        return "management"
    if "a&r" in r or "a and r" in r:
        return "a_and_r"
    return "other"


def _discogs_extract_credits(release: dict) -> dict:
    """DiscogsClient.extractCredits — release/master → credits 辞書。"""
    credits: dict = {}
    if not release:
        return credits
    try:
        role_map: dict = {}
        for art in release.get("extraartists") or []:
            name = art.get("name", "")
            role = art.get("role", "")
            anv = art.get("anv", "")
            if not name:
                continue
            display = anv if not anv else f"{anv} ({name})"
            if not anv:
                display = name
            standard = _discogs_normalize_role(role)
            role_map.setdefault(standard, []).append(display)
        for key, names in role_map.items():
            credits[key] = "; ".join(names)

        # 主要アーティスト
        main_artists = []
        for a in release.get("artists") or []:
            name = a.get("name", "")
            anv = a.get("anv", "")
            if name:
                main_artists.append(f"{anv} ({name})" if anv else name)
        if main_artists:
            credits["artist"] = ", ".join(main_artists)

        # レーベル (catno 付)
        label_names = []
        for l in release.get("labels") or []:
            name = l.get("name", "")
            catno = l.get("catno", "")
            if name:
                label_names.append(f"{name} ({catno})" if catno else name)
        if label_names:
            credits["label"] = "; ".join(label_names)

        # フォーマット (vinyl / CD 等)
        formats = []
        for f in release.get("formats") or []:
            name = f.get("name", "")
            desc = f.get("descriptions") or []
            if name:
                formats.append(f"{name} ({', '.join(desc)})" if desc else name)
        if formats:
            credits["format"] = "; ".join(formats)

        if release.get("genres"):
            credits["genre"] = ", ".join(release["genres"])
        if release.get("styles"):
            credits["style"] = ", ".join(release["styles"])
        year = release.get("year") or 0
        if year > 0:
            credits["year"] = str(year)
        if release.get("country"):
            credits["country"] = release["country"]
        if release.get("notes"):
            credits["notes"] = release["notes"]
        if release.get("master_id"):
            credits["master_id"] = str(release["master_id"])
        if release.get("id"):
            credits["discogs_release_id"] = str(release["id"])
        if release.get("uri"):
            credits["discogs_uri"] = release["uri"]
    except Exception as e:
        logger.warning("extract_credits failed: %s", e)
    return credits


def _levenshtein(a: str, b: str) -> int:
    """DiscogsClient.levenshtein — 単純レーベンシュタイン距離。"""
    if not a or not b:
        return 10 ** 9
    costs = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        costs[0] = i
        nw = i - 1
        for j in range(1, len(b) + 1):
            cj = min(1 + min(costs[j], costs[j - 1]),
                     nw if a[i - 1] == b[j - 1] else nw + 1)
            nw = costs[j]
            costs[j] = cj
    return costs[len(b)]


def _discogs_score_match(r: dict, target_artist: str,
                         target_title: str, target_album: str) -> int:
    """DiscogsClient.scoreMatch — artist 40/30 + title 40/25 + album 20 + master 10 + year 5。"""
    score = 0
    ra = (r.get("artist") or "").lower()
    rt = (r.get("title") or "").lower()
    ta = target_artist.lower()
    tt = target_title.lower()
    if ta in ra or ra in ta:
        score += 40
    elif _levenshtein(ra, ta) <= 2:
        score += 30
    if tt in rt or rt in tt:
        score += 40
    elif _levenshtein(rt, tt) <= 3:
        score += 25
    if target_album:
        talb = target_album.lower()
        if talb in rt or rt in talb:
            score += 20
    if r.get("master_id"):
        score += 10
    year = r.get("year") or 0
    if 1950 <= year <= 2030:
        score += 5
    return score


def _discogs_find_best_match_credits(artist: str, title: str,
                                      album: str) -> dict:
    """findBestMatchCredits — 検索 → スコアリング (閾値 50) → master 優先。"""
    import urllib.parse
    q = " ".join(x for x in (artist, title, album) if x)
    data = _discogs_get("/database/search", {
        "q": q, "type": "release", "per_page": 20})
    results = (data or {}).get("results") or []
    if not results:
        return {}
    best = None
    best_score = -1
    for r in results:
        s = _discogs_score_match(r, artist, title, album)
        if s > best_score:
            best_score = s
            best = r
    if not best or best_score < 50:
        return {}
    detail = None
    master_id = str(best.get("master_id") or "")
    if master_id and master_id != "0":
        detail = _discogs_get(f"/masters/{master_id}")
    if not detail:
        rid = str(best.get("id") or "")
        if rid:
            detail = _discogs_get(f"/releases/{rid}")
    return _discogs_extract_credits(detail or {})


# ─────────────────────────────────────────────────────────────────────────────
# MetadataCoordinator.resolve() 移植 — Tier 1-5 逐次統合
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_credits(artist: str, title: str, album: str = "",
                    duration_sec: float = 0.0) -> dict:
    """Bisen resolve() の完全移植。credits 辞書を返す。"""
    clean_artist = _sanitize(artist)
    clean_title = _sanitize(title)

    unknown = (not clean_artist
               or clean_artist.lower() in ("unknown artist", "various artists"))
    id_like_title = (not clean_title or "$" in title or "%" in title
                     or bool(re.match(r"^[a-zA-Z][0-9]$", clean_title)))

    if id_like_title and unknown:
        return {"status": "not_found", "credits": {}}

    # Tier 1: MB recording search (3 段階) + 信頼性判定
    rec = _mb_search_tiers(clean_artist, clean_title)
    knowledge: dict = {}
    album_title = album or ""
    artist_name = artist
    release_id = ""
    track_length_ms = 0
    release_data: Optional[dict] = None

    if rec:
        len_ms = rec.get("length") or 0
        credible = (not id_like_title) and (
            len_ms <= 0 or duration_sec <= 0
            or abs(len_ms / 1000.0 - duration_sec)
            <= max(duration_sec * 0.10, 15.0))
        if credible:
            knowledge["trackTitle"] = rec.get("title", "")
            track_length_ms = len_ms
            try:
                art = rec["artist-credit"][0]["artist"]
                found = art.get("name", "")
                if found and found.lower() != "[unknown]":
                    artist_name = found
                    knowledge["artistName"] = artist_name
            except Exception:
                pass
            # Tier 2: recording detail (relations)
            rec_id = rec.get("id", "")
            if rec_id:
                detail = _mb_recording_detail(rec_id)
                if detail:
                    track_data: dict = {}
                    _parse_relations(detail, track_data)
                    _ranked_merge(knowledge, track_data, RANK_MB)
                    rs = detail.get("releases") or []
                    if rs:
                        release_id = rs[0].get("id", "")
        elif unknown:
            try:
                art = rec["artist-credit"][0]["artist"]
                found = art.get("name", "")
                if found and found.lower() != "[unknown]":
                    artist_name = found
                    knowledge["artistName"] = artist_name
            except Exception:
                pass

    knowledge.setdefault("artistName", artist_name)

    # Tier 3: MB release detail (producers / studios / label / 日付)
    if release_id:
        rel = _mb_release_detail(release_id)
        if rel:
            release_data = rel
            if rel.get("title"):
                album_title = rel["title"]
                knowledge["albumTitle"] = album_title
            album_data: dict = {}
            _parse_relations(rel, album_data)
            _ranked_merge(knowledge, album_data, RANK_ALBUM)
            li = rel.get("label-info") or []
            if li and (li[0].get("label") or {}).get("name"):
                knowledge["label"] = li[0]["label"]["name"]
            if rel.get("date"):
                knowledge["releaseDate"] = rel["date"]
            if rel.get("country"):
                knowledge["releaseCountry"] = rel["country"]

    # Tier 4: Wikipedia (infobox 採掘 rank 0 / wikiSummary / artistBio)
    try:
        aq = (f"{clean_title} {artist_name}" if not album_title
              else f"{album_title} {artist_name} album")
        wiki_credits: dict = {}
        summary = _wiki_fetch_article(aq, wiki_credits)
        _ranked_merge(knowledge, wiki_credits, RANK_WIKI)
        if summary:
            knowledge["wikiSummary"] = summary
        if not unknown and artist_name:
            bio = _wiki_fetch_summary(artist_name)
            if bio:
                knowledge["artistBio"] = bio
    except Exception as e:
        logger.warning("Wikipedia enrichment failed: %s", e)

    # Tier 5: Discogs (MB→Discogs 権威リンク優先 / 無ければ fuzzy)
    try:
        a = knowledge.get("artistName", artist_name)
        t = knowledge.get("trackTitle", clean_title)
        alb = knowledge.get("albumTitle", album_title)
        if a and t:
            discogs_release_id = discogs_master_id = None
            if release_data:
                discogs_release_id, discogs_master_id = \
                    _extract_discogs_ids(release_data)
            disc_credits: dict = {}
            if discogs_release_id or discogs_master_id:
                detail = None
                if discogs_master_id and discogs_master_id != "0":
                    detail = _discogs_get(f"/masters/{discogs_master_id}")
                if not detail and discogs_release_id:
                    detail = _discogs_get(f"/releases/{discogs_release_id}")
                disc_credits = _discogs_extract_credits(detail or {})
            else:
                disc_credits = _discogs_find_best_match_credits(a, t, alb)
            _ranked_merge(knowledge, disc_credits, RANK_DISCOGS)
    except Exception as e:
        logger.warning("Discogs enrichment failed: %s", e)

    if track_length_ms:
        knowledge["trackLengthMs"] = track_length_ms

    credits = {k: v for k, v in knowledge.items() if not k.endswith("_rank")}
    if not (credits.get("trackTitle") or credits.get("artistName")
            or credits.get("albumTitle")):
        return {"status": "not_found", "credits": {}}
    return {"status": "success", "credits": credits}


# ─────────────────────────────────────────────────────────────────────────────
# キャッシュ・エンドポイント
# ─────────────────────────────────────────────────────────────────────────────
def _cache_key(artist: str, title: str) -> str:
    raw = f"{artist.strip().lower()}\n{title.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _cache_path(artist: str, title: str) -> str:
    return os.path.join(CACHE_DIR, f"{_cache_key(artist, title)}.json")


def _load_cache(artist: str, title: str, ignore_ttl: bool = False):
    path = _cache_path(artist, title)
    try:
        if not os.path.exists(path):
            return None
        if not ignore_ttl and time.time() - os.path.getmtime(path) > CACHE_TTL_SEC:
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(artist: str, title: str, data: dict) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = _cache_path(artist, title)
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


@router.get("/api/info/credits")
def get_credits(
    artist: str = Query("", description="アーティスト名"),
    title: str = Query("", description="曲名"),
    album: str = Query("", description="アルバム名 (照合精度向上)"),
    duration: float = Query(0, description="再生時間 [秒] (MB 信頼性判定)"),
):
    """LISTENING WIKI 用クレジット取得 (MusicBrainz + Discogs + Wikipedia 統合)。"""
    if not artist.strip() or not title.strip():
        raise unprocessable_entity("artist と title は必須です")

    cached = _load_cache(artist, title)
    if cached is not None:
        cached["cached"] = True
        return cached

    try:
        result = _fetch_credits(artist, title, album, duration)
    except requests.exceptions.Timeout:
        raise service_unavailable("Metadata request timed out")
    except requests.exceptions.RequestException as e:
        logger.warning("Metadata request failed: %s", e)
        stale = _load_cache(artist, title, ignore_ttl=True)
        if stale is not None:
            stale["cached"] = True
            return stale
        raise service_unavailable(f"Metadata sources unreachable: {e}")

    _save_cache(artist, title, result)
    result["cached"] = False
    return result


@router.get("/api/info/file_truth")
def get_file_truth(uri: str = Query("", description="MPD file URI (currentsong の file 値)")):
    """ファイル真理 (追加 Step D-7) — ffprobe によるファイル原本の解析。

    MPD の audio はデコード後の値 (DSD64 は PCM 表記 / MP3 は無意味な
    ビット深度)。ffprobe はコンテナ・ストリームを実際に解析するため、
    ファイル本来のコーデック / 解像度 / ビットレートを返す。

    R-11 対策: ffprobe 未導入・UPnP・ファイル不在は available=False を
    返す (エラーにしない — GUI は当該表示を省略)。
    """
    from hqmplayer_core.meta.filetruth import ffprobe_available, probe_file

    if not ffprobe_available():
        return {"available": False, "reason": "ffprobe_not_installed"}

    if not uri.strip():
        raise unprocessable_entity("uri は必須です")

    truth = probe_file(uri)
    if truth is None:
        # UPnP (http) / ファイル不在 / 解析失敗
        return {"available": False, "reason": "not_a_local_file"}

    return {"available": True, "truth": truth}







