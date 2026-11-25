import json
import os
from urllib import request
from openrouter import OpenRouter
from web import WEB_TOOLS, execute_tool as exec_web
from file_tool import FILE_TOOLS, execute_file_tool as exec_file

DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash-1017"
SYSTEM_PROMPT = "You are Openfuji, a small friendly fox that lives in the terminal. you answer minialistic and dont use fox emoji."
ALL_TOOLS = WEB_TOOLS + FILE_TOOLS
REASONING_LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
CFG_PATH = os.path.join(BASE_DIR, "config.json")
ARCHIVE_PATH = os.path.join(BASE_DIR, "archive.json")

config = {
    "BASE_URL": "https://openrouter.ai/api/v1",
    "API_KEY": "",
    "REASONING_LEVEL": "low",
    "ALLOWED": {},
}

def load_config():
    if not os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.write("OPENROUTER_API_KEY=\n")
        except Exception:
            pass
    else:
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

    config["API_KEY"] = os.environ.get("OPENROUTER_API_KEY", "")
    if os.environ.get("OPENROUTER_BASE_URL"):
        config["BASE_URL"] = os.environ["OPENROUTER_BASE_URL"]

    if os.path.exists(CFG_PATH):
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                saved = json.load(f)
                if saved.get("BASE_URL"): config["BASE_URL"] = saved["BASE_URL"]
                if isinstance(saved.get("ALLOWED"), dict): config["ALLOWED"] = saved["ALLOWED"]
        except Exception:
            pass

def save_api_key(key):
    config["API_KEY"] = key
    lines, found = [], False
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("OPENROUTER_API_KEY="):
                        lines.append(f"OPENROUTER_API_KEY={key}\n")
                        found = True
                    else:
                        lines.append(line)
        except Exception:
            pass
    if not found:
        lines.append(f"OPENROUTER_API_KEY={key}\n")
    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass

def save_config():
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump({"BASE_URL": config["BASE_URL"], "ALLOWED": config["ALLOWED"]}, f, indent=2)
    except Exception:
        pass

load_config()

def list_models():
    try:
        headers = {"Authorization": f"Bearer {config['API_KEY']}"} if config["API_KEY"] else {}
        req = request.Request(f"{config['BASE_URL'].rstrip('/')}/models", headers=headers)
        with request.urlopen(req, timeout=7) as res:
            return sorted(m["id"] for m in json.load(res)["data"])
    except Exception:
        return [DEFAULT_MODEL]

def exec_tool(name, args):
    res = exec_web(name, args)
    if not str(res).startswith("Unknown tool:"): return res
    res = exec_file(name, args)
    return res if res is not None else f"Unknown tool: {name}"

def ask_ai(messages, model, tool_handler=None):
    if not config["API_KEY"]:
        yield ("error", "error: no api key in .env or /settings")
        return

    client = OpenRouter(api_key=config["API_KEY"], server_url=config["BASE_URL"])
    send_args = {
        "model": model,
        "messages": messages,
        "tools": ALL_TOOLS,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    lvl = config["REASONING_LEVEL"]
    if lvl == "none":
        send_args["reasoning"] = {"enabled": False}
    elif lvl in REASONING_LEVELS:
        send_args["reasoning"] = {"effort": lvl}

    try:
        res = client.chat.send(**send_args)
    except TypeError:
        send_args.pop("reasoning", None)
        send_args.pop("stream_options", None)
        res = client.chat.send(**send_args)

    tc_buf, content, has_tools = {}, "", False

    for chunk in res:
        usage = getattr(chunk, "usage", None)
        if usage and getattr(usage, "completion_tokens", None):
            yield ("usage", usage.completion_tokens)

        if not chunk.choices: continue
        delta = chunk.choices[0].delta

        if getattr(delta, "reasoning", None):
            yield ("reasoning", delta.reasoning)

        if getattr(delta, "tool_calls", None):
            has_tools = True
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tc_buf:
                    tc_buf[idx] = {"id": tc.id or "", "type": "function", "function": {"name": getattr(tc.function, "name", "") or "", "arguments": getattr(tc.function, "arguments", "") or ""}}
                else:
                    if getattr(tc.function, "name", None): tc_buf[idx]["function"]["name"] += tc.function.name
                    if getattr(tc.function, "arguments", None): tc_buf[idx]["function"]["arguments"] += tc.function.arguments

        if getattr(delta, "content", None) and not has_tools:
            content += delta.content
            yield ("text", delta.content)

    if has_tools:
        calls = [tc_buf[i] for i in sorted(tc_buf.keys())]
        messages.append({"role": "assistant", "content": content, "tool_calls": calls})

        for tc in calls:
            name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            try:
                args = json.loads(raw_args) if raw_args else {}
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
            except Exception as e:
                messages.append({"role": "tool", "tool_call_id": tc["id"], "name": name, "content": f"Error: invalid JSON arguments ({e})"})
                continue

            yield ("tool", name)
            result = tool_handler(name, args) if tool_handler else exec_tool(name, args)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "name": name, "content": str(result)})

        yield from ask_ai(messages, model, tool_handler)
