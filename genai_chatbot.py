import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import os
from openai import OpenAI

st.set_page_config(page_title="Grocery Inventory AI Assistant", layout="wide")

# Custom page styling
st.markdown(
    """
    <style>
    /* Light main background for readability */
    body, .main {
        background-color: #f3f4f6;
        color: #111827;
    }
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #e5e7eb;
        color: #374151;
        padding: 0.4rem 0.9rem;
        border-radius: 999px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2563eb !important;
        color: white !important;
    }
    /* Keep tables light with dark text */
    .stDataFrame tbody, .stDataFrame thead {
        color: #111827;
    }
    </style>
    """,
    unsafe_allow_html=True,
)









def load_data():
    return pd.read_csv("inventory_optimized.csv")

df = load_data()

# ---------- FILE UPLOAD (ANY TYPE) ----------
uploaded_file = st.file_uploader(
    "Upload a file (CSV, Excel, or text) – optional",
    type=["csv", "xlsx", "xls", "txt"],
    help="Upload a data file to explore or use instead of the default inventory.",
)

user_df = None
raw_text = None

if uploaded_file is not None:
    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        user_df = pd.read_csv(uploaded_file)
        st.success(f"Loaded CSV file: {uploaded_file.name}")
    elif name.endswith((".xlsx", ".xls")):
        user_df = pd.read_excel(uploaded_file)
        st.success(f"Loaded Excel file: {uploaded_file.name}")
    elif name.endswith(".txt"):
        raw_text = uploaded_file.read().decode("utf-8", errors="ignore")
        st.success(f"Loaded text file: {uploaded_file.name}")
    else:
        st.warning("This file type is not handled yet.")

    if user_df is not None:
        st.subheader("Preview of uploaded data")
        st.dataframe(user_df.head(), use_container_width=True)
    elif raw_text is not None:
        st.subheader("Preview of uploaded text")
        st.text(raw_text[:2000])

# If the uploaded file is tabular, override df
if user_df is not None:
    user_df = user_df.rename(columns={
        "Needs_Reorder": "NeedsReorder",
        "Waste_Risk_Score": "WasteRiskScore",
        "Action_Priority": "ActionPriority",
    })
    df = user_df
    st.info("Using uploaded table instead of default inventory_optimized.csv.")
else:
    st.info("Using default inventory_optimized.csv (no table uploaded).")



# Normalize column names for downstream code
df = df.rename(columns={
    "Needs_Reorder": "NeedsReorder",
    "Waste_Risk_Score": "WasteRiskScore",
    "Action_Priority": "ActionPriority",
})

df["Days_to_Expire"] = pd.to_numeric(df["Days_to_Expire"], errors="coerce")

expired_df = df[df["Days_to_Expire"] < 0].copy()              # already expired
about_to_expire_df = df[(df["Days_to_Expire"] >= 1) &
                        (df["Days_to_Expire"] <= 10)].copy()   # 1–10 days lef


load_dotenv("OPENAI_API_KEY.env")
api_key = os.getenv("OPENAI_API_KEY")



client = OpenAI()  # uses OPENAI_API_KEY from your env

def call_llm(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a grocery inventory optimization assistant. "
                    "You see small CSV snippets about products (stock, predicted sales, "
                    "waste risk, reorder point, priority). "
                    "Always answer briefly in markdown with clear, practical actions "
                    "for the store manager."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
        max_tokens=800,
    )
    return response.choices[0].message.content

# ---------- SETTINGS ----------
with st.expander("⚙️ Settings (near-expiry & risk thresholds)", expanded=False):
    near_min = st.number_input("Near-expiry minimum days", value=1, min_value=-30, max_value=365)
    near_max = st.number_input("Near-expiry maximum days", value=10, min_value=-30, max_value=365)
    risk_threshold = st.slider("Waste risk threshold for URGENT", 0.0, 10.0, 0.5, 0.1)

# use settings for derived frames
df["Days_to_Expire"] = pd.to_numeric(df["Days_to_Expire"], errors="coerce")
expired_df = df[df["Days_to_Expire"] < 0].copy()
about_to_expire_df = df[
    (df["Days_to_Expire"] >= near_min) & (df["Days_to_Expire"] <= near_max)
].copy()


# ---------- HEADER ----------
st.title("🛒 Grocery Inventory AI Assistant")
st.caption(
    "Monitor **urgent items**, **reorders**, and **waste risk** so you can act before products expire."
)

k1, k2, k3 = st.columns(3)
k1.metric("🚨 Urgent items", int((df["ActionPriority"] == "URGENT").sum()))
k2.metric("📦 Reorder items", int((df["ActionPriority"] == "REORDER").sum()))
k3.metric("📊 Total SKUs", len(df))

# ---------- TABS ----------
tab_overview, tab_products, tab_chat = st.tabs(["📊 Overview", "📦 Products", "🤖 Assistant"])

with tab_overview:
    # Inventory action overview
    overview = (
        df["ActionPriority"]
        .value_counts()
        .rename("count")
        .reset_index()
        .rename(columns={"index": "ActionPriority"})
    )
    st.subheader("Inventory action overview")
    overview = (
    df["ActionPriority"]
    .value_counts()
    .rename("count")
    .reset_index()
    .rename(columns={"index": "ActionPriority"})
)
    st.bar_chart(overview, x="ActionPriority", y="count")
    st.divider()

    # Category summary
    st.markdown("### Category Risk Overview")
    st.caption("Average waste risk and action counts per category")
    if not all(col in df.columns for col in ["Category", "WasteRiskScore", "ActionPriority", "NeedsReorder"]):
        st.warning("Category summary cannot be shown because some required columns are missing.")
    else:
        category_summary = df.groupby("Category").agg({
            "WasteRiskScore": ["mean", "count"],
            "ActionPriority": lambda x: (x == "URGENT").sum(),
            "NeedsReorder": "sum",
        }).round(2)
        category_summary.columns = ["Avg Waste Risk", "Total Items", "URGENT Count", "REORDER Count"]
        category_summary = category_summary.sort_values("Avg Waste Risk", ascending=False)
        st.dataframe(category_summary, use_container_width=True)
        top_category = category_summary.index[0]
        top_risk = category_summary.iloc[0]["Avg Waste Risk"]
        st.metric("🚨 Highest Risk Category", top_category, f"{top_risk:.2f} avg waste risk")

with tab_products:
    col1, col2 = st.columns(2)

    # URGENT ITEMS


with col1:
    st.markdown("### 🚨 High waste-risk items")
    st.caption("Products marked as **URGENT** based on waste risk and stock levels.")

    show_urgent = st.button("Show urgent items", key="btn_urgent")
    if show_urgent:
        urgent = df[df["ActionPriority"] == "URGENT"].sort_values(
            "WasteRiskScore", ascending=False
        ).head(15)
        st.write(f"Urgent rows found: {len(urgent)}")

        def color_risk(val):
            return "background-color: #ffe5e5" if val > 6 else ""

        urgent_view = urgent[
            ["Product_Name", "WasteRiskScore", "Stock_Quantity", "Predicted_Sales", "ActionPriority"]
        ]
        styled_urgent = urgent_view.style.applymap(color_risk, subset=["WasteRiskScore"])
        st.dataframe(styled_urgent, use_container_width=True)

        # Download button must be inside this block
        csv_urgent = urgent_view.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download urgent items (CSV)",
            data=csv_urgent,
            file_name="urgent_items.csv",
            mime="text/csv",
            key="dl_urgent",
        )


# ⚠️ REORDER ITEMS
with col2:
    st.markdown("### ⚠️ Items to reorder")
    st.caption("Products where stock is below the optimized **Reorder Point**.")

    if st.button("Show items to reorder", key="btn_reorder"):
        if "NeedsReorder" in df.columns:
            reorder = df[df["NeedsReorder"] == 1].sort_values(
                "Reorder_Point", ascending=False
            ).head(15)
            st.write(f"Reorder rows found: {len(reorder)}")

            reorder_view = reorder[
                ["Product_Name", "Stock_Quantity", "Reorder_Point", "EOQ", "ActionPriority"]
            ]
            st.dataframe(reorder_view, use_container_width=True)

            csv_reorder = reorder_view.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download reorder list (CSV)",
                data=csv_reorder,
                file_name="reorder_items.csv",
                mime="text/csv",
                key="dl_reorder",
            )
        else:
            st.warning("Column `NeedsReorder` is missing in the dataset.")
    


    st.divider()
    st.markdown("### 🔍 Search product")
    st.caption(
        "Type part of a product name (e.g., **Yogurt**, **Bread**, **Milk**) "
        "to see stock, predicted sales, waste risk, and action priority."
    )
    query = st.text_input("Product name contains:")
    if query:
        results = df[df["Product_Name"].str.contains(query, case=False, na=False)].copy()
        results = results.sort_values("WasteRiskScore", ascending=False).head(20)
        if results.empty:
            st.info("No matching products found.")
        else:
            st.write(f"Found {len(results)} products:")
            st.dataframe(
                results[
                    ["Product_Name", "Stock_Quantity", "Predicted_Sales", "WasteRiskScore", "ActionPriority"]
                ],
                use_container_width=True,
            )
with tab_chat:
    st.markdown("### 🤖 Chat with your inventory assistant")
    # keep your existing chat_history, context_df, and call_llm logic here


# --- Search + Chat combined ---
st.divider()
st.markdown("### 🤖 Chat with your inventory assistant")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# show previous messages
for role, msg in st.session_state.chat_history:
    with st.chat_message(role):
        st.markdown(msg)

user_msg = st.chat_input(
    "Type a product name or question (this will search and also ask the assistant)...",
    key="inventory_chat_input",
)

if user_msg:
    st.session_state.chat_history.append(("user", user_msg))
    user_lower = user_msg.lower()

    # --- decide which rows to use ---
    if "expired" in user_lower and "about to" not in user_lower:
        # only expired
        context_df = expired_df.head(50)
        filter_info = "expired products"
    elif (
        "about to expire" in user_lower
        or "near expiry" in user_lower
        or "nearing expiry" in user_lower
        or "close to expiry" in user_lower
    ):
        # only about-to-expire (1–10 days)
        context_df = about_to_expire_df.head(50)
        filter_info = "products with 1–10 days to expiry"
    else:
        # default: both (expired first, then about-to-expire)
        context_df = pd.concat([expired_df, about_to_expire_df]).head(50)
        filter_info = "expired and near‑expiry products"

    


    # --- show matching products, if any ---
    if context_df.empty:
        st.info("No products match this expiry filter. Try a wider range or a different query.")
    else:
        st.markdown(f"#### Matching products ({filter_info})")
        st.dataframe(
            context_df[
                [
                    "Product_Name",
                    "Stock_Quantity",
                    "Predicted_Sales",
                    "Days_to_Expire",
                    "WasteRiskScore",
                    "ActionPriority",
                ]
            ],
            use_container_width=True,
        )

    # --- build prompt and call LLM ---
    context_text = context_df.to_csv(index=False)
    prompt = (
        "You are a grocery inventory optimization assistant.\n\n"
        "Use only the products provided in the CSV snippet. "
        "For 'near expiry' questions, treat near‑expiry as products with "
        "Days_to_Expire between 1 and 10 and ignore negative values.\n\n"
        "Here is CSV data for relevant products:\n"
        f"{context_text}\n\n"
        f"User question: {user_msg}\n\n"
        "Answer briefly with clear, practical recommendations in markdown, "
        "listing specific products when available."
    )

    ai_answer = call_llm(prompt)
    st.session_state.chat_history.append(("assistant", ai_answer))

    with st.chat_message("assistant"):
        st.markdown(ai_answer)




# display chat history
for role, msg in st.session_state.chat_history:
    with st.chat_message(role):
        st.markdown(msg)




