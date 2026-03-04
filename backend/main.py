import json
import os
from dotenv import load_dotenv

load_dotenv()  # Reads backend/.env for local dev; no-op in Railway

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from groq import Groq

from monday import get_board_schema
from tools import TOOL_DEFINITIONS
from prompts import build_system_prompt
from analysis.deals import execute_deals_analysis
from analysis.workorders import execute_workorders_analysis
from analysis.crossboard import execute_cross_board_analysis

app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])


class ChatRequest(BaseModel):
    messages: list


def execute_tool(name: str, args: dict) -> dict:
    """Route a tool call by name to the correct execution function."""
    routes = {
        "get_board_schema": lambda: get_board_schema(args["board_id"]),
        "run_deals_analysis": lambda: execute_deals_analysis(args),
        "run_workorders_analysis": lambda: execute_workorders_analysis(args),
        "run_cross_board_analysis": lambda: execute_cross_board_analysis(args),
    }
    handler = routes.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}
    return handler()


def summarize_result(name: str, result: dict) -> str:
    """Return a short human-readable summary for the action log panel."""
    if name == "get_board_schema":
        return f"{len(result.get('columns', []))} columns found"
    if name in ("run_deals_analysis", "run_workorders_analysis"):
        return f"{result.get('total_rows_after_filter', '?')} rows → {len(result.get('results', []))} groups"
    if name == "run_cross_board_analysis":
        return f"{result.get('match_count', '?')} deals matched to WOs"
    return "Done"


async def agent_stream(messages: list):
    """
    Core agent loop. Sends messages to Groq, executes tool calls server-side,
    streams NDJSON events to the browser, and loops until Groq returns a final answer.
    """
    current_messages = [{"role": "system", "content": build_system_prompt()}, *messages]
    try:
        while True:
            response = groq_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=current_messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )
            choice = response.choices[0]

            if choice.finish_reason == "stop":
                yield (
                    json.dumps({"type": "answer", "content": choice.message.content})
                    + "\n"
                )
                break

            if choice.finish_reason == "tool_calls":
                current_messages.append(choice.message)
                for tool_call in choice.message.tool_calls:
                    name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)

                    yield (
                        json.dumps({"type": "tool_start", "tool": name, "args": args})
                        + "\n"
                    )
                    try:
                        result = execute_tool(name, args)
                    except Exception as error:
                        result = {"error": str(error)}
                    yield (
                        json.dumps(
                            {
                                "type": "tool_done",
                                "tool": name,
                                "summary": summarize_result(name, result),
                            }
                        )
                        + "\n"
                    )

                    current_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result),
                        }
                    )

    except Exception as error:
        yield (
            json.dumps({"type": "answer", "content": f"⚠️ Agent error: {error}"}) + "\n"
        )


@app.post("/chat")
async def chat(request: ChatRequest):
    """Stream NDJSON agent events for a chat request."""
    return StreamingResponse(
        agent_stream(request.messages), media_type="application/x-ndjson"
    )
