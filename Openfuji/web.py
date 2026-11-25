import urllib.request
from duckduckgo_search import DDGS
from playwright.sync_api import sync_playwright

def search_web(query, max_results=5):
    try:
        results = DDGS().text(query, max_results=max_results)
        return "\n".join(f"{r['title']} - {r['href']}\n{r['body']}" for r in results) if results else "No results."
    except Exception as e:
        return f"Search failed: {e}"

def read_page(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            page.goto(url, timeout=15000)
            text = page.evaluate("document.body.innerText")
            browser.close()
            return text[:15000] if text else "Page was empty."
    except Exception as e:
        return f"Scrape failed: {e}"

def web_download(url, destination):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as res, open(destination, "wb") as f:
            f.write(res.read())
        return f"Downloaded {url} -> {destination}"
    except Exception as e:
        return f"Download failed: {e}"

WEB_TOOLS = [
    {"type": "function", "function": {"name": "search_web", "description": "Search duckduckgo", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "read_page", "description": "Scrape text from URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "web_download", "description": "Download file from URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "destination": {"type": "string"}}, "required": ["url", "destination"]}}}
]

def execute_tool(name, kwargs):
    func = globals().get(name)
    return func(**kwargs) if func else f"Unknown tool: {name}"
