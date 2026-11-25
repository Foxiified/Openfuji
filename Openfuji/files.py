import os
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

CATEGORIES = {
    "code": ((".py", ".js", ".ts", ".html", ".css", ".sh", ".c", ".cpp", ".java", ".rs", ".go"), "#5fd7d7"),
    "docs": ((".md", ".txt", ".rst"), "#7fd88f"),
    "data": ((".json", ".csv", ".yaml", ".yml", ".toml", ".xml"), "#d97736"),
    "other": ((), "#8a8a99"),
}

PREVIEW_LINES = 12
SHELL_START = ("python", "pip", "cat", "echo", "ls", "cd", "sudo", "git", "npm", "node",
               "bash", "sh", "chmod", "mkdir", "touch", "curl", "wget", "rm", "cp", "mv")

made = []

def category_of(name):
    ending = os.path.splitext(name)[1].lower()
    for category, (endings, _) in CATEGORIES.items():
        if ending in endings:
            return category
    return "other"

def looks_like_name(word):
    word = word.strip("`'\".,:;()[]")
    if not word or " " in word:
        return False
    ending = os.path.splitext(word)[1].lower()
    return any(ending in endings for endings, _ in CATEGORIES.values() if endings)

def is_shell(block):
    return len(block) == 1 and block[0].strip().startswith(SHELL_START)

def split_reply(reply):
    lines, kept, files = reply.split("\n"), [], []
    lone_name, i = None, 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped.startswith("```"):
            kept.append(lines[i])
            i += 1
            continue

        info = stripped[3:].strip()
        block = []
        i += 1
        while i < len(lines) and not lines[i].strip().startswith("```"):
            block.append(lines[i])
            i += 1
        i += 1

        name = None
        if info.startswith("file:"):
            name = info[len("file:"):].strip()
        elif looks_like_name(info):
            name = info
        elif lone_name:
            name = lone_name
        else:
            before = next((line for line in reversed(kept) if line.strip()), "")
            if before.strip().endswith(":") and not is_shell(block):
                name = next((w.strip("`'\".,:;()[]") for w in before.split() if looks_like_name(w)), None)

        if name:
            files.append((name, "\n".join(block) + "\n"))
            lone_name = None
        elif len(block) == 1 and looks_like_name(block[0]):
            lone_name = block[0].strip()
        else:
            kept += ["```", *block, "```"]
            lone_name = None

    if lone_name:
        kept.append(lone_name)
    return "\n".join(kept).strip(), files

def add_file(name, content):
    name = os.path.basename(name) or "untitled.txt"
    record = {"name": name, "size": len(content.encode()), "content": content}
    made.append(record)
    return record

def size_text(size):
    return f"{size} B" if size < 1024 else f"{size / 1024:.1f} KB"

def files_box(records):
    groups = {}
    for record in records:
        groups.setdefault(category_of(record["name"]), []).append(record)

    boxes = []
    for category, (_, colour) in CATEGORIES.items():
        if category not in groups:
            continue
        body = Text()
        for i, record in enumerate(groups[category]):
            if i:
                body.append("\n\n")
            body.append(record["name"], style=f"bold {colour}")
            body.append("  " + size_text(record["size"]), style="#8a8a99")
            content = record["content"].rstrip("\n").split("\n")
            for line in content[:PREVIEW_LINES]:
                body.append("\n" + line, style="#e6e6e6")
            if len(content) > PREVIEW_LINES:
                body.append(f"\n... {len(content) - PREVIEW_LINES} more lines", style="#8a8a99")
        boxes.append(
            Panel(body, title=f"{category} ({len(groups[category])})", title_align="left",
                  border_style=colour, expand=False, padding=(0, 1))
        )
    return Group(*boxes)
