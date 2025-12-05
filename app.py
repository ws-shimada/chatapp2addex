# import libraries
## streamlit
import streamlit as st
from streamlit_chat import message
##langchain
from langchain_openai.chat_models import ChatOpenAI
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
)
## class definition
from typing import Annotated
from typing_extensions import TypedDict
## langgraph
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
# ## visualize
# from IPython.display import Image, display
## time
from time import sleep
import datetime
import pytz # convert timezone
global now # get time from user's PC
now = datetime.datetime.now(pytz.timezone('Asia/Tokyo'))
## library firebase
import firebase_admin
from google.oauth2 import service_account
from google.cloud import firestore
import json
# ## library calculate tokens
# import tiktoken

# constant
## langsmith（動いていない）
# LANGCHAIN_TRACING_V2=True
# LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
# LANGCHAIN_API_KEY=userdata.get('langchain_api_key')
# LANGCHAIN_PROJECT="chatapptest202501"
## langchain
OPENAI_API_KEY=st.secrets.openai_api_key
MODEL_NAME="gpt-4-1106-preview"
## chat act config
FPATH = "preprompt_negative_binding_nuclear.txt"
with open(file = FPATH, encoding = "utf-8") as f:
    SYSTEM_PROMPT = f.read()
SLEEP_TIME_LIST = [5, 5, 5, 5, 5] # 各対話ターンの待機時間
DISPLAY_TEXT_LIST = ['「原子力発電を廃止すべきか否か」という意見に対して、あなたの意見を入力し、送信ボタンを押してください。',
                     'あなたの意見を入力し、送信ボタンを押してください。']
QUALTRICS_URL = "https://nagoyapsychology.qualtrics.com/jfe/form/SV_1YXssOhyFAzPQea/"
FIREBASE_APIKEY_DICT = json.loads(st.secrets["firebase"]["textkey"])
if not "user_id" in st.session_state:
    st.session_state.user_id = st.query_params["sessionid"]
OPENAI_API_KEY=st.secrets.openai_api_key

class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]

graph_builder = StateGraph(State)
llm = ChatOpenAI(model=MODEL_NAME,
                 api_key=OPENAI_API_KEY)
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
    ]
)
chain = prompt | llm
if "user_id" in st.session_state:
    config = {"configurable": {"thread_id": st.session_state.user_id}}
if not "memory" in st.session_state:
    st.session_state.memory = MemorySaver()

def chatbot(state: State):
    return {"messages": [chain.invoke({"history":state["messages"]})]}

# The first argument is the unique node name
# The second argument is the function or object that will be called whenever
# the node is used.
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("chatbot", END)
graph = graph_builder.compile(checkpointer=st.session_state.memory)

def stream_graph_updates(user_input: str):
    try:
        events = graph.stream({"messages": [("user", user_input)]}, config, stream_mode="values")
        for event in events:
            messages = event["messages"]
            msg_list = []
            for value in range(len(messages)):
                msg_list.append({
                    "role": messages[value].type,
                    "content": messages[value].content
                })
        return msg_list
    except Exception as e:
        st.error(f"Error occurred: {e}")
        return []

# Firebase 設定の読み込み
creds = service_account.Credentials.from_service_account_info(FIREBASE_APIKEY_DICT)
project_id = FIREBASE_APIKEY_DICT["project_id"]
db = firestore.Client(credentials=creds, project=project_id)

# 入力時の動作
def submitted():
    chat_placeholder = st.empty()
    with chat_placeholder.container():
        for i in range(len(st.session_state.log)):
            msg = st.session_state.log[i]
            if msg["role"] == "human":
                message(msg["content"], is_user=True, avatar_style="adventurer", seed="Nala", key=f"user_{i}")
            else:
                message(msg["content"], is_user=False, avatar_style="micah", key=f"ai_{i}")
    with st.spinner("相手からの返信を待っています..."):
        sleep(SLEEP_TIME_LIST[st.session_state.talktime])
        st.session_state.return_time = str(datetime.datetime.now(pytz.timezone('Asia/Tokyo')))
        user_input = next((msg["content"] for msg in reversed(st.session_state.log) if msg["role"] == "human"),
                          None  # 条件に一致するものがなかった場合のデフォルト値
                         )
        st.session_state.log = stream_graph_updates(user_input)
        doc_ref = db.collection(str(st.session_state.user_id)).document(str(st.session_state.talktime))
        doc_ref.set({
            "bottype" : "bind",
            "Human": next((msg["content"] for msg in reversed(st.session_state.log) if msg["role"] == "human"),
                       None  # 条件に一致するものがなかった場合のデフォルト値
                      ),
            "AI": next((msg["content"] for msg in reversed(st.session_state.log) if msg["role"] == "ai"),
                       None  # 条件に一致するものがなかった場合のデフォルト値
                      ),
            "Human_msg_sended": st.session_state.send_time,
            "AI_msg_returned": st.session_state.return_time,
        })
        st.session_state.talktime += 1
        st.session_state.state = 1
        st.rerun()

# チャット画面
def chat_page():
    if "talktime" not in st.session_state:
        st.session_state.talktime = 0
    if "log" not in st.session_state:
        st.session_state.log = []
    chat_placeholder = st.empty()
    with chat_placeholder.container():
        for i in range(len(st.session_state.log)):
            msg = st.session_state.log[i]
            if msg["role"] == "human":
                message(msg["content"], is_user=True, avatar_style="adventurer", seed="Nala", key=f"user_{i}")
            else:
                message(msg["content"], is_user=False, avatar_style="micah", key=f"ai_{i}")
    if st.session_state.talktime < 5:  # 会話時
        if not "user_input" in st.session_state:
            st.session_state.user_input = "hogehoge"
        with st.container():
            with st.form("chat_form", clear_on_submit=True, enter_to_submit=False):
                if st.session_state.talktime == 0:
                    user_input = st.text_area(DISPLAY_TEXT_LIST[0])
                else:
                    user_input = st.text_area(DISPLAY_TEXT_LIST[1])
                submit_msg = st.form_submit_button(
                    label="送信",
                    type="primary")
            if submit_msg:
                st.session_state.send_time = str(datetime.datetime.now(pytz.timezone('Asia/Tokyo')))
                st.session_state.log.append({"role": "human", "content": user_input})
                st.session_state.state = 2
                st.rerun()
    elif st.session_state.talktime == 5:  # 会話終了時
        st.markdown(
            f"""
            会話が終了しました。\n\n
            下のリンクをクリックし、引き続きアンケートに回答してください。\n\n
            アンケートページは別のタブで開きます。\n\n
            <a href="{QUALTRICS_URL}" target="_blank">アンケートページに進む</a>
            """,
            unsafe_allow_html=True)

def main():
    hide_streamlit_style = """
                <style>
                div[data-testid="stToolbar"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
                }
                div[data-testid="stDecoration"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
                }
                div[data-testid="stStatusWidget"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
                }
                #MainMenu {
                visibility: hidden;
                height: 0%;
                }
                header {
                visibility: hidden;
                height: 0%;
                }
                footer {
                visibility: hidden;
                height: 0%;
                }
                </style>
                """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True) 
    if "state" not in st.session_state:
        st.session_state.state = 1
    if st.session_state.state == 1:
        chat_page()
    elif st.session_state.state == 2:
        submitted()

if __name__ == "__main__":
    main()
