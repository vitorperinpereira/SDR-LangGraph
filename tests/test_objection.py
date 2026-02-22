
import pytest
from langchain_core.messages import HumanMessage
from app.graph import app_graph

@pytest.mark.asyncio
async def test_objection_flow():
    # 1. Start with a simple greeting to get to qualify
    inputs = {"messages": [HumanMessage(content="Oi")]}
    config = {"configurable": {"thread_id": "test_objection_1"}}
    
    # Run first step
    result = await app_graph.ainvoke(inputs, config=config)
    assert result["stage"] == "qualify"
    
    # 2. User expresses an objection (e.g. "muito caro")
    inputs = {"messages": [HumanMessage(content="Mas eu acho que é muito caro")]}
    result = await app_graph.ainvoke(inputs, config=config)
    
    # 3. Expect transition to 'objection' then loop back to 'collect_preferences' or 'qualify' based on logic.
    # Actually, my implementation sets stage="collect_preferences" in the return dict of 'objection' node.
    # But wait, the graph executes the node and returns the state update.
    # The 'objection' node runs, returns messages + stage="collect_preferences".
    # So the final stage after execution should reflect that.
    
    # Let's check the messages to ensure objection response was given
    last_message = result["messages"][-1].content
    assert "financeira" in last_message or "pagamento" in last_message
    
    # The user should now be in 'collect_preferences' stage (or ready to be moved there by router if re-run)
    # My objection node returns `stage: "collect_preferences"`. 
    # The graph won't automatically execute collect_preferences unless there is an edge or it's a superstep.
    # In LangGraph, if a node returns a state update, that update is applied.
    # If I want it to stop there and wait for user, that's fine.
    
    assert result["stage"] == "collect_preferences"
    
    # 4. If user now gives name/need, it might be handled by collect_preferences if the graph thinks it is there.
    # But 'collect_preferences' node expects 'preference' (morning/afternoon).
    # If the user was just redirected there effectively resetting the context to "let's schedule".
    
    # Let's try to schedule now
    inputs = {"messages": [HumanMessage(content="Prefiro de manhã")]}
    result = await app_graph.ainvoke(inputs, config=config)
    
    # Should move to waiting_choice
    assert result["stage"] == "waiting_choice"
    last_msg = result["messages"][-1].content.lower()
    assert "consegui" in last_msg or "tenho vagas" in last_msg or "horário" in last_msg or "escola" in last_msg or "ou" in last_msg
