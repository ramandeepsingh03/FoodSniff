# app.py

import os
import streamlit as st
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# ─── Page Setup ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Zomatoo Explorer",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("🍴 Zomatoo Explorer (Self-Detecting Fields)")

# ─── Sidebar: Mongo Connection ────────────────────────────────────────────────
st.sidebar.header("🔌 Connection Settings")
mongo_uri = st.sidebar.text_input(
    "MongoDB URI", 
    value=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
    help="e.g. mongodb://user:pass@host:port"
)
db_name = st.sidebar.text_input("Database name", "zomato")
col_name = st.sidebar.text_input("Collection name", "zomatoo")

@st.cache_resource
def get_client(uri: str):
    return MongoClient(uri)

# Connect & grab a sample
try:
    client = get_client(mongo_uri)
    db = client[db_name]
    coll = db[col_name]
    total = coll.count_documents({})
    st.sidebar.success(f"Connected! {total} docs found")
    sample = coll.find_one()
    if not sample:
        st.sidebar.error("Collection is empty.")
        st.stop()
except PyMongoError as e:
    st.sidebar.error(f"Connection failed:\n{e}")
    st.stop()

# ─── Show sample so you can verify field names ────────────────────────────────
with st.expander("🔍 Sample document"):
    st.json(sample)

# ─── Auto-detect your key fields ───────────────────────────────────────────────
# Restaurant name
if "name" in sample:
    name_field = "name"
elif "restaurant_name" in sample:
    name_field = "restaurant_name"
else:
    name_field = next((k for k,v in sample.items() if isinstance(v,str)), None)
    st.sidebar.warning(f"Using '{name_field}' as restaurant-name field")

# Locality path
if sample.get("location",{}).get("locality") is not None:
    locality_path = "location.locality"
else:
    locality_path = None
    for k,v in sample.items():
        if isinstance(v,dict) and "locality" in v:
            locality_path = f"{k}.locality"
            break
    st.sidebar.warning(f"Using '{locality_path}' as locality path")

# Events array
if "zomato_events" in sample:
    events_field = "zomato_events"
else:
    events_field = next((k for k,v in sample.items() if isinstance(v,list)), None)
    st.sidebar.warning(f"Using '{events_field}' as events array")

# Cost for two
if "average_cost_for_two" in sample:
    cost_field = "average_cost_for_two"
else:
    cost_field = None
    st.sidebar.warning("Cannot find 'average_cost_for_two'; cost metrics will be blank.")

# Rating path
if sample.get("user_rating",{}).get("aggregate_rating") is not None:
    rating_path = "user_rating.aggregate_rating"
else:
    rating_path = None
    st.sidebar.warning("Cannot find 'user_rating.aggregate_rating'; rating metrics will be blank.")

# ─── Pick a query ─────────────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.header("📋 Pick a query")
options = {
    f"1️⃣ Show only `{name_field}`": 1,
    f"2️⃣ List unique `{locality_path}`": 2,
    f"3️⃣ Show `{name_field}` & event titles": 3,
    "4️⃣ Count events by locality": 4,
    "5️⃣ Top 3 localities: events/rest + avg cost + avg rating": 5,
}
choice = st.sidebar.radio("", list(options.keys()))

def show_df(df: pd.DataFrame):
    if df.empty:
        st.warning("No results — check your field names or data.")
    else:
        st.dataframe(df, height=350)

# ─── Query Implementations ────────────────────────────────────────────────────
def q1():
    st.subheader(f"1️⃣ Show only `{name_field}`")
    st.code(f"db.{col_name}.find({{}}, {{ {name_field}:1, _id:0 }})", language="js")
    docs = list(coll.find({}, {name_field:1, "_id":0}))
    df = pd.DataFrame(docs).rename(columns={name_field:"Restaurant"})
    show_df(df)

def q2():
    st.subheader(f"2️⃣ List unique `{locality_path}`")
    st.code(f"db.{col_name}.distinct('{locality_path}')", language="js")
    vals = coll.distinct(locality_path)
    df = pd.DataFrame(vals, columns=["Locality"])
    show_df(df)

def q3():
    st.subheader(f"3️⃣ Show `{name_field}` & event titles")
    st.code(f"""
db.{col_name}.aggregate([
  {{ $match: {{ {events_field}: {{ $exists:true, $ne:[] }} }} }},
  {{ $project: {{ _id:0, {name_field}:1,
      event_titles: {{ $map: {{ input:'${events_field}', as:'e', in:'$$e.event.title' }} }}
  }} }}
]);
""", language="js")
    pipeline = [
        {"$match": {events_field: {"$exists": True, "$ne": []}}},
        {"$project": {
            "_id": 0,
            name_field: 1,
            "event_titles": {
                "$map": {
                    "input": f"${events_field}",
                    "as": "e",
                    "in": "$$e.event.title"
                }
            }
        }}
    ]
    docs = list(coll.aggregate(pipeline))
    df = pd.DataFrame(docs).rename(columns={name_field:"Restaurant"})
    show_df(df)

def q4():
    st.subheader("4️⃣ Count events by locality")
    st.code(f"""
db.{col_name}.aggregate([
  {{ $match: {{ {events_field}: {{ $exists:true, $ne:[] }} }} }},
  {{ $project: {{ locality:'${locality_path}', num_events:{{ $size:'${events_field}' }} }} }},
  {{ $group: {{ _id:'$locality', total_events:{{ $sum:'$num_events' }} }} }},
  {{ $sort:{{ total_events:-1 }} }}
]);
""", language="js")
    pipeline = [
        {"$match": {events_field: {"$exists": True, "$ne": []}}},
        {"$project": {
            "locality": f"${locality_path}",
            "num_events": {"$size": f"${events_field}"}
        }},
        {"$group": {"_id":"$locality", "total_events":{"$sum":"$num_events"}}},
        {"$sort":{"total_events":-1}}
    ]
    df = pd.DataFrame(coll.aggregate(pipeline)).rename(
        columns={"_id":"Locality","total_events":"Total Events"}
    )
    show_df(df)
    if not df.empty:
        st.bar_chart(df.set_index("Locality")["Total Events"])

def q5():
    st.subheader("5️⃣ Top 3 localities by events per restaurant, avg cost, avg rating")
    st.code(f"""
db.{col_name}.aggregate([
  {{ $match: {{ {events_field}: {{ $exists:true, $ne:[] }} }} }},
  {{ $group: {{
      _id: '${locality_path}',
      restaurants_with_events: {{ $sum:1 }},
      total_events: {{ $sum:{{ $size:'${events_field}' }} }},
      avg_cost: {{ $avg:'${cost_field}' }},
      avg_rating: {{ $avg:{{ $toDouble:'${rating_path}' }} }}
  }} }},
  {{ $addFields: {{
      events_per_rest: {{ $divide:['$total_events','$restaurants_with_events'] }}
  }} }},
  {{ $sort: {{ events_per_rest:-1 }} }},
  {{ $limit: 3 }},
  {{ $project: {{
      _id:0,
      Locality:'$_id',
      Restaurants:'$restaurants_with_events',
      TotalEvents:'$total_events',
      EventsPerRestaurant:{{ $round:['$events_per_rest',2] }},
      AvgCost:{{ $round:['$avg_cost',2] }},
      AvgRating:{{ $round:['$avg_rating',2] }}
  }} }}
]);
""", language="js")

    pipeline = [
        {"$match": {events_field: {"$exists": True, "$ne": []}}},
        {"$group": {
            "_id": f"${locality_path}",
            "restaurants_with_events": {"$sum": 1},
            "total_events": {"$sum": {"$size": f"${events_field}"}},
            "avg_cost": {"$avg": f"${cost_field}"},
            "avg_rating": {"$avg": {"$toDouble": f"${rating_path}"}},
        }},
        {"$addFields": {
            "events_per_rest": {
                "$divide": ["$total_events", "$restaurants_with_events"]
            }
        }},
        {"$sort": {"events_per_rest": -1}},
        {"$limit": 3},
        {"$project": {
            "_id": 0,
            "Locality": "$_id",
            "Restaurants": "$restaurants_with_events",
            "Total Events": "$total_events",
            "Events/Restaurant": {"$round": ["$events_per_rest", 2]},
            "Avg Cost for 2": {"$round": ["$avg_cost", 2]},
            "Avg Rating": {"$round": ["$avg_rating", 2]}
        }}
    ]
    df = pd.DataFrame(coll.aggregate(pipeline))
    show_df(df)
    if not df.empty:
        st.bar_chart(df.set_index("Locality")["Events/Restaurant"])

# ─── Dispatch the right query ─────────────────────────────────────────────────
if options[choice] == 1:
    q1()
elif options[choice] == 2:
    q2()
elif options[choice] == 3:
    q3()
elif options[choice] == 4:
    q4()
else:
    q5()


