"""Binance 공개 API — 코인 시세 (키 불필요)."""
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOP_COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]

# api.binance.com 은 일부 리전(미국 등)의 IP를 지역 차단(451)한다 — Streamlit Cloud 서버가
# 그 리전이면 서버사이드 호출이 막힌다. data-api.binance.vision 은 공개 시장데이터 전용 미러로
# 지역 제한이 없어 이를 기본으로 쓰고, 혹시 막히면 api.binance.com 으로 폴백한다.
BASES = ["https://data-api.binance.vision", "https://api.binance.com"]

# 일시적 네트워크/레이트리밋 오류 시 자동 재시도
_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])))


def _get(path, params, timeout):
    """여러 base 를 순서대로 시도 (지역 차단 등으로 하나가 막혀도 다음 것으로 폴백)."""
    last_err = None
    for base in BASES:
        try:
            r = _session.get(f"{base}{path}", params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            last_err = e
    raise last_err


def fetch_klines(symbol="BTCUSDT", interval="1d", limit=365):
    """캔들 조회. limit > 1000 이면 endTime 을 거슬러가며 여러 번 요청해 긴 히스토리를 모은다
    (Binance 는 한 번에 최대 1000개). 상장 이후 데이터가 부족하면 있는 만큼만 반환."""
    limit = min(int(limit), 5000)          # 안전 상한
    if limit <= 1000:
        r = _get("/api/v3/klines",
                 {"symbol": symbol, "interval": interval, "limit": limit}, timeout=20)
        return r.json()

    out = []
    end = None
    while len(out) < limit:
        params = {"symbol": symbol, "interval": interval, "limit": min(1000, limit - len(out))}
        if end is not None:
            params["endTime"] = end
        r = _get("/api/v3/klines", params, timeout=20)
        batch = r.json()
        if not batch:
            break
        out = batch + out                  # 더 오래된 구간을 앞에 붙임
        end = int(batch[0][0]) - 1         # 이번 배치의 첫 캔들보다 더 과거로
        if len(batch) < params["limit"]:
            break                          # 상장 이전 → 더 없음
    return out[-limit:]


def klines_to_df(raw):
    cols = ["open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "tbav", "tbqav", "ignore"]
    df = pd.DataFrame(raw, columns=cols)
    df["date"] = pd.to_datetime(df["open_time"], unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[["date", "open", "high", "low", "close", "volume"]].set_index("date")


def fetch_df(symbol="BTCUSDT", interval="1d", limit=365):
    return klines_to_df(fetch_klines(symbol, interval, limit))


def ticker_24h(symbol="BTCUSDT"):
    r = _get("/api/v3/ticker/24hr", {"symbol": symbol}, timeout=15)
    d = r.json()
    return {
        "symbol": symbol,
        "price": float(d["lastPrice"]),
        "change_pct": float(d["priceChangePercent"]),
        "high": float(d["highPrice"]),
        "low": float(d["lowPrice"]),
        "volume": float(d["volume"]),
    }
