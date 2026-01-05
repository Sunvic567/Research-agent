from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, List
from .llm import llm
import logging
from prompts.writer_agent_prompt import writer_agent_prompt as prompt
from langchain_core.messages import SystemMessage, BaseMessage, AIMessage, HumanMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('writer_agent') 

 

# Agent state
class writer_agent_state(TypedDict):
    message: List[BaseMessage]
    article: Optional[str]

async def writing_agent(state: writer_agent_state) -> writer_agent_state:
    '''Creates a comprehensive article or summary from the analysis'''  
    messages: List[BaseMessage] = list(state.get("message", []))
    
    # Add system prompt
    system_msg = SystemMessage(content=prompt)
    all_messages = [system_msg] + messages
    
    try:
        logger.info('Agent processing analysis data...')
        llm_response = await llm.ainvoke(all_messages)
        
        # Append AI response as AIMessage
        messages.append(AIMessage(content=llm_response.content))
        
        return {
            'message': messages, 
            'article': llm_response.content
        }
        
    except Exception as e:
        logger.exception(f'Error processing input: {e}')
        error_msg = AIMessage(content=f"I encountered an error: {str(e)}")
        messages.append(error_msg)
        
        return {
            'message': messages,
            'article': f"Writing failed: {str(e)}" 
        }

# Fixed: Remove space and quotes
graph = StateGraph(writer_agent_state)
graph.add_node('writing_agent', writing_agent)
graph.set_entry_point('writing_agent')
graph.add_edge('writing_agent', END)

app = graph.compile()
