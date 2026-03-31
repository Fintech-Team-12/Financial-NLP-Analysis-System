import os
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.title("Samsung Audit Report QA")
question = st.text_input("질문")
year = st.number_input("연도", min_value=2014, max_value=2024, value=2024)

if st.button("질문하기") and question:
    response = requests.post(f"{API_BASE_URL}/ask", json={"question": question, "year": int(year)}, timeout=30)
    response.raise_for_status()
    data = response.json()
    st.write(data["answer"])
