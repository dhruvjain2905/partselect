"""
Terminal chat interface for the PartSelect chatbot.

Usage:
    python scripts/chat.py

No frontend needed — this talks directly to the LangGraph graph
(not through HTTP) so you can demo and debug without running FastAPI.

Features:
- Rich formatted output with panels and colour
- Shows which tools were called and what they returned (debug mode)
- Shows session context (model number, appliance type) in the sidebar
- /help, /clear, /context, /debug, /quit commands
"""

import asyncio
import uuid
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns
from rich.markdown import Markdown
from rich.rule import Rule
from rich import box
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from app.agent.graph import graph
from app.agent.state import ChatState

console = Console(width=100)

SESSION_ID = str(uuid.uuid4())[:8]
DEBUG_MODE = True


def print_header():
    console.print()
    console.print(Panel(
        Text.assemble(
            ("PartSelect", "bold white"),
            (" Parts Specialist", "dim white"),
            ("\n", ""),
            ("Dishwasher & Refrigerator Parts Assistant", "dim cyan"),
        ),
        border_style="blue",
        padding=(0, 2),
    ))
    console.print(
        f"  [dim]Session:[/] [cyan]{SESSION_ID}[/]   "
        f"[dim]Commands:[/] /help  /context  /debug  /clear  /quit",
    )
    console.print()


def print_context(state: dict):
    """Print the current session context as a compact table."""
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column(style="dim")
    t.add_column(style="cyan")

    t.add_row("Appliance",   state.get("appliance_type") or "[dim]unknown[/]")
    t.add_row("Brand",       state.get("brand")          or "[dim]unknown[/]")
    conf = state.get("model_confidence", "none")
    model = state.get("model_number")
    model_str = f"{model} [dim]({conf})[/]" if model else "[dim]unknown[/]"
    t.add_row("Model",       model_str)

    console.print(Panel(t, title="[dim]Session Context[/]", border_style="dim", padding=(0, 1)))


def print_tool_call(tool_name: str, tool_input: dict, tool_output: str):
    """Show tool calls in debug mode."""
    # Truncate long outputs
    out_preview = tool_output[:800] + "..." if len(tool_output) > 800 else tool_output
    try:
        parsed = json.loads(out_preview)
        out_preview = json.dumps(parsed, indent=2)[:800]
    except Exception:
        pass

    console.print(Panel(
        f"[yellow]Input:[/]\n{json.dumps(tool_input, indent=2)}\n\n"
        f"[green]Output:[/]\n{out_preview}",
        title=f"[yellow]⚙ Tool: {tool_name}[/]",
        border_style="yellow",
        padding=(0, 1),
    ))


def print_assistant(content: str):
    console.print(Panel(
        Markdown(content),
        title="[blue]PartSelect Assistant[/]",
        border_style="blue",
        padding=(1, 2),
    ))


def print_user(content: str):
    console.print(f"\n[bold cyan]You:[/] {content}")


def print_help():
    help_text = """
[bold]Commands:[/]
  [cyan]/help[/]      Show this message
  [cyan]/context[/]   Show current session context (model number, appliance type etc.)
  [cyan]/debug[/]     Toggle debug mode (shows tool calls and SQL queries)
  [cyan]/clear[/]     Start a new session (clears all context)
  [cyan]/quit[/]      Exit

[bold]Example questions:[/]
  • Is part PS11750093 compatible with my WDT750SAHZ0?
  • My dishwasher top rack keeps sagging on the left side
  • What part do I need if my fridge ice maker stopped working?
  • How do I install the door balance link kit?
  • I have part number W10195840, is it still available?
  • My WRS325SDHZ0 is not making ice — what should I replace?
  • What are the most common repairs for the WDT750SAHZ0?
  • My dishwasher fills but never starts the wash cycle
    """
    console.print(Panel(help_text.strip(), title="[dim]Help[/]", border_style="dim"))


async def chat_turn(user_input: str, config: dict, current_state: dict) -> dict:
    """Send one message and return the updated state."""
    global DEBUG_MODE

    # Build the state update
    if not current_state:
        state_update: ChatState = {
            "messages": [HumanMessage(content=user_input)],
            "appliance_type": None,
            "brand": None,
            "model_number": None,
            "model_confidence": "none",
            "intent_category": None,
            "is_in_scope": True,
        }
    else:
        state_update = {"messages": [HumanMessage(content=user_input)]}

    with console.status("[dim]Thinking...[/]", spinner="dots"):
        result = await graph.ainvoke(state_update, config=config)

    # In debug mode, print tool calls
    if DEBUG_MODE:
        messages = result.get("messages", [])
        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    # Find the corresponding ToolMessage
                    tool_output = ""
                    for j in range(i + 1, len(messages)):
                        if isinstance(messages[j], ToolMessage) and messages[j].tool_call_id == tc["id"]:
                            tool_output = str(messages[j].content)
                            break
                    print_tool_call(tc["name"], tc.get("args", {}), tool_output)

    # Find the final assistant response
    reply = ""
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
            reply = msg.content
            break

    if reply:
        print_assistant(reply)

    return result


async def main():
    global SESSION_ID, DEBUG_MODE

    print_header()
    console.print("[dim]Type /help for commands or just start chatting.[/]\n")

    config = {"configurable": {"thread_id": SESSION_ID}}
    current_state = {}

    while True:
        try:
            user_input = console.input("[bold cyan]You:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            break

        if not user_input:
            continue

        # Commands
        if user_input.lower() == "/quit":
            console.print("[dim]Goodbye.[/]")
            break

        if user_input.lower() == "/help":
            print_help()
            continue

        if user_input.lower() == "/debug":
            DEBUG_MODE = not DEBUG_MODE
            status = "[green]ON[/]" if DEBUG_MODE else "[red]OFF[/]"
            console.print(f"[dim]Debug mode:[/] {status}")
            continue

        if user_input.lower() == "/context":
            print_context(current_state)
            continue

        if user_input.lower() == "/clear":
            SESSION_ID = str(uuid.uuid4())[:8]
            config = {"configurable": {"thread_id": SESSION_ID}}
            current_state = {}
            console.print(Rule(style="dim"))
            console.print(f"[dim]New session started. ID:[/] [cyan]{SESSION_ID}[/]")
            continue

        # Normal message
        try:
            current_state = await chat_turn(user_input, config, current_state)
        except Exception as e:
            console.print(f"[red]Error:[/] {e}")
            if DEBUG_MODE:
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
