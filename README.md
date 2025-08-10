# Zomatoo Explorer 🍽️

**Zomatoo Explorer** is an interactive Streamlit dashboard for exploring and analyzing restaurant data stored in MongoDB. Designed for flexibility and ease of use, it automatically detects key fields in your dataset and provides ready-to-use queries and visualizations for restaurant analytics.

---

## Features

- **Plug-and-Play MongoDB Connection:**  
  Easily connect to any MongoDB instance by specifying the URI, database, and collection.

- **Automatic Field Detection:**  
  The app inspects your data and auto-detects fields for restaurant name, locality, events, cost, and ratings—no manual mapping required.

- **Sample Document Preview:**  
  Instantly view a sample document to verify your schema and field names.

- **Prebuilt Analytics & Queries:**  
  Choose from a set of insightful queries:

  - List all restaurant names
  - List unique localities
  - Show restaurants and their event titles
  - Count events by locality (with charts)
  - Top 3 localities by events per restaurant, average cost, and rating

- **Interactive DataFrames & Visualizations:**  
  Results are displayed in interactive tables and charts for easy exploration.

- **MongoDB Query Transparency:**  
  Each query displays the equivalent MongoDB command for learning and reproducibility.

---

## Quick Start

1. **Clone the repository:**

   ```sh
   git clone https://github.com/yourusername/zomatoo-explorer.git
   cd zomatoo-explorer
   ```

2. **Install dependencies:**

   ```sh
   pip install -r requirements.txt
   ```

3. **Start the app:**

   ```sh
   streamlit run app1.py
   ```

4. **Configure your MongoDB connection** in the sidebar and start exploring!

---

## Project Structure

- [`app1.py`](app1.py): Main Streamlit app for data exploration and analytics
- `clean_restaurants_1.json`: Example dataset (import into MongoDB
