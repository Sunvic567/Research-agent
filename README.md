# Multi-Agent Research System

A production-ready multi-agent system that conducts web research, analyzes findings, and generates comprehensive articles. Built with LangGraph and Google's Gemini 2.5 Flash.

## 🎯 What It Does

Takes a user query → Researches the web → Analyzes findings → Writes a complete article

**Example:**
```
Input: "Write about climate change impacts on coastal cities"
Output: Comprehensive, well-researched article with analysis and insights
```

## 🏗️ Architecture

### Three Specialized Agents

1. **Research Agent** - Searches the web using Tavily (max 5 sources per query)
2. **Analyzer Agent** - Structures and analyzes research findings
3. **Writer Agent** - Generates the final article

### Smart Orchestrator

Automatically determines which agents to run based on your query:
- `full_research` - All 3 agents (research → analyze → write)
- `quick_research` - Skip analysis (research → write)
- `research_only` - Just gather information
- `analyze_provided` - You provide data (analyze → write)
- `write_only` - You provide analysis (just write)

## 🚀 Quick Start

### Prerequisites
```bash
pip install langgraph langchain-google-genai tavily-python langsmith
```

### Environment Setup
Create a `.env` file:
```env
GOOGLE_API_KEY=your_google_api_key
TAVILY_API_KEY=your_tavily_api_key
LANGSMITH_API_KEY=your_langsmith_key  # Optional for tracing
```

### Basic Usage
```python
from orchestrator import app
import asyncio

async def main():
    result = await app.ainvoke({
        'user_query': "Explain FastAPI benefits for building APIs",
        'user_provided_data': None,  # Optional: provide your own data
        'task_type': None,  # Auto-detected
        'agents_to_run': [],
        'completed_agents': []
    })
    
    print(result['final_article'])

asyncio.run(main())
```

## 📊 Memory & Learning System

The system learns from every interaction and stores:

- **Research results** - Cached web searches for faster responses
- **Analyses** - Past analyses on similar topics
- **Articles** - Generated articles with quality scores
- **Learnings** - Success/failure patterns for each agent
- **Query cache** - Instant responses for repeated queries

### Benefits:
- ⚡ **Faster responses** - Cached results return instantly
- 🎯 **Better quality** - Agents learn from past successes
- 💡 **Context-aware** - Leverages similar past research

### Memory Operations:
```python
from database.agent_memory import MemoryManager

memory = MemoryManager()

# Get statistics
stats = memory.get_statistics()

# Find similar past research
similar = memory.get_similar_research("climate change", limit=5)

# Get best articles on a topic
articles = memory.get_best_articles("AI agents", limit=10)

# Clear old cache (older than 30 days)
memory.clear_old_cache(days=30)
```

## ⚙️ Configuration

### LLM Settings (`llm.py`)
```python
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",   # Fast & cost-effective
    temperature=0.3,             # Focused responses
    max_output_tokens=1024,      # Adjust for longer articles
)
```

**Model Options:**
- `gemini-2.5-flash` - Fast, affordable (recommended)
- `gemini-2.5-pro` - Higher quality, slower, more expensive

### Research Settings (`research_agent.py`)
```python
response = tavily_client.search(query, max_results=5)
```

Increase `max_results` for more comprehensive research (impacts speed and cost).

## 🔍 Monitoring with LangSmith

The system is fully instrumented with LangSmith tracing:

```python
@traceable(name="task_classifier")
async def task_classifier(state):
    # Auto-traced function
```

**View in LangSmith:**
- See execution flow for all agents
- Monitor token usage and costs
- Debug failures with full traces
- Track latency per agent

Set `LANGSMITH_API_KEY` in your environment to enable.

## 🎛️ Customization

### Modify Agent Prompts

Edit files in `prompts/`:
- `research_agent_prompt.py` - Research behavior
- `analyzer_agent_prompt.py` - Analysis structure
- `writer_agent_prompt.py` - Writing style

### Adjust Agent Behavior

**Make analyzer preserve more detail:**
```python
# In analyzer_agent_prompt.py
"""
Create a detailed analysis including:
- Specific statistics and data points
- Direct quotes from sources
- Concrete examples
DO NOT over-summarize.
"""
```

**Change writing style:**
```python
# In writer_agent_prompt.py
"""
Write in a [professional/casual/technical] tone.
Target length: [500/1000/2000] words.
Include: [sections/examples/statistics].
"""
```

## 📈 Performance Optimization

### Current Performance
- **Latency**: ~29 seconds for full research
- **Token Usage**: ~11,000 tokens per request
- **Breakdown**: Research (40%) + Analysis (20%) + Writing (40%)

### Quick Wins

**1. Parallel Web Searches** (Save 5-8s)
```python
# In research_agent.py, modify research_tool
async def parallel_search(queries):
    tasks = [tavily_client.search(q, max_results=5) for q in queries]
    return await asyncio.gather(*tasks)
```

**2. Use Faster Model for Analysis** (Save 2-3s)
```python
# Create separate LLM for analyzer
analyzer_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  # Already fast
    max_output_tokens=512,      # Reduce if analysis is too long
)
```

**3. Leverage Cache** (10x faster for repeated queries)
```python
# Already implemented - returns cached results instantly
cached = memory.get_cached_result(query)
if cached:
    return cached  # ~0.5s vs 29s
```

**4. Reduce Token Processing**
```python
# Pass only necessary data between agents
writer_input = {
    "analysis": analysis_output,     # Structure
    "key_research": top_3_sources,   # Not all 5 sources
}
```

## 🗃️ Database Schema

SQLite database at `memory/agent_memory.db`:

**Core Tables:**
- `conversations` - User queries and metadata
- `research_results` - Web search results
- `analyses` - Analysis outputs
- `articles` - Generated articles
- `learnings` - Agent improvement patterns
- `query_cache` - Fast lookup for repeated queries

## 🔧 Troubleshooting

### "Research agent not returning enough detail"
→ Increase `max_results` in `research_tool()` or run multiple searches

### "Writer produces generic content"
→ Pass raw research data to writer, not just analysis summary
→ Update writer prompt to demand specifics

### "Slow response times"
→ Enable query caching (already implemented)
→ Implement parallel searches
→ Use faster model for non-critical agents

### "Token limit exceeded"
→ Reduce `max_output_tokens` in `llm.py`
→ Filter research results before passing to analyzer
→ Limit number of past memories loaded

## 📝 Best Practices

**For Production:**
1. Set up proper error handling and retries
2. Monitor costs with LangSmith
3. Implement rate limiting for API calls
4. Regularly clear old cache (>30 days)
5. Track quality scores for articles

**For Development:**
1. Use LangSmith to debug agent interactions
2. Test with diverse query types
3. Evaluate output quality with DeepEval
4. A/B test different prompts

## 🚦 System Requirements

- Python 3.9+
- Internet connection (for Tavily searches)
- API keys for Google Gemini and Tavily
- ~100MB disk space for SQLite database
---

**Built with:** LangGraph • Google Gemini • Tavily • LangSmith