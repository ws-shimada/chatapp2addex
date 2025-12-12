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
MODEL_NAME="gpt-4-1106-preview"
SLEEP_TIME_LIST = [5, 5, 5, 5, 5] # 各対話ターンの待機時間
DISPLAY_TEXT_LIST = ['「原子力発電を廃止すべきか否か」という意見に対して、あなたの意見を入力し、送信ボタンを押してください。',
                     'あなたの意見を入力し、送信ボタンを押してください。']
QUALTRICS_URL = "https://nagoyapsychology.qualtrics.com/jfe/form/SV_bOgTKz1CH3uES7c"
try:
    OPENAI_API_KEY = st.secrets["openai_api_key"]
except Exception:
    st.error("OpenAI APIキーが設定されていません。`secrets.toml` を確認してください。")
    st.stop()
try:
    FIREBASE_APIKEY_DICT = json.loads(st.secrets["firebase"]["textkey"])
except Exception as e:
    st.error(f"Firebase の認証情報の読み込みに失敗しました: {e}")
    st.stop()

## chat act config
FPATH = "preprompt_negative_binding_nuclear.txt"
try:
    with open(FPATH, encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    st.error("システムプロンプトファイルが見つかりません。デプロイ時に同じディレクトリに配置してください。")
    st.stop()

# id check
if not "sessionid" in st.query_params:
    st.error("ユーザーIDが設定されていません。URLを確認してください")
    st.stop()
if not "user_id" in st.session_state:
    st.session_state.user_id = st.query_params["sessionid"]
if "user_id" in st.session_state:
    config = {"configurable": {"thread_id": st.session_state.user_id}}

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

def stream_graph_updates(user_input: str) -> str | None:
    try:
        events = graph.stream({"messages": [("user", user_input)]},
                              config, stream_mode="values")
        ai_text = None
        for event in events:
            messages = event["messages"]
            for m in messages:
                # LangGraph/LC のメッセージ型に合わせてここ調整
                if m.type in ("ai", "assistant"):
                    ai_text = m.content
        return ai_text
    except Exception as e:
        # ログを壊さない
        st.session_state.last_error = f"llm_error: {e}"
        st.error("AIの応答でエラーが発生しました。時間をおいて再度お試しください。")
        return None

# Firebase 設定の読み込み

try:
    creds = service_account.Credentials.from_service_account_info(FIREBASE_APIKEY_DICT)
    project_id = FIREBASE_APIKEY_DICT["project_id"]
    db = firestore.Client(credentials=creds, project=project_id)
    st.session_state.firestore_available = True
except Exception as e:
    st.session_state.firestore_available = False
    st.error("Firestore の初期化に失敗しました。ログはクラウドに保存されません。")

# 入力時の動作
def submitted():
    user_input = st.session_state.last_input
    if user_input is None or len(str(user_input).strip()) == 0:
        st.error("内部エラー：ユーザー入力が取得できませんでした。最初からやり直してください。")
        st.stop()
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
        user_input = st.session_state.last_input
        ai_reply = stream_graph_updates(st.session_state.last_input)
        if ai_reply is None or len(str(ai_reply).strip()) == 0:
            # 人間の発言はもう log に乗っているので、それだけ残す
            st.warning("今回は相手からの返信を取得できませんでした。もう一度お試しください。")
            # talktime を進めない / Firestoreにも書かない
            st.session_state.state = 1
            st.stop()
        st.session_state.log.append({"role": "ai", "content": ai_reply})
        if st.session_state.firestore_available:
            try:
                doc_ref = db.collection(str(st.session_state.user_id)).document(str(st.session_state.talktime))
                doc_ref.set({
                    "bottype": "indi",
                    "Human": user_input,
                    "AI": ai_reply,
                    "Human_msg_sended": st.session_state.send_time,
                    "AI_msg_returned": st.session_state.return_time,
                })
            except Exception as e:
                st.session_state.last_error = f"firestore_error: {e}"
                st.warning("ログの保存に失敗しました（Firestore）。ローカルのダウンロードログを必ず確保してください。")
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
        for i, msg in enumerate(st.session_state.log):
            if msg["role"] == "human":
                message(
                    msg["content"],
                    is_user=True,
                    avatar_style="adventurer",
                    seed="Nala",
                    key=f"user_{i}",
                )
            else:
                message(
                    msg["content"],
                    is_user=False,
                    avatar_style="micah",
                    key=f"ai_{i}",
                )
    if st.session_state.talktime < 5:  # 会話時
        with st.container():
            prompt_text = DISPLAY_TEXT_LIST[0] if st.session_state.talktime == 0 else DISPLAY_TEXT_LIST[1]
            with st.form("chat_form", clear_on_submit=True, enter_to_submit=False):
                user_input = st.text_area(prompt_text, key="chat_input")
                submit_msg = st.form_submit_button(
                    label="送信",
                    type="primary")
            if submit_msg:
                cleaned = user_input.strip()
                if len(cleaned) == 0:
                    st.warning("1文字以上入力してください。")
                    st.stop()
                st.session_state.log.append({"role": "human", "content": cleaned})
                st.session_state.last_input = cleaned
                st.session_state.send_time = str(datetime.datetime.now(pytz.timezone('Asia/Tokyo')))
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
