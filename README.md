# polymarket-copycat

This is a bot designed to selectively replicate bets from successful traders on [Polymarket](https://polymarket.com)

It will let you specify a list of traders to follow, along with some filtering criteria (on categories and transaction size), as well as a scaling ratio for your transactions.

## Installation

```sh
git clone https://github.com/Yann-J/polymarket-copycat && cd polymarket-copycat
# Create virtual env to install requirements locally
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

Create a `run.py` with content similar to `run.py.example`, or from the below snippet:

```py
# -*- coding: utf-8 -*-
import asyncio
from polymarket_copy_trading_bot import PolymarketCopyTradingBot

async def main():
    config = {
        "host": "https://clob.polymarket.com",
        "private_key": None,  # Add your private key for actual trading
        "funder_address": None,  # Add if using proxy wallet
        "chain_id": 137,
        "signature_type": 1,
    }

    bot = PolymarketCopyTradingBot(**config)

    bot.add_trader_to_copy(
        trader_address="johnny234",
        copy_percentage=0.08,
        min_copy_amount=50,
        max_copy_amount=400,
        max_daily_copy=1500,
        categories_filter=["Politics"],
        min_trader_amount=150,
    )

    bot.add_trader_to_copy(
        trader_address="jerk-mate",
        copy_percentage=0.05,
        min_copy_amount=30,
        max_copy_amount=200,
        max_daily_copy=800,
        min_trader_amount=120,
    )

    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

```sh
python run.py
```

## Who to follow?

See the [Leaderboard](https://polymarket.com/leaderboard) to get some inspo of who to follow...
