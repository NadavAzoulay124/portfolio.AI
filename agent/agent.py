from __future__ import annotations

import os
import pathlib
import sys
from typing import List

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

# Allow running from different working directories by appending project root
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1].parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Import tool definitions
from agent.tools.tools import (  # type: ignore
    show_portfolio_tool,
    buy_stock_tool,
    sell_stock_tool,
    web_search_tool,
)


SYSTEM_PROMPT = """You are Finsight Assistant.
- Use tools to inspect the portfolio and fetch facts.
- NEVER execute Buy/Sell unless the user explicitly confirms in the same message.
- Be concise and base statements on tool results; avoid guessing.
"""


def _load_openai_key_from_env() -> None:
    """Load environment variables and ensure OpenAI key is present."""
    load_dotenv()  # load from .env if present
    # ChatOpenAI reads OPENAI_API_KEY from env automatically
    if not os.getenv("OPENAI_API_KEY"):
        # Allow downstream code to still attempt usage; but make it explicit for the user
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your environment or a .env file."
        )


def get_agent(model: str = "gpt-4", temperature: float = 0.0) -> AgentExecutor:
    """Create and return an AgentExecutor bound to portfolio + web search tools.

    - model: OpenAI model name compatible with langchain_openai.ChatOpenAI
    - temperature: Sampling temperature for the LLM (0.0 recommended for tools)
    """
    _load_openai_key_from_env()

    tools = [
        show_portfolio_tool,
        buy_stock_tool,
        sell_stock_tool,
        # web_search_tool,
    ]

    llm = ChatOpenAI(model=model, temperature=temperature)

    # Create tool names list for the prompt
    tool_names = [tool.name for tool in tools]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    
    # Bind the tools and tool_names to the prompt
    prompt = prompt.partial(
        tools="\n".join([f"- {tool.name}: {tool.description}" for tool in tools]),
        tool_names=", ".join(tool_names)
    )

    agent = create_openai_tools_agent(llm=llm, tools=tools, prompt=prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=6,
    )
    return executor


def run_cli() -> None:
    """Simple REPL to interact with the agent from the terminal."""
    print("Finsight Assistant - type 'exit' to quit")
    try:
        agent = get_agent()
    except Exception as e:
        print(f"Failed to initialize agent: {e}")
        return

    while True:
        try:
            user_input = input("You> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()  # newline
            break
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        try:
            result = agent.invoke({"input": user_input})
            output = result.get("output") if isinstance(result, dict) else result
            print(f"Agent> {output}")
        except Exception as e:
            print(f"Agent error: {e}")


if __name__ == "__main__":
    run_cli()


