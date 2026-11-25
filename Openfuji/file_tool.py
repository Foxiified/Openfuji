import os
import shutil
import subprocess

def read_file(filepath, line_numbers=False):
    if not os.path.exists(filepath): return f"File not found: {filepath}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            if not line_numbers: return f.read()
            return "".join(f"{i}: {ln}" for i, ln in enumerate(f, 1))
    except Exception as e: return f"Couldn't read {filepath}: {e}"

def create_file(filepath, content=""):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f: f.write(content)
        return f"Created {filepath}"
    except Exception as e: return f"Failed to create {filepath}: {e}"

def write_file(filepath, content):
    return create_file(filepath, content)

def edit_lines(filepath, start_line, content, end_line=None):
    if not os.path.exists(filepath): return f"File not found: {filepath}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        end = start_line if end_line is None else end_line
        if start_line < 1 or end < start_line or end > len(lines):
            return f"Invalid line range {start_line}-{end} (file has {len(lines)} lines)."
        new_lines = content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        lines[start_line - 1:end] = new_lines
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return f"Updated lines {start_line}-{end} in {filepath}"
    except Exception as e: return f"Failed to edit {filepath}: {e}"

def delete_lines(filepath, start_line, end_line=None):
    if not os.path.exists(filepath): return f"File not found: {filepath}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        end = start_line if end_line is None else end_line
        if start_line < 1 or end < start_line or end > len(lines):
            return f"Invalid line range {start_line}-{end} (file has {len(lines)} lines)."
        del lines[start_line - 1:end]
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return f"Deleted lines {start_line}-{end} from {filepath}"
    except Exception as e: return f"Failed to delete lines in {filepath}: {e}"

def get_working_directory():
    try: return os.getcwd()
    except Exception as e: return f"Failed to get cwd: {e}"

def list_directory(path="."):
    try:
        items = os.listdir(path)
        return "\n".join(items) if items else "Directory is empty."
    except Exception as e: return f"Failed to list {path}: {e}"

def move_file(source, dest):
    if not os.path.exists(source): return f"Source not found: {source}"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        shutil.move(source, dest)
        return f"Moved {source} -> {dest}"
    except Exception as e: return f"Move failed: {e}"

def rename_file(filepath, new_name):
    if not os.path.exists(filepath): return f"File not found: {filepath}"
    try:
        new_path = os.path.join(os.path.dirname(os.path.abspath(filepath)), new_name)
        if os.path.exists(new_path): return f"Target {new_name} already exists."
        os.rename(filepath, new_path)
        return f"Renamed to {new_name}"
    except Exception as e: return f"Rename failed: {e}"

def delete_file(filepath):
    if not os.path.exists(filepath): return f"Not found: {filepath}"
    if os.path.isdir(filepath): return f"{filepath} is a dir, use delete_directory."
    try:
        os.remove(filepath)
        return f"Deleted {filepath}"
    except Exception as e: return f"Delete failed: {e}"

def delete_directory(path):
    if not os.path.exists(path): return f"Not found: {path}"
    try:
        shutil.rmtree(path)
        return f"Deleted dir {path}"
    except Exception as e: return f"Dir delete failed: {e}"

def run_command(command):
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        out = res.stdout + (f"\n[stderr]\n{res.stderr}" if res.stderr else "")
        return out[:15000] if out.strip() else "Success (no output)"
    except subprocess.TimeoutExpired: return "Command timed out."
    except Exception as e: return f"Command failed: {e}"

def global_search(query, path="."):
    matches = []
    try:
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    filepath = os.path.join(root, f)
                    with open(filepath, "r", encoding="utf-8") as file:
                        if query in file.read(): matches.append(filepath)
                except Exception: pass
        return "\n".join(matches) if matches else "No matches found."
    except Exception as e: return f"Search failed: {e}"

FILE_TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "line_numbers": {"type": "boolean"}}, "required": ["filepath"]}}},
    {"type": "function", "function": {"name": "create_file", "description": "Create a file", "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}}, "required": ["filepath"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write/overwrite a file", "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}}, "required": ["filepath", "content"]}}},
    {"type": "function", "function": {"name": "edit_lines", "description": "Replace specific lines in a file (1-indexed)", "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}, "content": {"type": "string"}}, "required": ["filepath", "start_line", "content"]}}},
    {"type": "function", "function": {"name": "delete_lines", "description": "Delete specific lines from a file (1-indexed)", "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["filepath", "start_line"]}}},
    {"type": "function", "function": {"name": "list_directory", "description": "List dir contents", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "get_working_directory", "description": "Get cwd", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "move_file", "description": "Move a file", "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "dest": {"type": "string"}}, "required": ["source", "dest"]}}},
    {"type": "function", "function": {"name": "rename_file", "description": "Rename a file", "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "new_name": {"type": "string"}}, "required": ["filepath", "new_name"]}}},
    {"type": "function", "function": {"name": "delete_file", "description": "Delete file", "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}}, "required": ["filepath"]}}},
    {"type": "function", "function": {"name": "delete_directory", "description": "Delete dir", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "Run shell command", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "global_search", "description": "Search text in files", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}}, "required": ["query"]}}}
]

def execute_file_tool(name, kwargs):
    func = globals().get(name)
    return func(**kwargs) if func else None
