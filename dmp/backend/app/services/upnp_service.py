"""
UPnP ContentDirectory クライアント
対応サーバー:
  - Soundgenic (Twonky)        : 192.168.0.116:9000
  - Asset UPnP: TYSBOX-MAIN    : 192.168.0.153:26125  ← メインライブラリ
  - Asset UPnP: Archive Cands  : 192.168.0.153:26126
  - Asset UPnP: Recent Acq     : 192.168.0.153:26127
  - Asset UPnP: Soundgenic     : 192.168.0.153:26128

【DIDLパーサー修正済み】
  Soundgenicの実レスポンスで確認した正しいnamespace:
  urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

# ── サーバー定義 ──────────────────────────────────────────────
SERVERS: dict[str, dict] = {
    "soundgenic": {
        "name":        "Soundgenic",
        "ip":          "192.168.0.116",
        "port":        9000,
        "control_url": "http://192.168.0.116:9000/dev0/srv1/control",
        "desc_url":    "http://192.168.0.116:9000/dev0/desc.xml",
    },
    "asset": {
        "name":        "Asset UPnP: TYSBOX-MAIN",
        "ip":          "192.168.0.153",
        "port":        26125,
        "control_url": (
            "http://192.168.0.153:26125"
            "/ContentDirectory/46be2c12-b3e5-4e17-0-123456789abc/control.xml"
        ),
        "desc_url":    "http://192.168.0.153:26125/DeviceDescription.xml",
    },
    "asset_archive": {
        "name":        "Asset UPnP: Archive Candidates",
        "ip":          "192.168.0.153",
        "port":        26126,
        "control_url": (
            "http://192.168.0.153:26126"
            "/ContentDirectory/46be2c12-b3e5-4e17-1-123456789abc/control.xml"
        ),
        "desc_url":    "http://192.168.0.153:26126/DeviceDescription.xml",
    },
    "asset_recent": {
        "name":        "Asset UPnP: Recent Aquisitions",
        "ip":          "192.168.0.153",
        "port":        26127,
        "control_url": (
            "http://192.168.0.153:26127"
            "/ContentDirectory/46be2c12-b3e5-4e17-2-123456789abc/control.xml"
        ),
        "desc_url":    "http://192.168.0.153:26127/DeviceDescription.xml",
    },
    "asset_soundgenic": {
        "name":        "Asset UPnP: Soundgenic",
        "ip":          "192.168.0.153",
        "port":        26128,
        "control_url": (
            "http://192.168.0.153:26128"
            "/ContentDirectory/46be2c12-b3e5-4e17-3-123456789abc/control.xml"
        ),
        "desc_url":    "http://192.168.0.153:26128/DeviceDescription.xml",
    },
}

# SOAP テンプレート
_SOAP_BROWSE = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
      <ObjectID>{object_id}</ObjectID>
      <BrowseFlag>{browse_flag}</BrowseFlag>
      <Filter>*</Filter>
      <StartingIndex>{start}</StartingIndex>
      <RequestedCount>{count}</RequestedCount>
      <SortCriteria>{sort}</SortCriteria>
    </u:Browse>
  </s:Body>
</s:Envelope>"""

_SOAP_SEARCH = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
                        s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
    <s:Body>
        <u:Search xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
            <ContainerID>{container_id}</ContainerID>
            <SearchCriteria>{criteria}</SearchCriteria>
            <Filter>*</Filter>
            <StartingIndex>{start}</StartingIndex>
            <RequestedCount>{count}</RequestedCount>
            <SortCriteria></SortCriteria>
        </u:Search>
    </s:Body>
</s:Envelope>"""

# 実際のSoundgenicレスポンスから確認したnamespace
_DIDL_NS  = "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
_DC_NS    = "http://purl.org/dc/elements/1.1/"
_UPNP_NS  = "urn:schemas-upnp-org:metadata-1-0/upnp/"


def _soap_headers(action: str) -> dict:
    return {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPAction":   f'"urn:schemas-upnp-org:service:ContentDirectory:1#{action}"',
    }


def _extract_didl(soap_xml: str) -> str:
    """SOAPレスポンスのResult要素からDIDL-Lite文字列を取得"""
    try:
        root = ET.fromstring(soap_xml)
        for elem in root.iter():
            if elem.tag.endswith("Result") and elem.text:
                return elem.text
    except ET.ParseError as e:
        logger.error(f"SOAP XML パースエラー: {e}")
    return ""


def _parse_didl(didl_xml: str) -> list[dict]:
    """
    DIDL-Lite XMLをパースしてコンテナ・トラックのリストを返す。
    Soundgenicの実レスポンスで検証済みのnamespace対応。
    """
    items: list[dict] = []
    if not didl_xml:
        return items
    try:
        root = ET.fromstring(didl_xml)
    except ET.ParseError as e:
        logger.error(f"DIDL-Lite パースエラー: {e}")
        return items

    for elem in root:
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        obj_id = elem.get("id", "")

        def txt(ns: str, tag: str) -> str:
            child = elem.find(f"{{{ns}}}{tag}")
            return (child.text or "").strip() if child is not None and child.text else ""

        title = txt(_DC_NS, "title") or txt(_UPNP_NS, "title") or obj_id

        if local == "container":
            items.append({
                "type":        "container",
                "id":          obj_id,
                "title":       title,
                "child_count": elem.get("childCount", "?"),
            })
        elif local == "item":
            artist = txt(_UPNP_NS, "artist") or txt(_DC_NS, "creator") or "Unknown Artist"
            album  = txt(_UPNP_NS, "album") or "Unknown Album"
            track_num_str = txt(_UPNP_NS, "originalTrackNumber")
            track_num = int(track_num_str) if track_num_str.isdigit() else None

            # res要素からURI・duration・アートURL取得
            uri = None
            duration = None
            art_uri  = None

            for res in elem.findall(f"{{{_DIDL_NS}}}res"):
                if uri is None and res.text and res.text.startswith("http"):
                    uri = res.text.strip()
                    d_str = res.get("duration", "")
                    if d_str:
                        try:
                            parts = d_str.split(":")
                            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                            duration = int(h * 3600 + m * 60 + s)
                        except Exception:
                            pass

            for art in elem.findall(f"{{{_UPNP_NS}}}albumArtURI"):
                if art.text:
                    art_uri = art.text.strip()
                    break

            if uri:
                items.append({
                    "type":         "item",
                    "id":           obj_id,
                    "title":        title,
                    "artist":       artist,
                    "album":        album,
                    "track_number": track_num,
                    "duration":     duration,
                    "uri":          uri,
                    "artwork_url":  art_uri,
                })
    return items


async def _soap_request(control_url: str, action: str, body: str, timeout: int = 4) -> str:
    logger.debug(f"SOAP Request -> {control_url} action={action}")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            control_url,
            headers=_soap_headers(action),
            data=body.encode("utf-8"),
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            resp.raise_for_status()
            return await resp.text()


def _build_search_criteria_variants(query: str, extended: bool = False) -> list[str]:
    """UPnP SearchCriteria文字列のリストを返す。
    extended=Trueの場合は追加バリアントも含む（Assetサーバー向け）。
    """
    q = (query or "").strip()
    if not q:
        return []
    q_esc = q.replace('"', '\\"')

    base = [
        f'dc:title contains "{q_esc}" or upnp:artist contains "{q_esc}" or upnp:album contains "{q_esc}"',
        f'dc:title contains "{q_esc}*" or upnp:artist contains "{q_esc}*" or upnp:album contains "{q_esc}*"',
    ]
    if not extended:
        return base

    extra = [
        f'dc:title contains "{q_esc}"',
        f'upnp:artist contains "{q_esc}"',
        f'upnp:album contains "{q_esc}"',
        f'dc:title contains "{q_esc}" or upnp:artist contains "{q_esc}" or upnp:album contains "{q_esc}" or upnp:genre contains "{q_esc}"',
        f'dc:creator contains "{q_esc}" or upnp:artist contains "{q_esc}"',
    ]
    if q_esc.isdigit():
        extra.append(f'upnp:originalTrackNumber = "{q_esc}"')
    return base + extra


# ── 公開API ───────────────────────────────────────────────────

def get_server(server_id: str) -> dict:
    if server_id not in SERVERS:
        raise ValueError(f"不明なサーバーID: {server_id}")
    return SERVERS[server_id]


def _extract_total_matches(soap_xml: str) -> int:
    """SOAPレスポンスのTotalMatches要素から総件数を取得"""
    try:
        root = ET.fromstring(soap_xml)
        for elem in root.iter():
            if elem.tag.endswith("TotalMatches") and elem.text:
                return int(elem.text)
    except Exception:
        pass
    return 0


async def browse(server_id: str, object_id: str = "0",
                 start: int = 0, count: int = 200) -> list[dict]:
    server = get_server(server_id)

    # 1回目のリクエストで総件数を確認し、全件を取得する
    body = _SOAP_BROWSE.format(
        object_id=object_id,
        browse_flag="BrowseDirectChildren",
        start=0, count=200, sort="",
    )
    resp = await _soap_request(server["control_url"], "Browse", body)
    items = _parse_didl(_extract_didl(resp))
    total = _extract_total_matches(resp)

    # 200件より多い場合は残りをページネーションで全件取得
    if total > len(items):
        offset = len(items)
        while offset < total:
            body = _SOAP_BROWSE.format(
                object_id=object_id,
                browse_flag="BrowseDirectChildren",
                start=offset, count=200, sort="",
            )
            try:
                resp = await _soap_request(server["control_url"], "Browse", body)
                page = _parse_didl(_extract_didl(resp))
                if not page:
                    break
                items.extend(page)
                offset += len(page)
            except Exception as e:
                logger.warning(f"Browse pagination failed at offset {offset}: {e}")
                break

    # If no children returned, try an Asset-specific fallback that uses
    # BrowseMetadata + Search heuristics to recover virtual/indexed containers
    if not items and server_id == "asset":
        try:
            # Get metadata for this container (title may encode search hint like "[A..]")
            meta_body = _SOAP_BROWSE.format(
                object_id=object_id,
                browse_flag="BrowseMetadata",
                start=0,
                count=0,
                sort="",
            )
            meta_resp = await _soap_request(server["control_url"], "Browse", meta_body)
            meta_items = _parse_didl(_extract_didl(meta_resp))

            # derive candidate search queries from the container title
            queries: list[str] = []
            if meta_items:
                title = (meta_items[0].get("title") or "").strip()
                import re

                m = re.match(r"^\[([A-Za-z0-9])\.\.\]$", title)
                if m:
                    letter = m.group(1)
                    queries.append(letter)
                    queries.append(letter + "*")
                else:
                    # try stripped title words as fallback
                    stripped = title.strip("[]")
                    if stripped:
                        parts = stripped.split()
                        if parts:
                            queries.append(parts[0])
                        queries.append(stripped)

            # try each candidate by performing a Search scoped to this container
            for q in queries:
                if not q:
                    continue
                try:
                    results = await search(server_id, q, container_id=object_id, start=0, count=200, allow_containers=True)
                    if results:
                        return results
                except Exception:
                    # ignore per-query failures and continue
                    continue
        except Exception as e:
            logger.warning(f"Asset fallback browse/search failed: {e}")

    return items


async def search(server_id: str, query: str, container_id: str = "0",
                 start: int = 0, count: int = 100, allow_containers: bool = False) -> list[dict]:
    server = get_server(server_id)

    is_asset = server_id in ("asset", "asset_archive", "asset_recent", "asset_soundgenic")
    variants = _build_search_criteria_variants(query, extended=is_asset)

    if not variants:
        return []

    # Soundgenic (Twonky) Search takes ~12s to respond; Asset is fast.
    soap_timeout = 4 if is_asset else 15
    # Overall cap: Asset tries multiple variants so allow more time total.
    total_timeout = 30.0 if not is_asset else 20.0

    logger.debug(f"Search ({server_id}, container={container_id}, soap_timeout={soap_timeout}s): {variants}")

    async def _attempt(cid: str) -> list[dict]:
        for criteria in variants:
            body = _SOAP_SEARCH.format(container_id=cid, criteria=criteria, start=start, count=count)
            try:
                resp = await _soap_request(server["control_url"], "Search", body, timeout=soap_timeout)
                parsed = _parse_didl(_extract_didl(resp))
                filtered = parsed if allow_containers else [i for i in parsed if i.get("type") == "item"]
                if filtered:
                    seen: set = set()
                    out: list[dict] = []
                    for it in filtered:
                        ident = it.get("id")
                        if ident in seen:
                            continue
                        seen.add(ident)
                        out.append(it)
                    return out
            except Exception as e:
                logger.debug(f"Search variant failed ({server_id}) cid={cid} criteria={criteria}: {e}")
                continue
        return []

    try:
        async def _full_search() -> list[dict]:
            result = await _attempt(container_id)
            if result:
                return result
            if container_id != "0":
                result = await _attempt("0")
                if result:
                    return result
            return []
        return await asyncio.wait_for(_full_search(), timeout=total_timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Search timed out ({server_id}) after {total_timeout}s")
        return []
    except Exception as e:
        logger.warning(f"Search failed ({server_id}): {e}")
        return []


async def is_reachable(server_id: str) -> bool:
    server = get_server(server_id)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                server["desc_url"],
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def status_all() -> list[dict]:
    """全サーバーの接続状態を一括取得"""
    results = []
    for sid, srv in SERVERS.items():
        reachable = await is_reachable(sid)
        results.append({
            "id":          sid,
            "name":        srv["name"],
            "ip":          srv["ip"],
            "reachable":   reachable,
            "control_url": srv["control_url"],
        })
    return results
