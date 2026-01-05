from typing import TypedDict, List, Optional,Annotated
import logging
from langgraph.graph import StateGraph, END, add_messages
from langchain_core.tools import tool
from tavily import TavilyClient
from settings.config import tavily_key
from .llm import llm
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from langgraph.prebuilt import ToolNode
 
from prompts.reasearch_agent_prompt import research_agent_prompt
          
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("research_agent")

prompt = research_agent_prompt


# Agent state - Use add_messages reducer
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    research_result: Optional[str]


# The provided tool
@tool
def research_tool(query: str) -> str:
    """Search the web for information about a topic using Tavily and return aggregated text."""
    if not query:
        raise ValueError("Please provide a non-empty query.")
    tavily_client = TavilyClient(api_key=tavily_key)
    try:
        response = tavily_client.search(query, max_results=5)
        results = []
        for r in response.get("results", []):
            results.append(
                "Title: {}\nContent: {}\nURL: {}".format(
                    r.get("title", "N/A"),
                    r.get("content", "N/A"),
                    r.get("url", "N/A"),
                )
            )
        return "\n---\n".join(results) if results else "No results found."
    except Exception as e:
        logger.exception("Error using research tool")
        raise RuntimeError(f"Tavily search failed: {e}")


# Give the LLM the available tools
tools = [research_tool]
llm_with_tools = llm.bind_tools(tools)


# The agent node
async def research_agent(state: AgentState) -> dict:
    """Calls the LLM with tools."""
    messages = state.get("messages", [])
    
    # Add system message at the start if not present
    if not messages or not isinstance(messages[0], SystemMessage):
        system_msg = SystemMessage(content=prompt)
        messages = [system_msg] + messages
    
    try:
        logger.info("Agent processing query...")
        llm_response = await llm_with_tools.ainvoke(messages)
        logger.info("Agent response type: %s", type(llm_response))

        # If the LLM requested tools, return the response
        if hasattr(llm_response, "tool_calls") and llm_response.tool_calls:
            logger.info("LLM requested tools: %s", llm_response.tool_calls)
            return {"messages": messages + [llm_response]}

        return {"messages": messages + [llm_response], "research_result": llm_response.content}

    except Exception as e:
        logger.exception("Error in research_agent")
        error_msg = AIMessage(content=f"I encountered an error: {e}")
        return {"messages": [error_msg], "research_result": str(e)}


# Routing logic
def should_continue(state: AgentState) -> str:
    """Return 'continue' if the last message requested tools, otherwise 'end'."""
    messages = state.get("messages", [])
    if not messages:
        logger.info("No messages in state; ending.")
        return "end"
    
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        logger.info("Routing to tools")
        return "continue"
    
    logger.info("Routing to end")
    return "end"


# Build the graph
graph = StateGraph(AgentState)
graph.add_node("agent", research_agent)
graph.add_node("tools", ToolNode(tools))  # ← Pass tools directly
graph.set_entry_point("agent")
graph.add_conditional_edges("agent", should_continue, {"continue": "tools", "end": END})
graph.add_edge("tools", "agent")

app = graph.compile()