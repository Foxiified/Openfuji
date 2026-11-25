import codecs
import json
import os
import re
import queue
import time
from datetime import datetime

_orig_decoder = codecs.getincrementaldecoder
def _safe_decoder(encoding):
    cls = _orig_decoder(encoding)
    if encoding.lower().replace("-", "") == "utf8":
        return lambda errors="strict": cls("ignore" if errors == "strict" else errors)
    return cls
codecs.getincrementaldecoder = _safe_decoder

from ai import DEFAULT_MODEL, SYSTEM_PROMPT, REASONING_LEVELS, ARCHIVE_PATH, ask_ai, list_models, config, save_config, save_api_key
from files import add_file, files_box, made, split_reply
from rich.text import Text
from textual import work
from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, OptionList, Static
from textual.reactive import reactive
from textual.worker import get_current_worker
from rich import box
from rich.table import Table

PURPLE, DIM, DIMMER = "#b18be8", "#8a8a99", "#5d5d6b"

chat_coding = "Cooking"
done_coding = "Ta da"
safemode_disable = "Id be careful"

COMMANDS = [
    ("/files", "files made this session"),
    ("/model", "choose the model"),
    ("/chat", "select and view previous logs"),
    ("/clear", "clear memory and start new log"),
    ("/safemode", "toggle safe mode (approval for file edits)"),
    ("/reasoning", "set reasoning effort level"),
    ("/settings", "configure api key, base url, and tps"),
]

def foxtext():
    txt = Text(no_wrap=True)
    for y in range(0, len(FOX_ROWS), 2):
        for top, bot in zip(FOX_ROWS[y], FOX_ROWS[y + 1]):
            t, b = FOX_PALETTE.get(top), FOX_PALETTE.get(bot)
            if t and b: txt.append("\u2580", style=f"{t} on {b}")
            elif t: txt.append("\u2580", style=t)
            elif b: txt.append("\u2584", style=b)
            else: txt.append(" ")
        txt.append("\n")
    txt.rstrip()
    return txt

def status_left_text(model, safe):
    txt = Text(no_wrap=True)
    txt.append(f" {model} ", style="bold #121212 on #d97736")
    if safe:
        txt.append(" ")
        txt.append(" ● safemode ", style="bold #121212 on #ff6b6b")

    for k, lbl in [("ctrl+o", "reasoning"), ("esc", "stop"), ("ctrl+c", "exit")]:
        txt.append(f"  {k}", style=f"bold {PURPLE}").append(f" {lbl}", style=f"bold {DIM}")
    return txt

def status_right_text(show_tps, tps):
    txt = Text(no_wrap=True)
    if show_tps:
        txt.append(f" {tps:.1f} t/s ", style="bold #121212 on #7fd88f")
    return txt

def colour_command(line):
    txt, in_qt = Text(), False
    for i, w in enumerate(line.split(" ")):
        if i: txt.append(" ")
        if w.startswith('"'): in_qt = True
        txt.append(w, style="#7d7d8a" if in_qt else ("#a9a9b3" if i == 0 else "#b0b0b0"))
        if w.endswith('"'): in_qt = False
    return txt

def plain_line(line):
    txt = Text()
    for i, part in enumerate(line.replace("**", "").lstrip("# ").split("`")):
        txt.append(part, style="#5fd7d7" if i % 2 else "#e6e6e6")
    return txt

class CodeBlock(Vertical):
    def __init__(self, code, lang="code"):
        super().__init__()
        self.code, self.lang = code, lang
    def compose(self):
        with Horizontal(classes="code-header"): yield Static(self.lang, classes="code-lang")
        yield Static(self.code, classes="code-content")

class ReasoningBlock(Static):
    def __init__(self, content):
        super().__init__()
        self.txt = content

    def on_mount(self):
        self.display = getattr(self.app, "show_reasoning", False)
        self.update(Text("▼ Reasoning:\n", style="bold #5d5d6b").append(self.txt, style="#8a8a99"))

    def toggle(self, state):
        self.display = state

class Openfuji(App):
    CSS = """
    * { background: ansi_default; }
    Screen { layout: vertical; }
    #stage { height: 21; border: none; margin: 0; padding: 0; }
    #fox { width: 36; height: 19; margin: 1 0 0 1; }
    #bubble-col { margin: 4 0 0 3; width: auto; }
    #bubble { border: round #b18be8; padding: 0 1; width: auto; max-width: 60; color: white; text-style: bold; }
    #tail { color: #b18be8; padding: 0 2; }
    #log { height: 1fr; padding: 0 2; border: none; margin: 0; }
    #log > Static { width: 100%; height: auto; }
    #log > .user { margin-top: 2; }
    #log > .reply { padding-left: 2; }
    #bottom { height: auto; padding: 0 2; margin-bottom: 1; border: none; }
    #commands { display: none; max-height: 9; border: round #b18be8; padding: 0 1; }
    #commands > .option-list--option-highlighted { background: #2f2540; }

    #approval-box { display: none; height: auto; border: round #b18be8; padding: 0 1; margin-bottom: 1; }
    #approval-box.-active { display: block; }
    #approval-title { padding: 0 1; }
    #approval-list { height: auto; max-height: 5; border: none; padding: 0; }
    #approval-list > .option-list--option-highlighted { background: #2f2540; }

    Input { border: round #4a4a55; border-title-color: #8a8a99; border-subtitle-color: #5d5d6b; padding: 0 1; }
    Input:focus { border: round #b18be8; border-title-color: #b18be8; }
    Input > .input--cursor { background: #b18be8; color: #121212; }
    Input > .input--placeholder { color: #6b6b78; }
    #status { height: 1; padding: 0 1; }
    #status-left { width: 1fr; overflow: hidden; }
    #status-right { width: auto; }
    CodeBlock { border: round #4a4a55; margin: 1 0; }
    .code-header { height: 1; dock: top; background: #33333b; }
    .code-lang { width: 1fr; padding-left: 1; color: #8a8a99; text-style: bold; }
    .code-content { padding: 0 1; }
    ReasoningBlock { border-left: heavy #5d5d6b; padding-left: 1; margin: 0 0 1 2; display: none; }
    """
    BINDINGS = [
        Binding("escape", "escape", show=False, priority=True), Binding("ctrl+c", "quit", show=False, priority=True),
        Binding("up", "list_up", show=False, priority=True), Binding("down", "list_down", show=False, priority=True),
        Binding("tab", "complete", show=False, priority=True), Binding("ctrl+o", "toggle_reasoning", show=False, priority=True),
    ]

    model_name = DEFAULT_MODEL
    safe = reactive(True)
    show_reasoning = False
    show_tps = True
    current_tps = 0.0

    def __init__(self):
        super().__init__(ansi_color=True, driver_class=None)
        self.matches, self.models = [], [DEFAULT_MODEL]
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.archive_file = ARCHIVE_PATH
        self.session_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.syncing = False
        self.chat_worker = None

    def watch_safe(self, safe: bool):
        self.update_status()

    def action_toggle_reasoning(self):
        self.show_reasoning = not self.show_reasoning
        for b in self.query(ReasoningBlock): b.toggle(self.show_reasoning)
        self.call_after_refresh(self.query_one("#log", VerticalScroll).scroll_end, animate=False)

    def save_to_archive(self, role, content):
        archive = {}
        try:
            if os.path.exists(self.archive_file):
                with open(self.archive_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    archive = {"legacy_log": data} if isinstance(data, list) else data
            archive.setdefault(self.session_id, []).append({"role": role, "content": content})
            if len(archive) > 30:
                for k in list(archive.keys())[:-30]: del archive[k]
            with open(self.archive_file, "w", encoding="utf-8") as f:
                json.dump(archive, f, indent=2)
        except Exception: pass

    def compose(self):
        with Horizontal(id="stage"):
            yield Static(foxtext(), id="fox")
            with Vertical(id="bubble-col"):
                yield Static("Hello, I am Openfuji!", id="bubble")
                yield Static(".", id="tail")
        with VerticalScroll(id="log"): pass
        with Vertical(id="bottom"):
            yield OptionList(id="commands")
            with Vertical(id="approval-box"):
                yield Static(id="approval-title")
                yield OptionList(id="approval-list")
            yield Input(placeholder="Type a message...  (/ for commands)")
            with Horizontal(id="status"):
                yield Static(id="status-left")
                yield Static(id="status-right")

    def on_mount(self):
        self.query_one("#commands", OptionList).can_focus = False
        box = self.query_one(Input)
        box.border_title, box.border_subtitle, box.cursor_blink = "you", "", False
        box.focus()
        self.update_status()
        self.load_models()

    @work(thread=True)
    def load_models(self):
        self.models = list_models()

    def say(self, msg):
        self.query_one("#bubble", Static).update(msg)

    def update_status(self):
        self.query_one("#status-left", Static).update(status_left_text(self.model_name, self.safe))
        self.query_one("#status-right", Static).update(status_right_text(self.show_tps, self.current_tps))

    def _approval_active(self):
        return self.query_one("#approval-box").has_class("-active")

    def check_action(self, act, params):
        if act in ("list_up", "list_down", "complete"):
            return bool(self.matches) or self._approval_active()
        return True

    def _settings_items(self):
        key = config["API_KEY"]
        masked = f"{key[:6]}...{key[-3:]}" if len(key) > 10 else ("set" if key else "not set")
        return [
            ("/settings api_key", f"({masked}) type key & enter"),
            ("/settings base_url", f"({config['BASE_URL']}) edit & enter"),
            ("/settings tps", f"({'on' if self.show_tps else 'off'}) press enter to toggle"),
        ]

    def refresh_menu(self, raw_val):
        txt, self.matches = raw_val.lower(), []

        if txt.startswith("/model "):
            q = txt[7:].strip()
            self.matches = [(f"/model {m}", "● current" if m == self.model_name else "") for m in self.models if q in m.lower()]
        elif txt.startswith("/reasoning "):
            q = txt[11:].strip()
            self.matches = [(f"/reasoning {lvl}", "● current" if lvl == config["REASONING_LEVEL"] else "") for lvl in REASONING_LEVELS if q in lvl]
        elif txt.startswith("/settings "):
            rest = txt[10:]
            if rest.startswith(("api_key ", "base_url ")):
                self.matches = []
            else:
                q = rest.strip()
                self.matches = [item for item in self._settings_items() if q in item[0]]
        elif txt.startswith("/chat "):
            q, sessions = txt[6:].strip(), []
            try:
                if os.path.exists(self.archive_file):
                    with open(self.archive_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict): sessions = list(data.keys())
            except Exception: pass
            self.matches = [(f"/chat {s}", "● active log" if s == self.session_id else "saved log") for s in reversed(sessions) if q in s.lower()]
        elif txt.startswith("/") and " " not in txt:
            self.matches = [c for c in COMMANDS if c[0].startswith(txt)]

        box = self.query_one("#commands", OptionList)
        box.clear_options()
        if self.matches:
            box.add_options([
                Text.assemble(
                    (n.split(" ")[0].ljust(11) if " " in n else n.ljust(11), f"bold {PURPLE}"),
                    (f" {n.split(' ', 1)[1]}" if " " in n else "", "bold white"),
                    (f"  {d}", DIM)
                ) for n, d in self.matches
            ])
            box.highlighted = 0
        box.display = bool(self.matches)

    def on_input_changed(self, e):
        if self.syncing: return
        self.refresh_menu(e.value)

    def _select_menu_item(self, val):
        box = self.query_one(Input)
        if val in ("/chat", "/model", "/reasoning", "/settings"):
            self._open_sub_input(f"{val} ")
            if val == "/chat" and not self.matches:
                self.say("no saved logs yet")
        elif val == "/settings base_url":
            self._open_sub_input(f"/settings base_url {config['BASE_URL']}")
            self.say("edit base url & press enter")
        elif val == "/settings api_key":
            self._open_sub_input("/settings api_key ")
            self.say("type api key & press enter")
        else:
            box.value = ""
            self.query_one("#commands", OptionList).display, self.matches = False, []
            self.run_command(val)

    def action_list_up(self):
        if self._approval_active():
            self.query_one("#approval-list", OptionList).action_cursor_up()
            return
        self.query_one("#commands", OptionList).action_cursor_up()

    def action_list_down(self):
        if self._approval_active():
            self.query_one("#approval-list", OptionList).action_cursor_down()
            return
        self.query_one("#commands", OptionList).action_cursor_down()

    def action_complete(self):
        if self._approval_active():
            opts = self.query_one("#approval-list", OptionList)
            choices = ["approve", "deny", "allow_workspace"]
            if opts.highlighted is not None and 0 <= opts.highlighted < len(choices):
                self._resolve_approval(choices[opts.highlighted])
            return
        cmd = self.query_one("#commands", OptionList)
        if cmd.highlighted is not None and self.matches:
            self._select_menu_item(self.matches[cmd.highlighted][0])

    def on_option_list_option_selected(self, e):
        if e.option_list.id == "approval-list":
            choices = ["approve", "deny", "allow_workspace"]
            if 0 <= e.option_index < len(choices):
                self._resolve_approval(choices[e.option_index])
            return
        if e.option_index < len(self.matches):
            self._select_menu_item(self.matches[e.option_index][0])
            self.query_one(Input).focus()

    def _resolve_approval(self, choice):
        box = self.query_one("#approval-box")
        if not box.has_class("-active"): return
        box.remove_class("-active")
        self.say(chat_coding)
        self.query_one(Input).focus()
        if hasattr(self, "approval_queue"):
            self.approval_queue.put(choice)

    def load_session_into_chat(self, session_name, messages):
        log = self.query_one("#log", VerticalScroll)
        for child in list(log.children):
            if child.id != "stage": child.remove()

        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in messages:
            role, content = m.get("role"), m.get("content")
            if role not in ("user", "assistant") or content is None: continue
            text_val = str(content)
            if not text_val.strip(): continue
            self.history.append({"role": role, "content": text_val})
            self.add_line(Text.assemble(("> ", "#cfcfcf"), (text_val, "bold white")) if role == "user" else Text(text_val, style="#a9a9b3"), classes="user" if role == "user" else "reply")

        self.session_id = session_name
        self.say(f"loaded: {session_name}")

    def _open_sub_input(self, prefix):
        box = self.query_one(Input)
        self.syncing = True
        box.value = prefix
        box.cursor_position = len(prefix)
        self.syncing = False
        self.refresh_menu(prefix)

    def run_command(self, cmd):
        name, _, arg = cmd.partition(" ")
        arg = arg.strip()
        if name == "/settings":
            if not arg:
                self._open_sub_input("/settings ")
                self.say("choose setting with arrows")
                return
            key, _, val = arg.partition(" ")
            val = val.strip()
            if key == "api_key":
                if not val:
                    self._open_sub_input("/settings api_key ")
                    self.say("type api key & press enter")
                else:
                    save_api_key(val)
                    self.load_models()
                    self.say("api key saved")
            elif key == "base_url":
                if not val:
                    self._open_sub_input(f"/settings base_url {config['BASE_URL']}")
                    self.say("edit base url & press enter")
                else:
                    config["BASE_URL"] = val
                    save_config()
                    self.load_models()
                    self.say("base url saved")
            elif key == "tps":
                self.show_tps = not self.show_tps
                self.update_status()
                self.say(f"tps: {'on' if self.show_tps else 'off'}")
            else:
                self.say("unknown setting")
        elif name == "/safemode":
            self.safe = not self.safe
            self.say("Safemode enabled" if self.safe else safemode_disable)
        elif name == "/reasoning":
            if not arg:
                self._open_sub_input("/reasoning ")
                self.say("select reasoning level")
            elif arg in REASONING_LEVELS:
                config["REASONING_LEVEL"] = arg
                self.say(f"reasoning: {arg}")
            else:
                self.say(f"use: {', '.join(REASONING_LEVELS)}")
        elif name == "/chat":
            if not arg:
                self._open_sub_input("/chat ")
                self.say("select a chat log" if self.matches else "no saved logs yet")
                return
            try:
                with open(self.archive_file, "r", encoding="utf-8") as f: archive = json.load(f)
                if isinstance(archive, dict) and arg in archive:
                    self.load_session_into_chat(arg, archive[arg])
                else: self.say(f"log '{arg}' not found")
            except Exception: self.say("logs not found")
        elif name == "/clear":
            self.history, self.session_id = [{"role": "system", "content": SYSTEM_PROMPT}], datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.add_line(Text("--- CHAT CLEARED (NEW LOG) ---", style=f"bold {PURPLE}"), classes="reply")
            self.say("memory cleared")
        elif name == "/files":
            if made:
                self.add_line(files_box(made), classes="reply")
                self.say("showing files")
            else: self.say("no files yet")
        elif name == "/model":
            if not arg:
                self._open_sub_input("/model ")
            elif len(self.models) > 1 and arg not in self.models:
                self.say(f"unknown model: {arg}")
            else:
                self.model_name = arg
                self.update_status()
                self.say(f"model: {arg}")
        else: self.say(f"Unknown command: {name}")

    def add_line(self, content, classes=""):
        log = self.query_one("#log", VerticalScroll)
        line = Static(content, classes=classes)
        log.mount(line)
        self.call_after_refresh(log.scroll_end, animate=False)
        return line

    def send(self, txt):
        if self.chat_worker and self.chat_worker.is_running:
            self.say("still cooking (esc to stop)")
            return
        self.add_line(Text.assemble(("> ", "#cfcfcf"), (txt, "bold white")), classes="user")
        wait = self.add_line(Text(" thinking... "), classes="reply")
        self.say(chat_coding)
        self.history.append({"role": "user", "content": txt})
        self.save_to_archive("user", txt)
        self.chat_worker = self.ask(wait, self.model_name)

    def request_tool_approval(self, name, args):
        q = queue.Queue()
        self.call_from_thread(self._show_approval_ui, name, args, q)
        return q

    def _show_approval_ui(self, name, args, q):
        self.approval_queue = q
        self.say(f"allow {name}?")
        box = self.query_one("#approval-box")
        summary = ", ".join(f"{k}={v!r}" for k, v in args.items()) if isinstance(args, dict) else str(args)
        if len(summary) > 70: summary = summary[:67] + "..."
        box.query_one("#approval-title", Static).update(
            Text.assemble((name, f"bold {PURPLE}"), (f"  {summary}" if summary else "", DIM))
        )
        opts = self.query_one("#approval-list", OptionList)
        opts.clear_options()
        opts.add_options([
            Text.assemble(("• ", f"bold {PURPLE}"), ("Approve", "bold white")),
            Text.assemble(("• ", f"bold {PURPLE}"), ("Deny", "bold white")),
            Text.assemble(("• ", f"bold {PURPLE}"), ("Allow this command for this workspace", "bold white")),
        ])
        opts.highlighted = 0
        box.add_class("-active")
        opts.focus()

    def _on_stopped(self, wait, full):
        clean = re.sub(r"<think>.*?</think>", "", full, flags=re.DOTALL)
        clean = re.sub(r"<think>.*", "", clean, flags=re.DOTALL).strip()
        if clean:
            wait.update(Text(f"{clean}\n[stopped]", style="#8a8a99"))
        else:
            wait.remove()
        self.say("stopped")
        self.update_status()

    @work(thread=True)
    def ask(self, wait, model):
        worker = get_current_worker()

        def tool_handler(name, args):
            if worker.is_cancelled:
                return "Error: Stopped by user."
            dangerous = ["create_file", "write_file", "edit_lines", "delete_lines", "delete_file", "delete_directory", "move_file", "rename_file", "run_command", "web_download"]
            ws = os.getcwd()
            allowed = config["ALLOWED"].get(ws, [])
            if self.safe and name in dangerous and name not in allowed:
                decision = self.request_tool_approval(name, args).get()
                if worker.is_cancelled:
                    return "Error: Stopped by user."
                if decision == "allow_workspace":
                    config["ALLOWED"].setdefault(ws, [])
                    if name not in config["ALLOWED"][ws]:
                        config["ALLOWED"][ws].append(name)
                    save_config()
                elif decision != "approve":
                    return "Error: User denied permission."
            from ai import exec_tool
            return exec_tool(name, args)

        full, stream_reasoning = "", ""
        gen_time, gen_tokens = 0.0, 0
        turn_start, turn_chunks, turn_chars, turn_exact = None, 0, 0, 0

        try:
            for kind, data in ask_ai(self.history, model, tool_handler=tool_handler):
                if worker.is_cancelled:
                    break
                if kind == "error":
                    self.call_from_thread(self.show_reply, wait, "", data, True)
                    return
                elif kind == "tool":
                    if turn_start is not None:
                        gen_time += max(time.time() - turn_start, 0.05)
                        gen_tokens += turn_exact or max(turn_chunks, turn_chars // 4)
                        turn_start, turn_chunks, turn_chars, turn_exact = None, 0, 0, 0
                    self.call_from_thread(self.say, f"using {data}...")
                elif kind == "usage":
                    turn_exact = data
                elif kind in ("reasoning", "text"):
                    if turn_start is None:
                        turn_start = time.time()
                    turn_chunks += 1
                    turn_chars += len(data)
                    if kind == "reasoning":
                        stream_reasoning += data
                    else:
                        full += data
                        self.call_from_thread(self.update_live, wait, full)
                    if turn_chunks % 2 == 0:
                        dt = gen_time + max(time.time() - turn_start, 0.05)
                        toks = gen_tokens + (turn_exact or max(turn_chunks, turn_chars // 4))
                        self.current_tps = toks / dt
                        self.call_from_thread(self.update_status)
        except Exception as e:
            if worker.is_cancelled:
                self.call_from_thread(self._on_stopped, wait, full)
            else:
                self.call_from_thread(self.show_reply, wait, "", f"error: {e}", True)
            return

        if worker.is_cancelled:
            self.call_from_thread(self._on_stopped, wait, full)
            return

        if turn_start is not None:
            gen_time += max(time.time() - turn_start, 0.05)
            gen_tokens += turn_exact or max(turn_chunks, turn_chars // 4)
        if gen_time > 0 and gen_tokens > 0:
            self.current_tps = gen_tokens / gen_time

        tag_reasoning = "\n\n".join(r.strip() for r in re.findall(r"<think>(.*?)</think>", full, flags=re.DOTALL) if r.strip())
        reasoning = "\n\n".join(p for p in (stream_reasoning.strip(), tag_reasoning) if p)
        reply = re.sub(r"<think>.*?</think>", "", full, flags=re.DOTALL).strip() or "Done."
        self.history.append({"role": "assistant", "content": reply})
        self.save_to_archive("assistant", reply)
        self.call_from_thread(self.show_reply, wait, reasoning, reply)

    def update_live(self, wait, txt):
        clean = re.sub(r"<think>.*?</think>", "", txt, flags=re.DOTALL)
        processed = re.sub(r"<think>.*", "thinking...", clean, flags=re.DOTALL).strip() or "thinking..."
        wait.update(Text(processed, style="#cfcfcf"))
        self.call_after_refresh(self.query_one("#log", VerticalScroll).scroll_end, animate=False)

    def show_reply(self, wait, reasoning, reply, failed=False):
        if failed:
            wait.update(Text(reply, style="#ff6b6b"))
            self.say("oops")
            return

        text, files = split_reply(reply)
        wait.remove()
        log = self.query_one("#log", VerticalScroll)
        if reasoning: log.mount(ReasoningBlock(reasoning))

        in_code, code_txt, lang = False, Text(), ""
        curr_txt, tbl_lines, lst_lines = Text(style="#e6e6e6"), [], []

        def flush_txt():
            nonlocal curr_txt
            if curr_txt.plain.strip(): log.mount(Static(curr_txt, classes="reply"))
            curr_txt = Text(style="#e6e6e6")

        def flush_tbl():
            nonlocal tbl_lines
            if not tbl_lines: return
            if any("-" in ln and not ln.replace("-", "").replace("|", "").replace(":", "").strip() for ln in tbl_lines):
                rows = [[plain_line(c.strip()) for c in ln.strip().strip("|").split("|")] for ln in tbl_lines if not ("-" in ln and not ln.replace("-", "").replace("|", "").replace(":", "").strip())]
                if rows:
                    t = Table(box=box.HORIZONTALS, show_edge=False, border_style="#4a4a55")
                    for col in rows[0]: t.add_column(col, style="bold white")
                    for row in rows[1:]: t.add_row(*row)
                    log.mount(Static(t, classes="reply"))
                    tbl_lines.clear()
                    return
            for ln in tbl_lines:
                if curr_txt.plain: curr_txt.append("\n")
                curr_txt.append_text(plain_line(ln))
            flush_txt()
            tbl_lines.clear()

        def flush_lst():
            nonlocal lst_lines
            if not lst_lines: return
            t = Table(box=box.HORIZONTALS, show_edge=False, show_header=False, border_style="#4a4a55")
            t.add_column("Item", style="#e6e6e6")
            for ln in lst_lines:
                pts = ln.lstrip().split(" ", 1)
                t.add_row(plain_line((pts[1] if len(pts) > 1 else ln).strip()))
            log.mount(Static(t, classes="reply"))
            lst_lines.clear()

        def flush_all(): flush_txt(); flush_tbl(); flush_lst()

        for ln in text.strip().split("\n"):
            s = ln.strip()
            if s.startswith("```"):
                if in_code:
                    log.mount(CodeBlock(code_txt, lang))
                    code_txt, in_code = Text(), False
                else:
                    flush_all()
                    in_code, lang = True, s[3:].strip() or "code"
                continue

            if in_code:
                if code_txt.plain: code_txt.append("\n")
                code_txt.append_text(colour_command(ln))
            elif "|" in s:
                flush_txt(); flush_lst(); tbl_lines.append(ln)
            elif s.startswith(("- ", "* ")) or (len(s.split(". ", 1)) == 2 and s.split(". ", 1)[0].isdigit()):
                flush_txt(); flush_tbl(); lst_lines.append(ln)
            else:
                flush_tbl(); flush_lst()
                if not s and not curr_txt.plain: continue
                if curr_txt.plain: curr_txt.append("\n")
                curr_txt.append_text(plain_line(ln))

        flush_all()
        if in_code and code_txt.plain: log.mount(CodeBlock(code_txt, lang))
        if files: log.mount(Static(files_box([add_file(n, c) for n, c in files]), classes="reply"))

        self.call_after_refresh(log.scroll_end, animate=False)
        self.say(done_coding)
        self.update_status()

    def action_escape(self):
        if self._approval_active():
            if self.chat_worker and self.chat_worker.is_running:
                self.chat_worker.cancel()
            self._resolve_approval("deny")
            return
        if self.chat_worker and self.chat_worker.is_running:
            self.chat_worker.cancel()
            self.say("stopping...")
            return
        if self.matches:
            self.query_one("#commands", OptionList).display, self.matches = False, []
            box = self.query_one(Input)
            box.value = ""
            box.focus()

    def on_input_submitted(self, e):
        if self._approval_active():
            self.action_complete()
            return
        cmd = self.query_one("#commands", OptionList)
        if cmd.display and self.matches and cmd.highlighted is not None:
            self._select_menu_item(self.matches[cmd.highlighted][0])
            return
        txt = e.value.strip()
        e.input.value = ""
        cmd.display, self.matches = False, []
        if not txt: return
        self.run_command(txt) if txt.startswith("/") else self.send(txt)

FOX_ROWS = [
    '............nn................o.....', '...........nmmn..............nmn....',
    '...........mkkko............nkkmo...', '...........lekjko..........nkjflo...',
    '..........nldekjlo........nkjjden...', '..........mfccejjmo......nkjjebdko..',
    '..........mfcbckjjmmmmmmmmkjecadko..', '..........mfaackjjjgggggggjjecadko..',
    '..........mfbbdkgggggggggiijjebdko..', '..........mfbdkhgggggggiiiiigjedko..',
    '..........mfdkgggggggggiiiiiiihhko..', '..........njkfgggggggiiiiiiiiijjko..',
    '...........nggggggggiiiiiiiiiiikn...', '...........mggggggggiiiiiiiiiiiko...',
    '..........mjgggkkkgiiiiiiigggiiimo..', '..........mjggknnnkiiiiiiinoolgiko..',
    '........omkjgfnfggnkfhhghnlhflliilo.', '..nl....mjjfeddeeffcbloodeffeeeegimo',
    '.oceo...nkecbdddbbbbaaldaaaaddddcen.', '.ncbl....nddcbbbbbbldbededaabbbbdl..',
    '.lcbeo....neecbbbbbbllcedbaaaacen...', 'ndcbbeln...omddbbbbbbbabaaaacden....',
    'ndcbbbbdkn..nnnedcbaaaaaaaadeln.....', 'ndcbbccegjn....okkdddddddello.......',
    'ndcbbehhgghn..okkeccddddcdlo........', 'ndefdegggggk.omkhdaacccbaben........',
    'nfhgfggggggkonkigcbaaaaaaaelo.......', 'nkkjggggggiknkjiiecaaaaaacelo.......',
    '.nkjgggggijjnjiiiiecbaaabeilo.......', '.omjiggiijkmmiiiiiiecaaadfimo.......',
    '.omkjigijkknkiikiiigdbbdfiimo.......', '..okokjjkkknkjinkiigfddfiilmmo......',
    '...nkkkjkkknjjjmmiiimelkiilkmo......', '....omkjkkknkkkjnkkknelmjimmmo......',
    '......ommmmnmkjjmnmmnelnmmnmn.......', '...........pommmmnnmnllnmnoo........',
    '.............ooooonmooonnn..........', '...................o....o...........',
]
FOX_PALETTE = {'a': '#fff6f6', 'b': '#fceef0', 'c': '#f8e5e3', 'd': '#efcdbf', 'e': '#e8ad92', 'f': '#ef984e', 'g': '#ef9540', 'h': '#ef9345', 'i': '#f29339', 'j': '#ed7d3f', 'k': '#e1763f', 'l': '#b9714b', 'm': '#b85a36', 'n': '#974e32', 'o': '#693b2c', 'p': '#38231e'}

if __name__ == "__main__":
    Openfuji().run()
