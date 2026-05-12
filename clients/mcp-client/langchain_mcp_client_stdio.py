"""
langchain_mcp_client_stdio.py

Despite the filename, this client connects to an MCP server over **SSE**
(not stdio). The filename is kept for historical/import reasons.

What this file does:
  - Connects to an MCP server via SSE (URL configurable via MCP_SSE_URL env var,
    default http://127.0.0.1:8000/sse).
  - Loads the available MCP tools using the adapter function load_mcp_tools.
  - Instantiates the ChatGoogleGenerativeAI model (Google Gemini) using your
    GOOGLE_API_KEY.
  - Creates a React agent using LangGraph's prebuilt agent (create_react_agent)
    with the LLM and tools.
  - Runs an interactive asynchronous chat loop for processing user queries.

Detailed explanations:
  - Retries (max_retries=2): If an API call fails due to transient errors
    (e.g. network issues), the call will automatically be retried up to 2 times.
  - Temperature (set to 0): Controls randomness. A temperature of 0 yields
    deterministic responses. Higher values (e.g., 0.7) yield more creative,
    varied responses.
  - GOOGLE_API_KEY: Required for authentication with Google's generative AI
    service.
"""

import asyncio
import os

from mcp import ClientSession
from mcp.client.sse import sse_client

from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent

from langchain_google_genai import ChatGoogleGenerativeAI

from langchain.memory import ConversationSummaryBufferMemory
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from dotenv import load_dotenv

load_dotenv()


# ---------------------------
# LLM Instantiation
# ---------------------------
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-lite",
    temperature=0,
    max_retries=2,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

# ----------------------------
# Memory
# ---------------------------
memory = ConversationSummaryBufferMemory(
    llm=llm,
    return_messages=True,  # ensures messages are stored as AI/HumanMessage objects
    max_token_limit=1000,  # how much history to keep before summarizing
)


SSE_URL = os.getenv("MCP_SSE_URL", "http://127.0.0.1:8000/sse")


async def run_agent():
    async with sse_client(SSE_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)

            agent = create_react_agent(llm, tools)

            print(f"MCP Client (SSE) connected to {SSE_URL}. Type 'quit' to exit.")
            memory.chat_memory.add_message(
                SystemMessage(
                    content="You are a helpful assistant connected to MCP tools."
                )
            )
            while True:
                query = input("\nQuery: ").strip()
                if query.lower() == "quit":
                    break

                # Add the new user message to memory once.
                memory.chat_memory.add_message(HumanMessage(content=query))

                # Retrieve context (past messages + summary if long). This
                # already includes the query we just appended, so we pass it
                # through as-is — no duplicate HumanMessage.
                past_messages = memory.load_memory_variables({})["history"]

                response = await agent.ainvoke({"messages": past_messages})

                # The agent returns a state dict whose "messages" list ends with
                # the final AI message. Extract it for both display and memory.
                final_message = response["messages"][-1]
                final_text = getattr(final_message, "content", str(final_message))

                memory.chat_memory.add_message(AIMessage(content=final_text))

                print("\nResponse:")
                print(final_text)


if __name__ == "__main__":
    asyncio.run(run_agent())
