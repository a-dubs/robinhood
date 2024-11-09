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

# function to write EstimatedOrderPriceHistoryEntry to MongoDB
def write_to_mongo(data: EstimatedOrderPriceHistoryEntry):
    Collection.insert_one(data.dict())

def clear_mongo():
    Collection.delete_many({})
    print("Cleared MongoDB")


client = CryptoAPITrading()
target_symbols = ["SHIB-USD", "DOGE-USD"]


def fetch_and_record_current_prices():
    for symbol in target_symbols:
        estimated_order_price_history_entry = client.get_current_estimated_price(symbol)
        print(f"Current estimated price for {symbol}")
        pprint(estimated_order_price_history_entry.dict())
        write_to_mongo(estimated_order_price_history_entry)
        # confirm the order is in the database
        # r = Collection.find_one({"symbol": symbol, "timestamp": estimated_order_price_history_entry.timestamp})
        # if not r:
        #     print("Failed to write to mongo")
        #     return

# def main():
#     last_time_fetched = None
#     while True:
#         fetch_and_record_current_prices()
#         # sleep until top of next minute
#         seconds_to_sleep = 60 - datetime.now().second
#         last_time_fetched = datetime.now()

if __name__ == "__main__":
    # main()
    fetch_and_record_current_prices()
