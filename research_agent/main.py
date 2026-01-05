import streamlit as st
from orchestrator import  task_classifier
st.title("Research Agent")
st.divider()
st.markdown("This is the Research Agent application.")
user_input = st.text_area("Enter your research query here:")

