import json
import re
import json_repair
from typing import List, Dict, Any
from gpt_researcher.config.config import Config
from gpt_researcher.utils.llm import create_chat_completion
from gpt_researcher.master.prompts import auto_agent_instructions, generate_search_queries_prompt

async def choose_agent(
    query, cfg, parent_query=None, cost_callback: callable = None, headers=None
):
    """
    Chooses the agent automatically
    Args:
        parent_query: In some cases the research is conducted on a subtopic from the main query.
        The parent query allows the agent to know the main context for better reasoning.
        query: original query
        cfg: Config
        cost_callback: callback for calculating llm costs

    Returns:
        agent: Agent name
        agent_role_prompt: Agent role prompt
    """
    query = f"{parent_query} - {query}" if parent_query else f"{query}"
    response = None  # Initialize response to ensure it's defined

    try:
        response = await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{auto_agent_instructions()}"},
                {"role": "user", "content": f"task: {query}"},
            ],
            temperature=0.15,
            llm_provider=cfg.llm_provider,
            llm_kwargs=cfg.llm_kwargs,
            cost_callback=cost_callback,
        )

        agent_dict = json.loads(response)
        return agent_dict["server"], agent_dict["agent_role_prompt"]

    except Exception as e:
        print("⚠️ Error in reading JSON, attempting to repair JSON")
        return await handle_json_error(response)

async def handle_json_error(response):
    try:
        agent_dict = json_repair.loads(response)
        if agent_dict.get("server") and agent_dict.get("agent_role_prompt"):
            return agent_dict["server"], agent_dict["agent_role_prompt"]
    except Exception as e:
        print(f"Error using json_repair: {e}")

    json_string = extract_json_with_regex(response)
    if json_string:
        try:
            json_data = json.loads(json_string)
            return json_data["server"], json_data["agent_role_prompt"]
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")

    print("No JSON found in the string. Falling back to Default Agent.")
    return "Default Agent", (
        "You are an AI critical thinker research assistant. Your sole purpose is to write well written, "
        "critically acclaimed, objective and structured reports on given text."
    )

def extract_json_with_regex(response):
    json_match = re.search(r"{.*?}", response, re.DOTALL)
    if json_match:
        return json_match.group(0)
    return None


async def get_sub_queries(
    query: str,
    agent_role_prompt: str,
    cfg,
    parent_query: str,
    report_type: str,
    cost_callback: callable = None,
):
    """
    Gets the sub queries
    Args:
        query: original query
        agent_role_prompt: agent role prompt
        cfg: Config
        parent_query:
        report_type:
        cost_callback:

    Returns:
        sub_queries: List of sub queries

    """
    max_research_iterations = cfg.max_iterations if cfg.max_iterations else 1
    response = await create_chat_completion(
        model=cfg.smart_llm_model,
        messages=[
            {"role": "system", "content": f"{agent_role_prompt}"},
            {
                "role": "user",
                "content": generate_search_queries_prompt(
                    query,
                    parent_query,
                    report_type,
                    max_iterations=max_research_iterations,
                ),
            },
        ],
        temperature=0.1,
        llm_provider=cfg.llm_provider,
        llm_kwargs=cfg.llm_kwargs,
        cost_callback=cost_callback,
    )

    sub_queries = json_repair.loads(response)

    return sub_queries