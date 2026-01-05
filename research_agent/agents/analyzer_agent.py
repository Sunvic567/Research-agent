from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, List
from .llm import llm
import logging
from prompts.analyzer_agent_prompt import analyzer_agent_prompt
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('analyzer_agent')  # Fixed: lowercase 'agent'

prompt = analyzer_agent_prompt
# Agent state
class analyzer_agent_state(TypedDict):
    message: List[BaseMessage]
    analysis: Optional[str]


async def Analyzer_Agent(state: analyzer_agent_state) -> analyzer_agent_state:
    '''Analyze the result of the searches for key details'''
    # Get existing messages
    messages: List[BaseMessage] = list(state.get("message", []))
    
    # Add system prompt
    system_msg = SystemMessage(content=prompt)
    all_messages = [system_msg] + messages

    try:
        logger.info('Agent processing research data...')
        llm_response = await llm.ainvoke(all_messages)
        
        # Append AI response as AIMessage
        messages.append(AIMessage(content=llm_response.content))
        
        return {
            'message': messages, 
            'analysis': llm_response.content
        }
        
    except Exception as e:
        logger.exception(f'Error processing input: {e}')
        error_msg = AIMessage(content=f"I encountered an error: {str(e)}")
        messages.append(error_msg)
        
        return {
            'message': messages,
            'analysis': f"Analysis failed: {str(e)}"
        }
        

graph = StateGraph(analyzer_agent_state)
graph.add_node('Analyzer_Agent', Analyzer_Agent)
graph.set_entry_point('Analyzer_Agent')
graph.add_edge('Analyzer_Agent', END)

app = graph.compile()
