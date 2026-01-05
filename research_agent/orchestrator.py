from typing import TypedDict, Optional, List
from agents.llm import llm
from langgraph.graph import StateGraph, END
import logging
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
import asyncio
from agents.research_agent import app as research_app
from agents.analyzer_agent import app as analyzer_app
from agents.writer_agent import app as writer_app
from database.agent_memory import MemoryManager
from langsmith import Client, traceable
from settings.config import langsmith_key


memory = MemoryManager()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('orchestrator')

class OrchestratorState(TypedDict):
    user_query: str
    task_type: Optional[str]
    user_provided_data: Optional[str]
    research_result: Optional[str]
    analysis: Optional[str]
    final_article: Optional[str]
    agents_to_run: List[str]
    completed_agents: List[str]
    conversation_id: Optional[int]

@traceable(name="task_classifier")
async def task_classifier(state: OrchestratorState) -> dict:
    """Decides which agents to run based on user query"""
    logger.info('Classifying task...')
     # Start a new conversation in memory
    conv_id = memory.start_conversation(
        user_query=state['user_query'],
        user_provided_data=state.get('user_provided_data')
    )
    
    # Check if we have similar past queries (optional speedup)
    cached_result = memory.get_cached_result(state['user_query'])
    if cached_result:
        logger.info('Found cached resul for similar query')


    classifier_prompt = f"""
    Analyze this user query and determine the task type:
    
    Query: {state['user_query']}
    User provided data: {state.get('user_provided_data', 'None')}
    
    Task types:
    - full_research: Need to research, analyze, and write
    - quick_research: Need to research and write (skip analysis)
    - research_only: Only need research
    - analyze_provided: User provided data, analyze and write
    - write_only: User provided analysis, just write
    
    Respond with ONLY the task type.
    """
    
    try:
        response = await llm.ainvoke([HumanMessage(content=classifier_prompt)])
        task_type = response.content.strip().lower()
        
        # Map task type to agents
        task_mapping = {
            'full_research': ['research', 'analyzer', 'writer'],
            'quick_research': ['research', 'writer'],
            'research_only': ['research'],
            'analyze_provided': ['analyzer', 'writer'],
            'write_only': ['writer']
        }
        
        agents = task_mapping.get(task_type, ['research', 'analyzer', 'writer'])
        
        logger.info(f'Task type: {task_type}, Agents: {agents}')
        
        return {
            'task_type': task_type,
            'agents_to_run': agents,
            'completed_agents': [],
             'conversation_id': conv_id
        }
    except Exception as e:
        logger.error(f'Error in classifier: {e}')
        # Default to full research on error
        return {
            'task_type': 'full_research',
            'agents_to_run': ['research', 'analyzer', 'writer'],
            'completed_agents': []
        }

@traceable(name="search_node")
async def search_node(state: OrchestratorState) -> dict:
    '''Perform research based on user query'''
    logger.info('Starting research agent...')

     # Check for similar past research to help the agent
    similar_research = memory.get_similar_research(state['user_query'], limit=3)
    
    context_hint = ""
    if similar_research:
        context_hint = "\n\nPast related research found:\n"
        for sr in similar_research:
            context_hint += f"- Query: {sr['query']}\n  Key points: {sr['results'][:200]}...\n"

    try:
        search_result = await research_app.ainvoke({
            'messages': [HumanMessage(content=state.get('user_query'))],
            'research_result': None
        })
        
        # Extract the actual research result string
        result = search_result.get('research_result', 'No research result')
        
        # Save research to memory
        if state.get('conversation_id'):
            memory.save_research(
                conversation_id=state['conversation_id'],
                query=state['user_query'],
                results=result,
                sources=[]  # You can extract sources from research_result if needed
            )
            
            # Save successful pattern as learning
            memory.save_learning(
                agent_name='research',
                lesson=f'Successfully researched: {state["user_query"][:100]}',
                context=f'Returned {len(result)} characters of data',
                success_pattern=True
            )
        
        # Update completed agents
        completed = state.get('completed_agents', [])
        completed.append('research')
        
        logger.info('Research completed')
        return {
            'research_result': result,
            'completed_agents': completed
        }
    except Exception as e:
        logger.error(f'Error calling search agent: {e}')
        # Log failure as learning
        if state.get('conversation_id'):
            memory.save_learning(
                agent_name='research',
                lesson=f'Failed to research: {str(e)}',
                context=state['user_query'],
                success_pattern=False
            )
        return {
            'research_result': f"Research failed: {str(e)}",
            'completed_agents': state.get('completed_agents', []) + ['research']
        }

@traceable(name="analyse_node")
async def analyse_node(state: OrchestratorState) -> dict:
    """Analyzes research data or provided data"""
    logger.info('Starting analysis agent...')
    
    # Determine input
    if state.get('research_result'):
        input_text = state['research_result']
    elif state.get('user_provided_data'):
        input_text = state['user_provided_data']
    else:
        input_text = state['user_query']
    # Get past analyses on similar topics for context
    past_analyses = memory.get_past_analyses(state['user_query'], limit=2)
    
    context_hint = ""
    if past_analyses:
        context_hint = "\n\nPrevious analyses on similar topics:\n"
        for pa in past_analyses:
            context_hint += f"- {pa['original_query']}\n  Key insights: {', '.join(pa['key_insights'][:3]) if pa['key_insights'] else 'N/A'}\n"
    
    try:
        analysis_result = await analyzer_app.ainvoke({
            'message': [HumanMessage(content=input_text)],
            'analysis': None
        })
        
        # Extract analysis string
        result = analysis_result.get('analysis', 'No analysis result')
        
        # Save analysis to memory
        if state.get('conversation_id'):
            # Extract key insights (simple extraction - you can make this smarter)
            key_insights = []
            if '**Finding' in result or '## Key Findings' in result:
                # Extract first few lines as insights
                lines = result.split('\n')
                key_insights = [line.strip() for line in lines if line.strip() and len(line) > 20][:5]
            
            memory.save_analysis(
                conversation_id=state['conversation_id'],
                analysis=result,
                key_insights=key_insights
            )
            
            # Save successful pattern
            memory.save_learning(
                agent_name='analyzer',
                lesson=f'Successfully analyzed {len(input_text)} chars of data',
                context=state['user_query'][:100],
                success_pattern=True
            )

        # Update completed agents
        completed = state.get('completed_agents', [])
        completed.append('analyzer')
        
        logger.info('Analysis completed')
        return {
            'analysis': result,
            'completed_agents': completed
        }
    except Exception as e:
        logger.error(f'Error analyzing data: {e}')
        # Log failure
        if state.get('conversation_id'):
            memory.save_learning(
                agent_name='analyzer',
                lesson=f'Analysis failed: {str(e)}',
                context=state['user_query'],
                success_pattern=False
            )
        return {
            'analysis': f"Analysis failed: {str(e)}",
            'completed_agents': state.get('completed_agents', []) + ['analyzer']
        }

@traceable(name="writer_node")
async def writer_node(state: OrchestratorState) -> dict:
    '''Writes the final report'''
    logger.info('Starting writing agent...')
    
    # Determine input
    if state.get('research_result'):
        input_text = state['research_result']
    else:
        input_text = state['user_query']
    
    # Get best past articles for style reference
    best_articles = memory.get_best_articles(topic=state['user_query'], limit=2)
    
    context_hint = ""
    if best_articles:
        context_hint = "\n\nHigh-quality past articles for style reference:\n"
        for article in best_articles:
            context_hint += f"- Quality: {article['quality_score']}, Words: {article['word_count']}\n"
            context_hint += f"  Preview: {article['article'][:300]}...\n"
    
    try:
        writer_result = await writer_app.ainvoke({
            'message': [HumanMessage(content=input_text)],
            'article': None
        })
        
        # Extract article string
        result = writer_result.get('article', 'No article generated')

        
        # Save article to memory
        if state.get('conversation_id'):
            memory.save_article(
                conversation_id=state['conversation_id'],
                article=result,
            )
            
            # Save successful pattern
            memory.save_learning(
                agent_name='writer',
                context=state['user_query'][:100],
                success_pattern=True,
                lesson=f'Wrote article of length {len(result)}'
            )
            
            # Cache the result for similar future queries
            memory.cache_result(state['user_query'], result)
        
        # Update completed agents
        completed = state.get('completed_agents', [])
        completed.append('writer')
        
        logger.info('Writing completed')
        return {
            'final_article': result,
            'completed_agents': completed
        }
    except Exception as e:
        logger.error(f'Error writing article: {e}')

         # Log failure
        if state.get('conversation_id'):
            memory.save_learning(
                agent_name='writer',
                lesson=f'Writing failed: {str(e)}',
                context=state['user_query'],
                success_pattern=False
            )
        return {
            'final_article': f"Writing failed: {str(e)}",
            'completed_agents': state.get('completed_agents', []) + ['writer']
        }

@traceable(name="route_next_agent")
def route_next_agent(state: OrchestratorState) -> str:
    """Routes to the next agent or END"""
    agents_to_run = state.get('agents_to_run', [])
    completed = state.get('completed_agents', [])
    
    logger.info(f'Routing - To run: {agents_to_run}, Completed: {completed}')
    
    # Find next agent
    for agent in agents_to_run:
        if agent not in completed:
            logger.info(f'Routing to: {agent}')
            return agent
    
    # All done
    logger.info('All agents completed, ending')
    return 'end'


# Build graph
graph = StateGraph(OrchestratorState)
graph.add_node('task_classifier', task_classifier)
graph.add_node('search_node', search_node)
graph.add_node('analyse_node', analyse_node)
graph.add_node('writer_node', writer_node)

graph.set_entry_point('task_classifier')

# Universal routing from any node
routing_map = {
    'research': 'search_node',
    'analyzer': 'analyse_node',
    'writer': 'writer_node',
    'end': END
}

graph.add_conditional_edges('task_classifier', route_next_agent, routing_map)
graph.add_conditional_edges('search_node', route_next_agent, routing_map)
graph.add_conditional_edges('analyse_node', route_next_agent, routing_map)
graph.add_conditional_edges('writer_node', route_next_agent, routing_map)

# Compile
app = graph.compile()

# Test
if __name__ == "__main__":
    import asyncio
    
    test_state = {
        'user_query': "Write a detailed article on the impacts of climate change on coastal cities.",
        'task_type': None,
        'user_provided_data': None,
        'research_result': None,
        'analysis': None,
        'final_article': None,
        'agents_to_run': [],
        'completed_agents': []
    }
    
    result = asyncio.run(app.ainvoke(test_state))
    
    print("\n=== Results ===")
    print(f"Task Type: {result['task_type']}")
    print(f"Agents Run: {result['completed_agents']}")
    print(f"\nFinal Article:\n{result['final_article']}")