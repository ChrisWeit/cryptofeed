'''
Copyright (C) 2017-2019  Bryant Moscon - bmoscon@gmail.com

Please see the LICENSE file for the terms and conditions
associated with this software.
'''
import asyncio
from decimal import Decimal
import time

from sortedcontainers import SortedDict as sd

from cryptofeed.feed import RestFeed
from cryptofeed.defines import TRADES, BUY, SELL, BID, ASK, TICKER, L2_BOOK, COINBENE
from cryptofeed.standards import pair_exchange_to_std

import aiohttp


class Coinbene(RestFeed):
    id = COINBENE

    def __init__(self, pairs=None, channels=None, callbacks=None, **kwargs):
        super().__init__('http://api.coinbene.com/v1/market/', pairs=pairs, channels=channels, callbacks=callbacks, **kwargs)

    def __reset(self):
        self.last_trade_update = {}

    async def _trades(self, session, pair):
        """
        {
            "status": "ok",
            "timestamp": 1489473538996,
            "symbol": "btcusdt",
            "trades": [{
                "tradeId ": 14894644510000001,
                "price": 4000.00,
                "quantity": 1.0000,
                "take": "buy",
                "time": "2018-03-14 18:36:32"
            }]
        }
        """
        if pair not in self.last_trade_update:
            async with session.get(f"{self.address}trades?symbol={pair}") as response:
                data = await response.json()
                update = {}
                for trade in data['trades']:
                    price = Decimal(trade['price'])
                    amount = Decimal(trade['quantity'])
                    side = BUY if trade['take'] == 'buy' else SELL
                    update[trade['tradeId']] = (price, amount, side, trade['time'])
                self.last_trade_update[pair] = update
        else:
            async with session.get(f"{self.address}trades?symbol={pair}&size=2000") as response:
                data = await response.json()
                update = {}
                for trade in data['trades']:
                    if trade['tradeId'] in self.last_trade_update[pair]:
                        continue
                    price = Decimal(trade['price'])
                    amount = Decimal(trade['quantity'])
                    side = BUY if trade['take'] == 'buy' else SELL
                    update[trade['tradeId']] = (price, amount, side, trade['time'])

                    await self.callbacks[TRADES](feed=self.id,
                                                 pair=pair_exchange_to_std(pair),
                                                 side=side,
                                                 amount=amount,
                                                 price=price,
                                                 order_id=trade['tradeId'],
                                                 timestamp=trade['time'])
                self.last_trade_update[pair] = update

    async def _ticker(self, session, pair):
        """
        {
            "status":"ok",
            "ticker":[
                {
                    "24hrAmt":"1264748.00057000",
                    "24hrHigh":"11709.54000000",
                    "24hrLow":"9200.00000000",
                    "24hrVol":"119.76200000",
                    "ask":"0.81000000",
                    "bid":"0.80000000",
                    "last":"11525.00000000",
                    "symbol":"BTCUSDT"
                }
            ],
            "timestamp":1517536673213
        }
        """
        async with session.get(f"{self.address}ticker?symbol={pair}") as response:
            data = await response.json()
            bid = Decimal(data['ticker'][0]['bid'])
            ask = Decimal(data['ticker'][0]['ask'])
            await self.callbacks[TICKER](feed=self.id,
                                         pair=pair_exchange_to_std(pair),
                                         bid=bid,
                                         ask=ask)

    async def _book(self, session, pair):
        async with session.get("{}orderbook?symbol={}".format(self.address, pair)) as response:
            data = await response.json()

            book = {ASK: sd({
                Decimal(entry['price']): Decimal(entry['quantity']) for entry in data['orderbook']['asks']
            }), BID: sd({
                Decimal(entry['price']): Decimal(entry['quantity']) for entry in data['orderbook']['bids']
            })}

            await self.callbacks[L2_BOOK](feed=self.id,
                                          pair=pair_exchange_to_std(pair),
                                          book=book,
                                          timestamp=data['timestamp'])

    async def subscribe(self):
        self.__reset()
        return

    async def message_handler(self):
        async with aiohttp.ClientSession() as session:
            for chan in self.channels:
                for pair in self.pairs:
                    if chan == TRADES:
                        await self._trades(session, pair)
                    elif chan == TICKER:
                        await self._ticker(session, pair)
                    elif chan == L2_BOOK:
                        await self._book(session, pair)
                    # We can do 15 requests a second
                    await asyncio.sleep(0.07)
