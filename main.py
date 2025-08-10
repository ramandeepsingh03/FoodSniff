# app.py

import os
import streamlit as st
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import plotly.express as px

# ─── Page Configuration ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Zomato Analytics",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Sidebar: Page Navigation ────────────────────────────────────────────────
page = st.sidebar.selectbox("🔍 Select Page", ["Explorer", "Analytics", "About"])

# ─── MongoDB Connection Settings ─────────────────────────────────────────────
if page in ["Explorer", "Analytics"]:
    st.sidebar.header("🔌 Connection Settings")
    mongo_uri = st.sidebar.text_input(
        "MongoDB URI",
        value=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        help="e.g. mongodb://user:pass@host:port"
    )
    db_name = st.sidebar.text_input("Database name", value=os.getenv("DB_NAME", "zomato"))
    col_name = st.sidebar.text_input("Collection name", value=os.getenv("COLLECTION_NAME", "zomatoo"))

    @st.cache_resource
    def get_client(uri: str):
        return MongoClient(uri)

    try:
        client = get_client(mongo_uri)
        db = client[db_name]
        coll = db[col_name]
        total_docs = coll.count_documents({})
        st.sidebar.success(f"Connected! {total_docs} docs found")
    except PyMongoError as e:
        st.sidebar.error(f"Connection failed:\n{e}")
        st.stop()

# ─── Explorer Page ────────────────────────────────────────────────────────────
if page == "Explorer":
    st.title("🍴 Zomatoo Explorer (Self-Detecting Fields)")

    # Sample document viewer
    with st.expander("🔍 Sample document"):
        sample = coll.find_one()
        if not sample:
            st.warning("Collection is empty.")
            st.stop()
        st.json(sample)

    # Auto-detect key fields
    if "name" in sample:
        name_field = "name"
    elif "restaurant_name" in sample:
        name_field = "restaurant_name"
    else:
        name_field = next((k for k, v in sample.items() if isinstance(v, str)), None)
        st.sidebar.warning(f"Using '{name_field}' as restaurant-name field")

    if isinstance(sample.get("location"), dict) and "locality" in sample["location"]:
        locality_path = "location.locality"
    else:
        locality_path = None
        for k, v in sample.items():
            if isinstance(v, dict) and "locality" in v:
                locality_path = f"{k}.locality"
                break
        st.sidebar.warning(f"Using '{locality_path}' as locality path")

    if "zomato_events" in sample:
        events_field = "zomato_events"
    else:
        events_field = next((k for k, v in sample.items() if isinstance(v, list)), None)
        st.sidebar.warning(f"Using '{events_field}' as events array")

    if "average_cost_for_two" in sample:
        cost_field = "average_cost_for_two"
    else:
        cost_field = None
        st.sidebar.warning("Cannot find 'average_cost_for_two'; cost metrics will be blank.")

    if isinstance(sample.get("user_rating"), dict) and "aggregate_rating" in sample["user_rating"]:
        rating_path = "user_rating.aggregate_rating"
    else:
        rating_path = None
        st.sidebar.warning("Cannot find 'user_rating.aggregate_rating'; rating metrics will be blank.")

    # Sidebar: Query selection
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

    # Query implementations
    def q1():
        st.subheader(f"1️⃣ Show only `{name_field}`")
        st.code(f"db.{col_name}.find({{}}, {{ {name_field}:1, _id:0 }})", language="js")
        docs = list(coll.find({}, {name_field: 1, "_id": 0}))
        df = pd.DataFrame(docs).rename(columns={name_field: "Restaurant"})
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
                "event_titles": {"$map": {"input": f"${events_field}", "as": "e", "in": "$$e.event.title"}}
            }}
        ]
        docs = list(coll.aggregate(pipeline))
        df = pd.DataFrame(docs).rename(columns={name_field: "Restaurant"})
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
            {"$project": {"locality": f"${locality_path}", "num_events": {"$size": f"${events_field}"}}},
            {"$group": {"_id": "$locality", "total_events": {"$sum": "$num_events"}}},
            {"$sort": {"total_events": -1}}
        ]
        df = pd.DataFrame(coll.aggregate(pipeline)).rename(columns={"_id": "Locality", "total_events": "Total Events"})
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
  {{ $addFields: {{ events_per_rest: {{ $divide:['$total_events','$restaurants_with_events'] }} }} }},
  {{ $sort: {{ events_per_rest:-1 }} }},
  {{ $limit: 3 }},
  {{ $project: {{
      _id:0,
      Locality:'$_id',
      Restaurants:'$restaurants_with_events',
      Total Events:'$total_events',
      Events/Restaurant:{{ $round:['$events_per_rest',2] }},
      Avg Cost for 2:{{ $round:['$avg_cost',2] }},
      Avg Rating:{{ $round:['$avg_rating',2] }}
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
                "avg_rating": {"$avg": {"$toDouble": f"${rating_path}"}}
            }},
            {"$addFields": {"events_per_rest": {"$divide": ["$total_events", "$restaurants_with_events"]}}},
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

    # Dispatch
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

# ─── Analytics Page ───────────────────────────────────────────────────────────
elif page == "Analytics":
    st.title("🍽️ Restaurant Analytics Dashboard")

    @st.cache_data
    def fetch_total_restaurants():
        return coll.count_documents({})

    @st.cache_data
    def fetch_total_events():
        pipeline = [
            {"$project": {"num_events": {"$size": {"$ifNull": ["$zomato_events", []]}}}},
            {"$group": {"_id": None, "total": {"$sum": "$num_events"}}}
        ]
        res = list(coll.aggregate(pipeline))
        return res[0]["total"] if res else 0

    @st.cache_data
    def fetch_avg_rating():
        pipeline = [
            {"$group": {"_id": None, "avg": {"$avg": {"$toDouble": "$user_rating.aggregate_rating"}}}}
        ]
        res = list(coll.aggregate(pipeline))
        return round(res[0]["avg"], 2) if res else 0

    @st.cache_data
    def fetch_avg_cost():
        pipeline = [
            {"$group": {"_id": None, "avg": {"$avg": {"$toDouble": "$average_cost_for_two"}}}}
        ]
        res = list(coll.aggregate(pipeline))
        return round(res[0]["avg"], 2) if res else 0

    @st.cache_data
    def fetch_event_count_by_area():
        pipeline = [
            {"$match": {"zomato_events": {"$exists": True, "$ne": []}}},
            {"$project": {"area": "$location.locality", "num_events": {"$size": "$zomato_events"}}},
            {"$group": {"_id": "$area", "total_events": {"$sum": "$num_events"}}},
            {"$sort": {"total_events": -1}},
            {"$limit": 10}
        ]
        return pd.DataFrame(coll.aggregate(pipeline))

    @st.cache_data
    def fetch_cuisine_distribution():
        pipeline = [
            {"$unwind": "$cuisines"},
            {"$group": {"_id": "$cuisines", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        return pd.DataFrame(coll.aggregate(pipeline))

    @st.cache_data
    def fetch_restaurant_count_by_area():
        pipeline = [
            {"$group": {"_id": "$location.locality", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        return pd.DataFrame(coll.aggregate(pipeline))

    @st.cache_data
    def fetch_events_by_month():
        pipeline = [
            {"$unwind": "$zomato_events"},
            {"$project": {"month": {"$month": {"$toDate": "$zomato_events.event.start_date"}}}},
            {"$group": {"_id": "$month", "events": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        df = pd.DataFrame(coll.aggregate(pipeline))
        months = [None, "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        df["Month"] = df["_id"].map(lambda m: months[m])
        df["Event Count"] = df["events"]
        return df[["Month", "Event Count"]]

    @st.cache_data
    def fetch_locations():
        docs = coll.find({}, {"location.latitude": 1, "location.longitude": 1})
        df = pd.DataFrame(docs).dropna(subset=["location"])
        df["lat"] = df["location"].apply(lambda x: float(x["latitude"]))
        df["lon"] = df["location"].apply(lambda x: float(x["longitude"]))
        return df[["lat", "lon"]]

    # Display Key Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Restaurants", fetch_total_restaurants())
    c2.metric("Active Events", fetch_total_events())
    c3.metric("Average Rating", fetch_avg_rating())
    c4.metric("Average Cost for Two", f"₹{fetch_avg_cost()}")

    st.markdown("---")

    # Visual Insights Grid
    colA, colB, colC = st.columns(3, gap="large")
    with colA:
        st.subheader("Events by Top Areas")
        figA = px.bar(fetch_event_count_by_area(), x="_id", y="total_events",
                      labels={"_id":"Area","total_events":"Events"})
        st.plotly_chart(figA, use_container_width=True)
    with colB:
        st.subheader("Top 10 Cuisines")
        figB = px.pie(fetch_cuisine_distribution(), names="_id", values="count")
        st.plotly_chart(figB, use_container_width=True)
    with colC:
        st.subheader("Restaurants by Area")
        figC = px.bar(fetch_restaurant_count_by_area(), x="_id", y="count",
                      labels={"_id":"Area","count":"Restaurants"})
        st.plotly_chart(figC, use_container_width=True)

    colD, colE = st.columns(2, gap="large")
    with colD:
        st.subheader("Monthly Event Trends")
        figD = px.line(fetch_events_by_month(), x="Month", y="Event Count", markers=True)
        st.plotly_chart(figD, use_container_width=True)
    with colE:
        st.subheader("Restaurant Map")
        st.map(fetch_locations())

# ─── About Page ───────────────────────────────────────────────────────────────
elif page == "About":
    # ─── About Page ────────────────────────────────────────────────────────
    st.title("📄 About This Project")
    st.markdown(
        """
        Welcome to **Zomatoo Explorer & Analytics** – your one-stop dashboard to 
        explore restaurant data, run ad-hoc MongoDB queries, and visualize key metrics 
        in a clean, interactive UI.
        """
    )

    # Top icons + description
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        st.image("https://img.icons8.com/ios-filled/100/000000/kitchen.png", width=80)
    with col2:
        st.markdown(
            """
            ### What It Does
            - **Explorer**: Self-detects your schema and runs sample queries  
            - **Analytics**: Shows totals, trends and maps with Plotly & Streamlit  
            - **About**: Project metadata, author & mentor info
            """
        )
    with col3:
        st.image("https://img.icons8.com/fluency/96/000000/data-visualization.png", width=80)

    st.markdown("---")

    # Key info as metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("👤 Created by", "Ramandeep Singh")
    c2.metric("🎓 Mentor", "[Your Mentor Name]")
    c3.metric("📅 Built on", "April 2025")

