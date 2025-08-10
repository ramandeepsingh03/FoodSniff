# ──────────────────────────────────────────────────────────────────────────────
#  app.py – Zomatoo Explorer (10 ready-made queries, self-detecting fields)
# ──────────────────────────────────────────────────────────────────────────────
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
    help="e.g. mongodb://user:pass@host:port",
)
db_name  = st.sidebar.text_input("Database name",    "zomato")
col_name = st.sidebar.text_input("Collection name",  "zomatoo")

@st.cache_resource
def get_client(uri: str):
    return MongoClient(uri)

# Connect & grab a sample
try:
    client = get_client(mongo_uri)
    db    = client[db_name]
    coll  = db[col_name]
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
with st.expander("🔍 Sample document", expanded=False):
    st.json(sample)

# ─── Auto-detect key fields (name/locality/events/cost/rating) ────────────────
if "name" in sample:
    name_field = "name"
elif "restaurant_name" in sample:
    name_field = "restaurant_name"
else:
    name_field = next((k for k, v in sample.items() if isinstance(v, str)), None)
    st.sidebar.warning(f"Using “{name_field}” as restaurant-name field")

if sample.get("location", {}).get("locality") is not None:
    locality_path = "location.locality"
else:
    locality_path = next(
        (f"{k}.locality" for k, v in sample.items() if isinstance(v, dict) and "locality" in v),
        None,
    )
    st.sidebar.warning(f"Using “{locality_path}” as locality path")

events_field = (
    "zomato_events"
    if "zomato_events" in sample
    else next((k for k, v in sample.items() if isinstance(v, list)), None)
)
if events_field != "zomato_events":
    st.sidebar.warning(f"Using “{events_field}” as events array")

cost_field = "average_cost_for_two" if "average_cost_for_two" in sample else None
if not cost_field:
    st.sidebar.warning("Cannot find ‘average_cost_for_two’; cost metrics will be blank.")

rating_path = (
    "user_rating.aggregate_rating"
    if sample.get("user_rating", {}).get("aggregate_rating") is not None
    else None
)
if not rating_path:
    st.sidebar.warning("Cannot find ‘user_rating.aggregate_rating’; rating metrics will be blank.")

# Extra fields for new queries
cuisine_field = "cuisines"
delivery_field = "has_online_delivery"

# ─── Helper to pretty-print DataFrames ────────────────────────────────────────
def show_df(df: pd.DataFrame):
    if df.empty:
        st.warning("No results — check your field names or filters.")
    else:
        st.dataframe(df, height=350, use_container_width=True)

# ─── Query Picker ─────────────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.header("📋 Pick a query")

options = {
    f"1️⃣ Show only “{name_field}”": 1,
    f"2️⃣ List unique “{locality_path}”": 2,
    f"3️⃣ Show “{name_field}” & event titles": 3,
    "4️⃣ Count events by locality": 4,
    "5️⃣ Top 3 localities: events/rest + avg cost + avg rating": 5,
    "6️⃣ Show one sample document": 6,
    "7️⃣ High-rated, budget-friendly spots": 7,
    "8️⃣ Page through restaurants by cost": 8,
    "9️⃣ Continental / Asian OR online-delivery": 9,
    "🔟 Facet: top neighborhoods & cost buckets": 10,
}
choice = st.sidebar.radio(label="", options=list(options.keys()))

# ─── Query Implementations (q1 … q10) ────────────────────────────────────────
def q1():
    st.subheader(f"1️⃣ All restaurants – show only “{name_field}”")
    st.code(f'db.{col_name}.find({{}}, {{ {name_field}:1, _id:0 }})', language="js")
    docs = list(coll.find({}, {name_field: 1, "_id": 0}))
    show_df(pd.DataFrame(docs).rename(columns={name_field: "Restaurant"}))

def q2():
    st.subheader(f"2️⃣ Unique values in “{locality_path}”")
    st.code(f'db.{col_name}.distinct("{locality_path}")', language="js")
    show_df(pd.DataFrame(coll.distinct(locality_path), columns=["Locality"]))

def q3():
    st.subheader(f"3️⃣ “{name_field}” + event titles")
    st.code(
        f"""
db.{col_name}.aggregate([
  {{ $match: {{ {events_field}: {{ $exists:true, $ne:[] }} }} }},
  {{ $project: {{ _id:0, {name_field}:1,
      event_titles: {{
        $map: {{ input:'${events_field}', as:'e', in:'$$e.event.title' }}
      }}
  }} }}
])
""",
        language="js",
    )
    pipeline = [
        {"$match": {events_field: {"$exists": True, "$ne": []}}},
        {
            "$project": {
                "_id": 0,
                name_field: 1,
                "event_titles": {
                    "$map": {"input": f"${events_field}", "as": "e", "in": "$$e.event.title"}
                },
            }
        },
    ]
    show_df(pd.DataFrame(coll.aggregate(pipeline)).rename(columns={name_field: "Restaurant"}))

def q4():
    st.subheader("4️⃣ Count events by locality")
    st.code(
        f"""
db.{col_name}.aggregate([
  {{ $match: {{ {events_field}: {{ $exists:true, $ne:[] }} }} }},
  {{ $project: {{ locality:'${locality_path}',
                 num_events:{{ $size:'${events_field}' }} }} }},
  {{ $group: {{ _id:'$locality', total_events:{{ $sum:'$num_events' }} }} }},
  {{ $sort: {{ total_events:-1 }} }}
])
""",
        language="js",
    )
    pipeline = [
        {"$match": {events_field: {"$exists": True, "$ne": []}}},
        {"$project": {"locality": f"${locality_path}", "num_events": {"$size": f"${events_field}"}}},
        {"$group": {"_id": "$locality", "Total Events": {"$sum": "$num_events"}}},
        {"$sort": {"Total Events": -1}},
    ]
    df = pd.DataFrame(coll.aggregate(pipeline)).rename(columns={"_id": "Locality"})
    show_df(df)
    if not df.empty:
        st.bar_chart(df.set_index("Locality")["Total Events"])

def q5():
    st.subheader("5️⃣ Top 3 localities: events/rest + avg cost + avg rating")
    st.code(
        f"""
db.{col_name}.aggregate([
  {{ $match: {{ {events_field}: {{ $exists:true, $ne:[] }} }} }},
  {{ $group: {{
      _id: '${locality_path}',
      restaurants_with_events: {{ $sum:1 }},
      total_events: {{ $sum:{{ $size:'${events_field}' }} }},
      avg_cost:     {{ $avg:'${cost_field}' }},
      avg_rating:   {{ $avg:{{ $toDouble:'${rating_path}' }} }}
  }} }},
  {{ $addFields: {{
      events_per_rest: {{ $divide:['$total_events','$restaurants_with_events'] }}
  }} }},
  {{ $sort: {{ events_per_rest:-1 }} }}, {{ $limit: 3 }}
])
""",
        language="js",
    )
    pipeline = [
        {"$match": {events_field: {"$exists": True, "$ne": []}}},
        {
            "$group": {
                "_id": f"${locality_path}",
                "Restaurants": {"$sum": 1},
                "Total Events": {"$sum": {"$size": f"${events_field}"}},
                "Avg Cost for 2": {"$avg": f"${cost_field}"},
                "Avg Rating": {"$avg": {"$toDouble": f"${rating_path}"}},
            }
        },
        {"$addFields": {"Events/Restaurant": {"$divide": ["$Total Events", "$Restaurants"]}}},
        {"$sort": {"Events/Restaurant": -1}},
        {"$limit": 3},
    ]
    df = pd.DataFrame(coll.aggregate(pipeline)).rename(columns={"_id": "Locality"})
    show_df(df)
    if not df.empty:
        st.bar_chart(df.set_index("Locality")["Events/Restaurant"])

# ─── NEW QUERIES ──────────────────────────────────────────────────────────────
def q6():
    """Show one raw sample doc (handy when exploring)."""
    st.subheader("6️⃣ A raw sample document")
    st.code(f"db.{col_name}.findOne()", language="js")
    st.json(coll.find_one())

def q7():
    """High-rated & budget-friendly spots with sliders."""
    st.subheader("7️⃣ High-rated, budget-friendly spots")
    min_rating = st.sidebar.slider("⭐ Minimum rating", 0.0, 5.0, 4.0, 0.1)
    max_cost   = st.sidebar.number_input("💸 Max cost for 2", min_value=0, value=1500, step=100)
    query = {
        rating_path: {"$gt": min_rating},
        cost_field:  {"$lte": max_cost},
    }
    st.code(
        f"""
db.{col_name}.find(
  {{ "{rating_path}": {{ $gt: {min_rating} }},
     "{cost_field}":  {{ $lte: {max_cost} }} }},
  {{ {name_field}:1, "{rating_path}":1, {cost_field}:1, _id:0 }}
)
""",
        language="js",
    )
    docs = list(coll.find(query, {name_field: 1, rating_path: 1, cost_field: 1, "_id": 0}))
    df = pd.DataFrame(docs).rename(
        columns={
            name_field: "Restaurant",
            rating_path: "Rating",
            cost_field: "Cost for 2",
        }
    )
    show_df(df)

def q8():
    """Paging through restaurants by cost – user controls skip & limit."""
    st.subheader("8️⃣ Page through restaurants by cost")
    skip  = st.sidebar.number_input("🔢 Skip N docs", 0, value=10, step=5)
    limit = st.sidebar.number_input("📄 Limit", 1, value=5, step=1)
    st.code(
        f"""
db.{col_name}.find({{}},
  {{ {name_field}:1, {cost_field}:1, _id:0 }})
  .sort({{ {cost_field}:1 }})
  .skip({skip})
  .limit({limit})
""",
        language="js",
    )
    docs = list(
        coll.find({}, {name_field: 1, cost_field: 1, "_id": 0})
        .sort(cost_field, 1)
        .skip(skip)
        .limit(limit)
    )
    df = pd.DataFrame(docs).rename(columns={name_field: "Restaurant", cost_field: "Cost for 2"})
    show_df(df)

def q9():
    """Continental or Asian OR online-delivery"""
    st.subheader("9️⃣ Continental / Asian OR online-delivery")
    st.code(
        f"""
db.{col_name}.find(
  {{
    $or: [
      {{ {cuisine_field}: {{ $in: ["Continental","Asian"] }} }},
      {{ {delivery_field}: 1 }}
    ]
  }},
  {{ _id:0, {name_field}:1, {cuisine_field}:1, {delivery_field}:1 }}
)
""",
        language="js",
    )
    query = {
        "$or": [
            {cuisine_field: {"$in": ["Continental", "Asian"]}},
            {delivery_field: 1},
        ]
    }
    proj = {name_field: 1, cuisine_field: 1, delivery_field: 1, "_id": 0}
    df = pd.DataFrame(coll.find(query, proj)).rename(
        columns={name_field: "Restaurant", cuisine_field: "Cuisines", delivery_field: "Delivery?"}
    )
    show_df(df)

def q10():
    """Facet: (a) top neighborhoods by rating & (b) cost buckets."""
    st.subheader("🔟 Facet – top neighborhoods & cost buckets")
    st.code(
        f"""
db.{col_name}.aggregate([
  {{
    $facet: {{
      topNeighborhoods: [
        {{ $group: {{
            _id: "${locality_path}",
            avgRating: {{ $avg: {{ $toDouble: "${rating_path}" }} }},
            count:     {{ $sum: 1 }}
        }} }},
        {{ $match: {{ count: {{ $gte: 5 }} }} }},
        {{ $sort:  {{ avgRating:-1 }} }},
        {{ $limit: 5 }},
        {{ $project: {{ _id:0, locality:"$_id", avgRating:1, count:1 }} }}
      ],
      costBuckets: [
        {{ $bucket: {{
            groupBy: "${cost_field}",
            boundaries:[0,500,1000,1500,2000,3000],
            default:"3000+",
            output: {{
              numRestaurants: {{ $sum: 1 }},
              avgRating:{{ $avg: {{ $toDouble: "${rating_path}" }} }}
            }}
        }} }},
        {{ $project: {{ _id:0, range:"$_id",
                         numRestaurants:1, avgRating:1 }} }}
      ]
    }}
  }}
])
""",
        language="js",
    )
    pipeline = [
        {
            "$facet": {
                "topNeighborhoods": [
                    {
                        "$group": {
                            "_id": f"${locality_path}",
                            "avgRating": {"$avg": {"$toDouble": f"${rating_path}"}},
                            "count": {"$sum": 1},
                        }
                    },
                    {"$match": {"count": {"$gte": 5}}},
                    {"$sort": {"avgRating": -1}},
                    {"$limit": 5},
                    {"$project": {"_id": 0, "Locality": "$_id", "avgRating": 1, "count": 1}},
                ],
                "costBuckets": [
                    {
                        "$bucket": {
                            "groupBy": f"${cost_field}",
                            "boundaries": [0, 500, 1000, 1500, 2000, 3000],
                            "default": "3000+",
                            "output": {
                                "numRestaurants": {"$sum": 1},
                                "avgRating": {"$avg": {"$toDouble": f"${rating_path}"}},
                            },
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "Range": "$_id",
                            "numRestaurants": 1,
                            "avgRating": 1,
                        }
                    },
                ],
            }
        }
    ]
    result = list(coll.aggregate(pipeline))[0]  # single doc with two lists
    left, right = st.columns(2)
    with left:
        st.markdown("**Top Neighborhoods (≥5 restaurants)**")
        df1 = pd.DataFrame(result["topNeighborhoods"])
        show_df(df1)
    with right:
        st.markdown("**Cost Buckets**")
        df2 = pd.DataFrame(result["costBuckets"])
        show_df(df2)

# ─── Dispatcher ───────────────────────────────────────────────────────────────
dispatch = {
    1: q1,
    2: q2,
    3: q3,
    4: q4,
    5: q5,
    6: q6,
    7: q7,
    8: q8,
    9: q9,
    10: q10,
}
dispatch[options[choice]]()
