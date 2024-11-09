import base64
import datetime
import json
from typing import Any, Dict, Optional, List
import uuid
import requests
from nacl.signing import SigningKey
from pprint import pprint
from pydantic import BaseModel
from diskcache import Cache
from dotenv import load_dotenv
import os

# setup cache
cache = Cache("cache")

# load environment variables
load_dotenv()

API_KEY = os.getenv("ROBINHOOD_API_KEY")
BASE64_PRIVATE_KEY = os.getenv("ROBINHOOD_BASE64_PRIVATE_KEY")



# make pydantic class for representing a trading pair
# {'asset_code': 'BTC',
# 'asset_increment': '0.000000010000000000',
# 'max_order_size': '20.0000000000000000',
# 'min_order_size': '0.000001000000000000',
# 'quote_code': 'USD',
# 'quote_increment': '0.010000000000000000',
# 'status': 'tradable',
# 'symbol': 'BTC-USD'}]}

class TradingPair(BaseModel):
    asset_code: str
    asset_increment: float
    max_order_size: float
    min_order_size: float
    quote_code: str
    quote_increment: float
    status: str
    symbol: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradingPair":
        return cls(
            asset_code=data["asset_code"],
            asset_increment=float(data["asset_increment"]),
            max_order_size=float(data["max_order_size"]),
            min_order_size=float(data["min_order_size"]),
            quote_code=data["quote_code"],
            quote_increment=float(data["quote_increment"]),
            status=data["status"],
            symbol=data["symbol"],
        )

# make pydantic model for representing bid and ask estimates
# ask:
# [{'symbol': 'SHIB-USD', 'price': '0.00001945', 'quantity': '800', 'side': 'ask', 'ask_inclusive_of_buy_spread':
# '0.00001955', 'buy_spread': '0.00514139', 'timestamp': '2024-11-09T06:16:50.104485455-05:00'}]
# bid:
# [{'symbol': 'SHIB-USD', 'price': '0.00001943', 'quantity': '800', 'side': 'bid', 'bid_inclusive_of_sell_spread': '0.00001933', 'sell_spread': '0.00514668', 'timestamp': '2024-11-09T06:15:05.54552805-05:00'}]

class EstimatedOrderPrice(BaseModel):
    symbol: str
    price: float
    quantity: float
    side: str
    timestamp: datetime.datetime
    price_including_spread: float
    spread: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EstimatedOrderPrice":
        if data["side"] == "bid":
            price_including_spread_key = "bid_inclusive_of_sell_spread"
            spread_key = "sell_spread"
        else:
            price_including_spread_key = "ask_inclusive_of_buy_spread"
            spread_key = "buy_spread"
        return cls(
            symbol=data["symbol"],
            price=float(data["price"]),
            quantity=float(data["quantity"]),
            side=data["side"],
            timestamp=datetime.datetime.fromisoformat(data["timestamp"]),
            price_including_spread=float(data[price_including_spread_key]),
            spread=float(data[spread_key]),
        )

class EstimatedBidAndAskPrice(BaseModel):
    bid: EstimatedOrderPrice
    ask: EstimatedOrderPrice
    timestamp: datetime.datetime

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EstimatedBidAndAskPrice":
        bid = EstimatedOrderPrice.from_dict(data["bid"])
        ask = EstimatedOrderPrice.from_dict(data["ask"])
        # raise error if the timestamps of the bid and ask are not the same
        if bid.timestamp != ask.timestamp:
            raise ValueError("Bid and ask timestamps must match")
        timestamp = bid.timestamp

        return cls(bid=bid, ask=ask, timestamp=timestamp)
    
    @classmethod
    def from_objs(cls, bid: EstimatedOrderPrice, ask: EstimatedOrderPrice) -> "EstimatedBidAndAskPrice":
        if bid.timestamp != ask.timestamp:
            raise ValueError("Bid and ask timestamps must match")
        timestamp = bid.timestamp

        return cls(bid=bid, ask=ask, timestamp=timestamp)

class EstimatedOrderPriceHistoryEntry(BaseModel):
    """
    A flattened version of EstimatedBidAndAskPrice for storing in MongoDB to avoid nested documents
    and make querying easier.
    """
    symbol: str
    bid_price: float
    bid_quantity: float
    bid_side: str
    bid_timestamp: datetime.datetime
    bid_price_including_spread: float
    bid_spread: float
    ask_price: float
    ask_quantity: float
    ask_side: str
    ask_timestamp: datetime.datetime
    ask_price_including_spread: float
    ask_spread: float
    timestamp: datetime.datetime

    @classmethod
    def from_obj(cls, data: EstimatedBidAndAskPrice) -> "EstimatedOrderPriceHistoryEntry":
        return cls(
            symbol=data.bid.symbol,
            bid_price=data.bid.price,
            bid_quantity=data.bid.quantity,
            bid_side=data.bid.side,
            bid_timestamp=data.bid.timestamp,
            bid_price_including_spread=data.bid.price_including_spread,
            bid_spread=data.bid.spread,
            ask_price=data.ask.price,
            ask_quantity=data.ask.quantity,
            ask_side=data.ask.side,
            ask_timestamp=data.ask.timestamp,
            ask_price_including_spread=data.ask.price_including_spread,
            ask_spread=data.ask.spread,
            timestamp=data.timestamp,
        )

    @classmethod
    def from_objs(cls, bid: EstimatedOrderPrice, ask: EstimatedOrderPrice) -> "EstimatedOrderPriceHistoryEntry":
        return cls(
            symbol=bid.symbol,
            bid_price=bid.price,
            bid_quantity=bid.quantity,
            bid_side=bid.side,
            bid_timestamp=bid.timestamp,
            bid_price_including_spread=bid.price_including_spread,
            bid_spread=bid.spread,
            ask_price=ask.price,
            ask_quantity=ask.quantity,
            ask_side=ask.side,
            ask_timestamp=ask.timestamp,
            ask_price_including_spread=ask.price_including_spread,
            ask_spread=ask.spread,
            timestamp=bid.timestamp,
        )

    

class CryptoAPITrading:
    def __init__(self):
        self.api_key = API_KEY
        private_key_seed = base64.b64decode(BASE64_PRIVATE_KEY)
        self.private_key = SigningKey(private_key_seed)
        self.base_url = "https://trading.robinhood.com"

    @staticmethod
    def _get_current_timestamp() -> int:
        return int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())

    @staticmethod
    def get_query_params(key: str, *args: Optional[str]) -> str:
        if not args:
            return ""

        params = []
        for arg in args:
            params.append(f"{key}={arg}")

        return "?" + "&".join(params)

    def make_api_request(self, method: str, path: str, body: str = "") -> Any:
        timestamp = self._get_current_timestamp()
        headers = self.get_authorization_header(method, path, body, timestamp)
        url = self.base_url + path

        try:
            response = {}
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=json.loads(body), timeout=10)
            if response.status_code >= 400:
                print(f"Error making API request: {response.text}")
                return None
            return response.json()
        except requests.RequestException as e:
            print(f"Error making API request: {e}")
            return None

    def get_authorization_header(
            self, method: str, path: str, body: str, timestamp: int
    ) -> Dict[str, str]:
        message_to_sign = f"{self.api_key}{timestamp}{path}{method}{body}"
        signed = self.private_key.sign(message_to_sign.encode("utf-8"))

        return {
            "x-api-key": self.api_key,
            "x-signature": base64.b64encode(signed.signature).decode("utf-8"),
            "x-timestamp": str(timestamp),
        }

    def get_account(self) -> Any:
        path = "/api/v1/crypto/trading/accounts/"
        return self.make_api_request("GET", path)

    # The symbols argument must be formatted in trading pairs, e.g "BTC-USD", "ETH-USD". If no symbols are provided,
    # all supported symbols will be returned
    # use disk cache and cache the results for 1 day
    @cache.memoize(expire=86400)
    def get_trading_pairs(self, *symbols: Optional[str]) -> List[TradingPair]:
        print("Fetching trading pairs")
        query_params = self.get_query_params("symbol", *symbols)
        path = f"/api/v1/crypto/trading/trading_pairs/{query_params}"
        r = self.make_api_request("GET", path)["results"]
        return [TradingPair.from_dict(data) for data in r]

    # The asset_codes argument must be formatted as the short form name for a crypto, e.g "BTC", "ETH". If no asset
    # codes are provided, all crypto holdings will be returned
    def get_holdings(self, *asset_codes: Optional[str]) -> Any:
        query_params = self.get_query_params("asset_code", *asset_codes)
        path = f"/api/v1/crypto/trading/holdings/{query_params}"
        return self.make_api_request("GET", path).get("results")

    # The symbols argument must be formatted in trading pairs, e.g "BTC-USD", "ETH-USD". If no symbols are provided,
    # the best bid and ask for all supported symbols will be returned
    def get_best_bid_ask(self, *symbols: Optional[str]) -> Any:
        query_params = self.get_query_params("symbol", *symbols)
        path = f"/api/v1/crypto/marketdata/best_bid_ask/{query_params}"
        return self.make_api_request("GET", path).get("results")

    # The symbol argument must be formatted in a trading pair, e.g "BTC-USD", "ETH-USD"
    # The side argument must be "bid", "ask", or "both".
    # Multiple quantities can be specified in the quantity argument, e.g. "0.1,1,1.999".
    def get_estimated_price(self, symbol: str, side: str, quantity: str) -> List[EstimatedOrderPrice]:
        path = f"/api/v1/crypto/marketdata/estimated_price/?symbol={symbol}&side={side}&quantity={quantity}"
        r = self.make_api_request("GET", path).get("results")
        return [EstimatedOrderPrice.from_dict(data) for data in r]

    # Function for computing cost of buying a certain quantity of a crypto
    # The symbol argument must be formatted in a trading pair, e.g "BTC-USD", "ETH-USD"
    # The side will always be "bid" for this function
    def get_estimated_bid_price(self, symbol: str, quantity: str) -> EstimatedOrderPrice:
        return self.get_estimated_price(symbol, "bid", quantity)[0]
    
    def get_estimated_ask_price(self, symbol: str, quantity: str) -> EstimatedOrderPrice:
        return self.get_estimated_price(symbol, "ask", quantity)[0]

    def get_quantity_of_crypto(self, symbol: str, price: float) -> float:
        tp = self.get_trading_pairs(symbol)[0]
        r = self.get_estimated_bid_price(symbol, str(tp.min_order_size))
        return price / r.price

    def get_current_estimated_price(self, symbol: str) -> EstimatedOrderPriceHistoryEntry:
        both = self.get_estimated_price(symbol, "both", self.get_trading_pairs(symbol)[0].min_order_size)
        bid = [x for x in both if x.side == "bid"][0]
        ask = [x for x in both if x.side == "ask"][0]
        return EstimatedOrderPriceHistoryEntry.from_objs(bid=bid, ask=ask)

    def place_order(
            self,
            client_order_id: str,
            side: str,
            order_type: str,
            symbol: str,
            order_config: Dict[str, str],
    ) -> Any:
        body = {
            "client_order_id": client_order_id,
            "side": side,
            "type": order_type,
            "symbol": symbol,
            f"{order_type}_order_config": order_config,
        }
        path = "/api/v1/crypto/trading/orders/"
        return self.make_api_request("POST", path, json.dumps(body))

    def cancel_order(self, order_id: str) -> Any:
        path = f"/api/v1/crypto/trading/orders/{order_id}/cancel/"
        return self.make_api_request("POST", path)

    def get_order(self, order_id: str) -> Any:
        path = f"/api/v1/crypto/trading/orders/{order_id}/"
        return self.make_api_request("GET", path)

    def get_orders(self) -> Any:
        path = "/api/v1/crypto/trading/orders/"
        return self.make_api_request("GET", path)

def main():
    client = CryptoAPITrading()
    # tps = client.get_trading_pairs(
    #     "BTC-USD",
    #     "SHIB-USD",
    #     "DOGE-USD",
    # )

    # # for each trading pair, calculate the cost of buying the minimum order size
    # for tp in tps:
    #     cost = client.get_estimated_bid_price(tp.symbol, str(tp.min_order_size))
    #     print(f"Cost of buying {tp.min_order_size} {tp.asset_code} is {cost.price * cost.quantity} {tp.quote_code}")

    #     # how many shares of the crypto can be bought with $1 USD
    #     quantity = client.get_quantity_of_crypto(tp.symbol, 1)
    #     print(f"Can buy {quantity} {tp.asset_code} with $1 USD")


if __name__ == "__main__":
    main()
