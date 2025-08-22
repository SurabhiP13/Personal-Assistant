"""
langchain_mcp_client.py

This file implements an MCP client that:
  - Connects to an MCP server via a stdio connection.
  - Loads the available MCP tools using the adapter function load_mcp_tools.
  - Instantiates the ChatGoogleGenerativeAI model (Google Gemini) using your GOOGLE_API_KEY.
  - Creates a React agent using LangGraph’s prebuilt agent (create_react_agent) with the LLM and tools.
  - Runs an interactive asynchronous chat loop for processing user queries.

Detailed explanations:
  - Retries (max_retries=2): If an API call fails due to transient errors (e.g., network issues),
    the call will automatically be retried up to 2 times. Increase this if you experience temporary failures.
  - Temperature (set to 0): Controls randomness. A temperature of 0 yields deterministic responses.
    Higher values (e.g., 0.7) yield more creative, varied responses.
  - GOOGLE_API_KEY: Required for authentication with Google’s generative AI service.

Responses are printed as JSON using a custom encoder to handle non-serializable objects.
"""

#############################################################################################################################
#############################################################################################################################

import asyncio
import os
import json
from typing import Optional

from mcp import ClientSession
from mcp.client.sse import sse_client

from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain.agents.agent import AgentExecutor
from langchain.memory import ConversationSummaryBufferMemory
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain import hub
from dotenv import load_dotenv

load_dotenv()


# ---------------------------
# Custom JSON Encoder
# ---------------------------
class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "content"):
            return {"type": o.__class__.__name__, "content": o.content}
        return super().default(o)


# ---------------------------
# LLM Instantiation
# ---------------------------
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0,
    max_retries=2,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

mcp_client = None

# ---------------------------
# Creating memory object
# ---------------------------

memory = ConversationSummaryBufferMemory(
    llm=llm,  # the same Gemini model you’re already using
    return_messages=True,  # ensures messages are stored as AI/HumanMessage objects
    max_token_limit=1000,  # how much history to keep before summarizing
)
history = [SystemMessage(content="You are a helpful assistant connected to MCP tools.")]
# -----------------------------------------------------------------
# Replacement for load_mcp_tools (compatible with new MCP client)
# -----------------------------------------------------------------
from langchain.tools import StructuredTool
from typing import Dict, Any


async def run_agent():
    global mcp_client
    async with sse_client("http://127.0.0.1:8000/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_client = type("MCPClientHolder", (), {"session": session})()
            tools = await load_mcp_tools(session)
            # memory = ConversationBufferMemory(return_messages=True)  # creates memory

            agent = create_react_agent(llm, tools)  # define agent promp

            print("MCP Client (SSE) Started! Type 'quit' to exit.")
            while True:
                query = input("\nQuery: ").strip()
                if query.lower() == "quit":
                    break

                # Add user message to memory
                memory.chat_memory.add_message(HumanMessage(content=query))

                # Retrieve context (past messages + summary if long)
                past_messages = memory.load_memory_variables({})["history"]

                # Run agent with history
                response = await agent.ainvoke(
                    {
                        "messages": [
                            SystemMessage(content="You are a helpful assistant.")
                        ]
                        + past_messages
                        + [HumanMessage(content=query)]
                    }
                )

                memory.chat_memory.add_message(AIMessage(content=str(response)))
                try:
                    formatted = json.dumps(response, indent=2, cls=CustomEncoder)
                except Exception:
                    formatted = str(response)
                print("\nResponse:")
                print(formatted)


if __name__ == "__main__":
    asyncio.run(run_agent())
