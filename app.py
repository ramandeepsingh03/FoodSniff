import streamlit as st
import pandas as pd
from pymongo import MongoClient
import plotly.express as px

# ======================
# App Configuration
# ======================
st.set_page_config(
    page_title="Restaurant Analytics Dashboard",
    page_icon="🍽️",
    layout="wide"
)

# ======================
# Database Connection
# ======================
@st.cache_resource
def get_db():
    client = MongoClient("mongodb://localhost:27017/")
    return client['zomato']

@st.cache_resource
def get_collection():
    return get_db()['zomatoo']

# ======================
# Data Fetching Functions
# ======================
@st.cache_data
def fetch_total_restaurants():
    return get_collection().count_documents({})

@st.cache_data
def fetch_total_events():
    pipeline = [
        {"$project": {"num_events": {"$size": {"$ifNull": ["$zomato_events", []]}}}},
        {"$group": {"_id": None, "total": {"$sum": "$num_events"}}}
    ]
    res = list(get_collection().aggregate(pipeline))
    return res[0]['total'] if res else 0

@st.cache_data
def fetch_avg_rating():
    pipeline = [
        {"$group": {"_id": None, "avg": {"$avg": {"$toDouble": "$user_rating.aggregate_rating"}}}}
    ]
    res = list(get_collection().aggregate(pipeline))
    return round(res[0]['avg'], 2) if res else 0

@st.cache_data
def fetch_avg_cost():
    pipeline = [
        {"$group": {"_id": None, "avg": {"$avg": {"$toDouble": "$average_cost_for_two"}}}}
    ]
    res = list(get_collection().aggregate(pipeline))
    return round(res[0]['avg'], 2) if res else 0

@st.cache_data
def fetch_event_count_by_area():
    pipeline = [
        {'$match': {'zomato_events': {'$exists': True, '$ne': []}}},
        {'$project': {'area': '$location.locality', 'num_events': {'$size': '$zomato_events'}}},
        {'$group': {'_id': '$area', 'total_events': {'$sum': '$num_events'}}},
        {'$sort': {'total_events': -1}},
        {'$limit': 10}
    ]
    return pd.DataFrame(get_collection().aggregate(pipeline))

@st.cache_data
def fetch_cuisine_distribution():
    pipeline = [
        {'$unwind': '$cuisines'},
        {'$group': {'_id': '$cuisines', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 10}
    ]
    return pd.DataFrame(get_collection().aggregate(pipeline))

@st.cache_data
def fetch_restaurant_count_by_area():
    pipeline = [
        {'$group': {'_id': '$location.locality', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 10}
    ]
    return pd.DataFrame(get_collection().aggregate(pipeline))

@st.cache_data
def fetch_events_by_month():
    pipeline = [
        {'$unwind': '$zomato_events'},
        {'$project': {'month': {'$month': {'$toDate': '$zomato_events.event.start_date'}}}},
        {'$group': {'_id': '$month', 'events': {'$sum': 1}}},
        {'$sort': {'_id': 1}}
    ]
    df = pd.DataFrame(get_collection().aggregate(pipeline))
    months = [None, 'Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    df['Month'] = df['_id'].map(lambda m: months[m])
    df['Event Count'] = df['events']
    return df[['Month','Event Count']]

@st.cache_data
def fetch_locations():
    docs = get_collection().find({}, {"location.latitude":1,"location.longitude":1})
    df = pd.DataFrame(docs)
    df = df.dropna(subset=['location'])
    df['lat'] = df['location'].apply(lambda x: float(x['latitude']))
    df['lon'] = df['location'].apply(lambda x: float(x['longitude']))
    return df[['lat','lon']]

# ======================
# Dashboard Layout
# ======================
st.title("🍽️ Restaurant Analytics Dashboard")
st.markdown("---")

# Key Metrics Row
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Restaurants", fetch_total_restaurants())
col2.metric("Active Events", fetch_total_events())
col3.metric("Average Rating", fetch_avg_rating())
col4.metric("Average Cost for Two", f"₹{fetch_avg_cost()}")
st.markdown("---")

# Visual Insights Grid
c1, c2, c3 = st.columns(3, gap='large')
with c1:
    st.subheader("Events by Top Areas")
    fig = px.bar(fetch_event_count_by_area(), x='_id', y='total_events', title='Events by Area', labels={'_id':'Area','total_events':'Events'})
    st.plotly_chart(fig, use_container_width=True)
with c2:
    st.subheader("Top 10 Cuisines")
    fig = px.pie(fetch_cuisine_distribution(), names='_id', values='count', title='Cuisine Popularity')
    st.plotly_chart(fig, use_container_width=True)
with c3:
    st.subheader("Restaurants by Area")
    fig = px.bar(fetch_restaurant_count_by_area(), x='_id', y='count', title='Top Areas by Restaurants', labels={'_id':'Area','count':'Restaurants'})
    st.plotly_chart(fig, use_container_width=True)

c4, c5 = st.columns(2, gap='large')
with c4:
    st.subheader("Monthly Event Trends")
    fig = px.line(fetch_events_by_month(), x='Month', y='Event Count', markers=True, title='Events by Month')
    st.plotly_chart(fig, use_container_width=True)
with c5:
    st.subheader("Restaurant Map")
    st.map(fetch_locations())

st.markdown("---")