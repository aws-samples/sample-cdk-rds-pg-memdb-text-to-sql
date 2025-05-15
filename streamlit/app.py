# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  *
#  * Permission is hereby granted, free of charge, to any person obtaining a copy of this
#  * software and associated documentation files (the "Software"), to deal in the Software
#  * without restriction, including without limitation the rights to use, copy, modify,
#  * merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  * permit persons to whom the Software is furnished to do so.
#  *
#  * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#  * INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
#  * PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#  * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#  * OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
#  * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#  */

import json
import ast

import requests

import streamlit as st
import pandas as pd

# API Gateway endpoint URL
API_ENDPOINT = st.secrets["api_endpoint"] + "text-to-sql"

# Initialize Streamlit app
st.set_page_config(page_title="Text2SQL Chatbot", layout="wide")
header = st.container()
header.title(":robot_face: Chatbot for US Home Property Data :house: :earth_americas:")
header.write("""This chatbot can answer follow-up questions and maintain context across multiple queries.""")
header.write("""<div class='fixed-header'/>""", unsafe_allow_html=True)

# Get secret
api_key = st.secrets["api_key"]

MAX_CONTEXT_LENGTH = 5
MAX_PAYLOAD_SIZE = 5 * 1024 * 1024  # 5 MB, adjust as needed

### Custom CSS for the sticky header
st.markdown(
    """
<style>
    div[data-testid="stVerticalBlock"] div:has(div.fixed-header) {
        position: sticky;
        top: 2.875rem;
        background-color: #273346;
        z-index: 999;
    }
    .fixed-header {
        border-bottom: 1px solid white;
    }
</style>
    """,
    unsafe_allow_html=True
)


def display_assistant_response(response_text, sql_query, sql_results=None, column_names=None):
    col1, col2 = st.columns([0.55, 0.45])
    with col1:
        st.markdown(response_text)
    with col2:
        if sql_results:
            st.markdown("### SQL Results\n(Up to five shown)")
            try:
                # Parse column_names if they're a JSON string
                if isinstance(column_names, str):
                    try:
                        column_names = json.loads(column_names)
                    except json.JSONDecodeError:
                        st.text("Could not parse column names as JSON")
                        column_names = []

                # Parse sql_results if it's a string
                if isinstance(sql_results, str):
                    try:
                        sql_results = ast.literal_eval(sql_results)
                    except Exception as e:
                        st.text(f"Could not parse query results: {e}")

                # Now we have both column_names and sql_results as Python objects
                df = pd.DataFrame(sql_results, columns=column_names)
                st.table(df.head(5))

            except Exception as e:
                st.error(f"Error rendering results: {str(e)}")
                st.text(f"Column names type: {type(column_names)}")
                st.text(f"SQL results type: {type(sql_results)}")

                # Display raw results as a fallback
                st.text("Raw results:")
                max_display = 500  # Limit display length
                result_str = str(sql_results)
                if len(result_str) > max_display:
                    st.code(result_str[:max_display] + "...")
                else:
                    st.code(result_str)

        st.markdown("### Generated SQL Query")

        # Handle the new format where sql_query can be a list [query_string, parameters]
        if isinstance(sql_query, list) and len(sql_query) > 0:
            query_text = sql_query[0]  # Extract the actual SQL query

            # If there are parameters, show them too
            if len(sql_query) > 1 and sql_query[1]:
                params = sql_query[1]
                if isinstance(params, dict):
                    params_text = "\n-- Named Parameters:\n"
                    for k, v in params.items():
                        params_text += f"--   {k}: {v}\n"
                else:
                    params_text = "\n-- Positional Parameters: " + str(params)
                query_text += params_text

            st.code(query_text, language="sql")
        else:
            # Handle the old format or empty queries
            st.code(sql_query, language="sql")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_context" not in st.session_state:
    st.session_state.conversation_context = []

# Create a container for the expander title and clear button
context_container = st.container()
context_col1, context_col2 = context_container.columns([0.9, 0.1])

# Add the expander in the first column
with context_col1:
    with st.expander("Conversation Context"):
        st.write(st.session_state.conversation_context)

# Add the clear button in the second column, aligned with the expander title
with context_col2:
    if st.button("🗑️", key="clear_chat", help="Clear conversation history"):
        st.session_state.messages = []
        st.session_state.conversation_context = []
        st.rerun()

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["content"])
        else:
            display_assistant_response(message["response"], message["query"])


# Function to send a message to the API Gateway
def send_message(message_prompt, conversation_context):
    payload = {
        "query": message_prompt,
        "conversation_context": conversation_context
    }

    if len(payload) > MAX_PAYLOAD_SIZE:
        st.error("Payload too large. Starting a new conversation.")
        st.session_state.conversation_context = []
        payload = {"query": message_prompt, "conversation_context": []}

    headers = {"Content-Type": "application/json", "x-api-key": api_key}

    try:
        http_response = requests.post(API_ENDPOINT, data=json.dumps(payload), headers=headers, timeout=30)
        http_response.raise_for_status()
        response_data = http_response.json().get("body", {})
    except Exception as e:
        return (
            f"Please try rephrasing your question about US housing data.",
            "No SQL generated",
            [],
            []
        )

    return (
        response_data.get("response", "I couldn't generate SQL for that question. Please try being more specific."),
        response_data.get("query", "No SQL generated"),
        response_data.get("query_results", []),
        response_data.get("column_names", [])
    )


# Send user message to API Gateway and get response
if user_input := st.chat_input("Say something"):
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(user_input)

    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.conversation_context.append({"role": "user", "content": user_input})

    try:
        response, query, results, columns = send_message(user_input, st.session_state.conversation_context)
        # Escape dollar signs in the response
        resp_text = response.replace("$", r"\$")
        with st.chat_message("assistant"):
            display_assistant_response(resp_text, query, results, columns)

        # Add assistant response to chat history
        st.session_state.messages.append({
            "role": "assistant",
            "response": resp_text,
            "query": query
        })
        st.session_state.conversation_context.append({
            "role": "assistant",
            "content": resp_text,
            "sql_query": query,
            "results_summary": f"Found {len(results) if results else 0} records"
        })

        # Limit the context size
        if len(st.session_state.conversation_context) > MAX_CONTEXT_LENGTH * 2:
            st.session_state.conversation_context = st.session_state.conversation_context[-MAX_CONTEXT_LENGTH * 2:]
    except requests.HTTPError as e:
        st.error(f"An error occurred: {str(e)}")
