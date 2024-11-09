
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


def clear_mongo():
    Collection.delete_many({})
    print("Cleared MongoDB")

if __name__ == "__main__":
    ui = input("Are you sure you want to clear the database? (y/n): ")
    if ui.lower().strip() in ("y", "yes"):
        clear_mongo()