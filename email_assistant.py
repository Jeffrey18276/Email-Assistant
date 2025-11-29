import streamlit as st
from langchain_core.messages import SystemMessage
import os
from dotenv import load_dotenv
import pathlib
import time
from datetime import datetime,timedelta

today = datetime.today()
start_last_week = today-timedelta(today.weekday()+7)
end_last_week = start_last_week+timedelta(days=6)
search_query = f"in:inbox after:{start_last_week.strftime('%Y-%m-%d')} before:{end_last_week.strftime('%Y-%m-%d')}"

st.set_page_config(page_title="Email Assistant", page_icon="🤖")

def load_css(file_path):
    with open(file_path) as f:
        st.html(f"<style>{f.read()}</style>")

load_dotenv()
css_path = pathlib.Path("style.css")
load_css(css_path)

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'trigger_ai' not in st.session_state:
    st.session_state.trigger_ai = False

st.title("AI Email Assistant")

SYSTEM_PROMPT = """You are a helpful email assistant. Your task is to help users manage and respond to their emails with high accuracy.

GMAIL TOOLS AVAILABLE:
- Search tool: Search emails. Provide ONLY the search query as a plain string
- Send tool: Send emails immediately. Provide a PROPERLY FORMATTED JSON string
- Draft tool: Create email drafts. Provide a JSON string

CRITICAL FORMATTING RULES:

FOR SEARCH TOOL:
- Input: "is:unread from:john"  ← JUST THE QUERY STRING
- Examples: "in:inbox", "is:unread", "from:example@gmail.com"




FOR SEND TOOL - MUST USE THIS EXACT JSON FORMAT:
{"__arg1": {"to": "email@example.com", "subject": "Subject here", "message": "Message body here"}}

- The "__arg1" wrapper is REQUIRED for tool validation.
- Always use this format when sending emails programmatically.

COMPOSING EMAILS - SMART DETECTION:
1. FIRST, check if the user has already provided all details (recipient, subject, message) in their request.
2. If ALL details are present:
   - Summarize what you understood
   - Ask for confirmation: "Should I send this email?"
   - When confirmed, immediately use the send tool
3. If details are MISSING, ask for them one at a time:
   - Missing recipient? Ask: "Who would you like to send this email to?"
   - Missing subject? Ask: "What should the subject be?"
   - Missing message? Ask: "What would you like to say in the message?"

EXAMPLES OF COMPLETE REQUESTS:
- "Send an email to john@example.com with subject 'Meeting' saying 'Let's meet tomorrow'"
- "Email sarah@test.com, subject: Project Update, message: The project is on track"

IMPORTANT RULES:
- When user provides all information at once, DO NOT ask for each detail separately
- When user confirms with "yes", "correct", "send it", "go ahead", etc., immediately send using the tool
- DO NOT ask "how can I help you" after sending - just confirm it was sent
- Remember conversation context - use the exact details the user provided

BE NATURAL AND HELPFUL in your conversations!."""


robot_avatar = 'images/robot.png'

def create_agent():
    """Create a fresh agent with properly configured Gmail tools"""
    from langchain_groq import ChatGroq
    from langchain_google_community import GmailToolkit
    from langchain_google_community.gmail.utils import (
        build_gmail_service,
        get_google_credentials,
    )
    from langchain.agents import create_agent
    from langchain_core.tools import Tool
    import json
    
    # Get credentials
    credentials = get_google_credentials(
        token_file="token.json",
        scopes=["https://mail.google.com/"],
        client_secrets_file="credentials.json",
    )
    
    # Build service
    api_resource = build_gmail_service(credentials=credentials)
    toolkit = GmailToolkit(api_resource=api_resource)
    
    # Get the original tools
    original_tools = toolkit.get_tools()
    
    def create_safe_tool(tool):
        original_func = getattr(tool, "run", None)
        if not original_func:
            return None
            
        def safe_wrapper(input_str):
            try:
                print(f"🔧 TOOL CALLED: {tool.name}")
                print(f"🔧 RAW INPUT: {input_str}")
                print(f"🔧 INPUT TYPE: {type(input_str)}")
                
                # For search tool - handle different input formats
                if tool.name == "search_gmail":
                    print("🔧 Executing SEARCH tool")
                    
                    # The input should be a plain string like "in:inbox"
                    if isinstance(input_str, str) and input_str.strip():
                        search_query = input_str.strip()
                        print(f"🔧 SEARCH QUERY: '{search_query}'")
                        
                        # Call the original function with the query
                        result = original_func(search_query)
                        print(f"🔧 SEARCH SUCCESS")
                        return f"Search completed for: {search_query}\nResults: {result}"
                    else:
                        return "Error: Please provide a valid search query"
                
                # For send_message tool - expect JSON string
                elif tool.name == "send_gmail_message":
                    print("🔧 Executing SEND tool")
                    try:
                        # Handle both string and object inputs
                        if isinstance(input_str, str):
                            # Try to parse as JSON string
                            try:
                                message_data = json.loads(input_str)
                                print(f"🔧 PARSED JSON STRING: {message_data}")
                            except json.JSONDecodeError:
                                print(f"🔧 NOT JSON, treating as plain string")
                                return "Error: Invalid JSON format for email data"
                        elif isinstance(input_str, dict):
                            # Already a dictionary object ← NEW!
                                message_data = input_str
                                print(f"🔧 RECEIVED DICT OBJECT: {message_data}")
                        else:
                            print(f"🔧 UNEXPECTED TYPE: {type(input_str)}")
                            return f"Error: Unexpected input type: {type(input_str)}"

                    # Extract the actual data
                        if "__arg1" in message_data:
                            actual_data = message_data["__arg1"]
                        else:
                            actual_data = message_data
                    
                        print(f"🔧 FINAL DATA TO SEND: {actual_data}")
                    
                        # Validate required fields ← NEW!
                        if not all(key in actual_data for key in ["to", "subject", "message"]):
                            return "Error: Missing required fields (to, subject, message)"
                    
                        # Send the email
                        result = original_func(actual_data)
                        print(f"🔧 SEND SUCCESS")
                        return f"✅ Email sent successfully: {result}"

                        
                    except Exception as send_error:
                        print(f"🔧 SEND ERROR: {send_error}")
                        import traceback
                        print(f"🔧 FULL TRACEBACK: {traceback.format_exc()}")
                        return f"❌ Send failed: {str(send_error)}"
                # For create_draft tool
                elif tool.name == "create_gmail_draft":
                    print("🔧 Executing DRAFT tool")
                    try:
                        if isinstance(input_str, str):
                            message_data = json.loads(input_str)
                        else:
                            message_data = input_str
                        result = original_func(message_data)
                        return f"✅ Draft created: {result}"
                    except Exception as draft_error:
                        return f"❌ Draft creation failed: {str(draft_error)}"
                
                # For other tools
                else:
                    print(f"🔧 Executing OTHER tool: {tool.name}")
                    result = original_func(input_str)
                    return f"Tool result: {result}"
                    
            except Exception as e:
                print(f"🔧 TOOL ERROR: {e}")
                import traceback
                print(f"🔧 FULL TRACEBACK: {traceback.format_exc()}")
                return f"Tool error: {str(e)}"
        
        return Tool(
            name=tool.name,
            description=tool.description,
            func=safe_wrapper
        )
    
    # Create safe tools
    safe_tools = []
    for tool in original_tools:
        safe_tool = create_safe_tool(tool)
        if safe_tool:
            safe_tools.append(safe_tool)
    
    llm = ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model="openai/gpt-oss-20b",
        temperature=0,
        max_tokens=1000,
        model_kwargs= {
            "response_format":None
        }
        
    )
    
    return create_agent(llm, safe_tools)


def process_message(prompt, response_placeholder=None):
    try:
        agent = create_agent()
        
        full_response = ""
        has_content = False
        
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        
        
        for msg in st.session_state.messages:
            if msg['role'] == 'user':
                messages.append(("user", msg['content']))
            elif msg['role'] == 'assistant':
                messages.append(("assistant", msg['content']))
        
        # Add the current prompt if it's not already in session state
        if not st.session_state.messages or st.session_state.messages[-1]['content'] != prompt:
            messages.append(("user", prompt))
        
        
        if response_placeholder:
            response_placeholder.markdown('<span class="thinking-animation">💭 Thinking...</span>', unsafe_allow_html=True)
        
        # MAIN STREAMING LOOP
        for chunk in agent.stream(
            {'messages': messages},
            stream_mode='values'
        ):
            if 'messages' in chunk and len(chunk['messages']) > 0:
                last_message = chunk['messages'][-1]
                
                if hasattr(last_message, 'content') and last_message.content:
                    if hasattr(last_message, 'type') and last_message.type == 'ai':
                        full_response = last_message.content
                        has_content = True
                        # Clear thinking animation and show streaming response
                        if response_placeholder:
                            response_placeholder.markdown(full_response + " ▌")
        
        # If we have content, return it without the cursor
        if has_content and response_placeholder:
            response_placeholder.markdown(full_response)
        
        return full_response if full_response else "I couldn't generate a response. Please try a different query."
        
    except Exception as api_error:
        err_msg = f"Error processing message: {str(api_error)}"
        # Also update the placeholder if it exists
        if response_placeholder:
            response_placeholder.markdown(f"❌ {err_msg}")
        return err_msg
    except Exception as e:
        err_msg = f"Unexpected error: {str(e)}"
        if response_placeholder:
            response_placeholder.markdown(f"❌ {err_msg}")
        return err_msg

# Display chat history
for message in st.session_state.messages:
    avatar = '🧑‍💻' if message['role'] == 'user' else robot_avatar
    with st.chat_message(message['role'],avatar=avatar):
        st.markdown(message['content'])

# Process sidebar button trigger
if st.session_state.trigger_ai and len(st.session_state.messages) > 0:
    
    last_message = st.session_state.messages[-1]
    if last_message['role'] == 'user':
        with st.chat_message('assistant',avatar=robot_avatar):
            response_placeholder = st.empty()
            
            response = process_message(last_message['content'], response_placeholder)
            
            st.session_state.messages.append({'role': 'assistant', 'content': response})
    
    st.session_state.trigger_ai = False
    st.rerun()

# Chat input
if prompt := st.chat_input("Ask about your emails...."):
    st.session_state.messages.append({'role': 'user', 'content': prompt})
    with st.chat_message("user",avatar='🧑‍💻'):
        st.markdown(prompt)

    with st.chat_message('assistant',avatar=robot_avatar):
        response_placeholder = st.empty()
        
        response = process_message(prompt, response_placeholder)
        
        st.session_state.messages.append({'role': 'assistant', 'content': response})
        st.rerun()

# Sidebar controls with improved queries
with st.sidebar:
    st.header("🔧 Controls")
    st.subheader("Quick Actions")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Inbox", use_container_width=True):
            st.session_state.messages.append({
                'role': 'user', 
                'content': search_query
            })
            st.session_state.trigger_ai = True
            st.rerun()
        if st.button("📝 Send Email", use_container_width=True):
            st.session_state.messages.append({
                'role': 'user', 
                'content': "I want to send an email"
            })
            st.session_state.trigger_ai = True
            st.rerun()
    with col2:
        if st.button("🔍 Search", use_container_width=True):
            st.session_state.messages.append({
                'role': 'user', 
                'content': 'Search for important emails is:unread'
            })
            st.session_state.trigger_ai = True
            st.rerun()
            
        if st.button("📊 Stats", use_container_width=True):
            st.session_state.messages.append({
                "role": "user", 
                "content": "How many unread emails do I have?"
            })
            st.session_state.trigger_ai = True
            st.rerun()

    st.subheader("Chat Management")
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    
    st.divider()
    st.caption(f"💬 Messages: {len(st.session_state.messages) // 2}")
