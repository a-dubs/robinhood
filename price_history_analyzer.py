from robinhood import EstimatedOrderPriceHistoryEntry, CryptoAPITrading
from datetime import datetime
from pprint import pprint

# import and setup mongodb
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

# load mongo db username and password from dotenv
from dotenv import load_dotenv
import os
load_dotenv()

client = MongoClient(
    "mongodb://192.168.1.69:27017/", 
    username=os.getenv("MONGO_USERNAME"),
    password=os.getenv("MONGO_PASSWORD")
)

db = client["crypto_trading"]
Collection = db["estimated_order_prices_history"]

# function to read all EstimatedOrderPriceHistoryEntry from MongoDB
def read_price_history() -> dict[str, list[EstimatedOrderPriceHistoryEntry]]:
    price_history = {}
    for entry in Collection.find():
        entry = EstimatedOrderPriceHistoryEntry(**entry)
        if entry.symbol not in price_history:
            price_history[entry.symbol] = []
        price_history[entry.symbol].append(entry)
    return price_history

if __name__ == "__main__":
    price_history = read_price_history()
    pprint(price_history)