"""Download closed historical candles from Bybit's public API (no credentials).

    python -m ml.data.download --symbol BTC/USDT --timeframe 1h --days 1095
"""
import argparse
import asyncio
import time
from pathlib import Path

from ml.data.ohlcv import TIMEFRAME_SECONDS, dataset_path, normalize_ohlcv, save_dataset
from trader.infra.gateway.bybit_gateway import BybitGateway

DEFAULT_ROOT = Path("data/ml/ohlcv")


async def download(symbol: str, timeframe: str, days: int, root: Path) -> Path:
    now_ms = int(time.time() * 1000)
    period_ms = TIMEFRAME_SECONDS[timeframe] * 1000
    # Only candles whose close time is in the past: the forming candle is excluded.
    until_ms = now_ms - period_ms
    since_ms = now_ms - days * 86_400_000
    gateway = BybitGateway(api_key="", api_secret="", is_testnet=False)
    try:
        rows = await gateway.fetch_ohlcv_history(symbol, timeframe, since_ms, until_ms)
    finally:
        await gateway.close()
    rows = [r for r in rows if int(r[0]) + period_ms <= now_ms]
    frame, report = normalize_ohlcv(rows, timeframe)
    path = dataset_path(root, symbol, timeframe)
    digest = save_dataset(frame, path)
    print(f"{symbol} {timeframe}: {report.as_dict()}")
    print(f"saved {path} sha256={digest}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", action="append", required=True)
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=1095)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    for symbol in args.symbol:
        asyncio.run(download(symbol, args.timeframe, args.days, args.root))


if __name__ == "__main__":
    main()
