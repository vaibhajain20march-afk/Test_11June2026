import asyncio
import os
from dotenv import load_dotenv
from github import Github, GithubException, Auth
import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel import NotificationOptions

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise EnvironmentError("GITHUB_TOKEN is not set. Copy .env.example to .env and fill in your token.")

gh = Github(auth=Auth.Token(GITHUB_TOKEN))
app = Server("github-mcp-server")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_repository",
            description="Get details about a GitHub repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner (user or org)"},
                    "repo": {"type": "string", "description": "Repository name"},
                },
                "required": ["owner", "repo"],
            },
        ),
        types.Tool(
            name="list_issues",
            description="List issues in a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "default": "open",
                        "description": "Issue state filter",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Max number of issues to return (1-100)",
                    },
                },
                "required": ["owner", "repo"],
            },
        ),
        types.Tool(
            name="get_issue",
            description="Get a specific issue by number.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                },
                "required": ["owner", "repo", "issue_number"],
            },
        ),
        types.Tool(
            name="create_issue",
            description="Create a new issue in a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "title": {"type": "string", "description": "Issue title"},
                    "body": {"type": "string", "description": "Issue body (markdown supported)"},
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels to apply",
                    },
                },
                "required": ["owner", "repo", "title"],
            },
        ),
        types.Tool(
            name="list_pull_requests",
            description="List pull requests in a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "default": "open",
                    },
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["owner", "repo"],
            },
        ),
        types.Tool(
            name="get_pull_request",
            description="Get a specific pull request by number.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "pr_number": {"type": "integer"},
                },
                "required": ["owner", "repo", "pr_number"],
            },
        ),
        types.Tool(
            name="create_pull_request",
            description="Create a new pull request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "head": {"type": "string", "description": "Branch to merge from"},
                    "base": {"type": "string", "description": "Branch to merge into"},
                    "draft": {"type": "boolean", "default": False},
                },
                "required": ["owner", "repo", "title", "head", "base"],
            },
        ),
        types.Tool(
            name="get_file_contents",
            description="Get the contents of a file in a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {"type": "string", "description": "File path relative to repo root"},
                    "ref": {"type": "string", "description": "Branch, tag, or commit SHA (default: default branch)"},
                },
                "required": ["owner", "repo", "path"],
            },
        ),
        types.Tool(
            name="list_commits",
            description="List commits in a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "branch": {"type": "string", "description": "Branch name (default: default branch)"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["owner", "repo"],
            },
        ),
        types.Tool(
            name="list_branches",
            description="List branches in a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                },
                "required": ["owner", "repo"],
            },
        ),
        types.Tool(
            name="search_repositories",
            description="Search GitHub repositories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (GitHub search syntax supported)"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_user",
            description="Get details about a GitHub user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "GitHub username (omit for authenticated user)"},
                },
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = await _dispatch(name, arguments)
    except GithubException as exc:
        result = f"GitHub API error {exc.status}: {exc.data.get('message', str(exc))}"
    except Exception as exc:
        result = f"Error: {exc}"

    return [types.TextContent(type="text", text=result)]


async def _dispatch(name: str, args: dict) -> str:
    if name == "get_repository":
        return _get_repository(args["owner"], args["repo"])
    if name == "list_issues":
        return _list_issues(args["owner"], args["repo"], args.get("state", "open"), args.get("limit", 20))
    if name == "get_issue":
        return _get_issue(args["owner"], args["repo"], args["issue_number"])
    if name == "create_issue":
        return _create_issue(args["owner"], args["repo"], args["title"], args.get("body", ""), args.get("labels", []))
    if name == "list_pull_requests":
        return _list_pull_requests(args["owner"], args["repo"], args.get("state", "open"), args.get("limit", 20))
    if name == "get_pull_request":
        return _get_pull_request(args["owner"], args["repo"], args["pr_number"])
    if name == "create_pull_request":
        return _create_pull_request(
            args["owner"], args["repo"], args["title"],
            args.get("body", ""), args["head"], args["base"], args.get("draft", False),
        )
    if name == "get_file_contents":
        return _get_file_contents(args["owner"], args["repo"], args["path"], args.get("ref"))
    if name == "list_commits":
        return _list_commits(args["owner"], args["repo"], args.get("branch"), args.get("limit", 20))
    if name == "list_branches":
        return _list_branches(args["owner"], args["repo"])
    if name == "search_repositories":
        return _search_repositories(args["query"], args.get("limit", 10))
    if name == "get_user":
        return _get_user(args.get("username"))
    return f"Unknown tool: {name}"


# ---------------------------------------------------------------------------
# Implementation helpers (synchronous — PyGithub is synchronous)
# ---------------------------------------------------------------------------

def _get_repository(owner: str, repo: str) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    return (
        f"Repository: {r.full_name}\n"
        f"Description: {r.description}\n"
        f"URL: {r.html_url}\n"
        f"Stars: {r.stargazers_count}  Forks: {r.forks_count}  Watchers: {r.watchers_count}\n"
        f"Language: {r.language}\n"
        f"Default branch: {r.default_branch}\n"
        f"Open issues: {r.open_issues_count}\n"
        f"Private: {r.private}\n"
        f"Created: {r.created_at.isoformat()}\n"
        f"Updated: {r.updated_at.isoformat()}"
    )


def _list_issues(owner: str, repo: str, state: str, limit: int) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    issues = list(r.get_issues(state=state)[:limit])
    if not issues:
        return f"No {state} issues found in {owner}/{repo}."
    lines = [f"Issues ({state}) in {owner}/{repo}:\n"]
    for issue in issues:
        lines.append(f"  #{issue.number} [{issue.state}] {issue.title}")
        lines.append(f"    URL: {issue.html_url}  |  Comments: {issue.comments}")
    return "\n".join(lines)


def _get_issue(owner: str, repo: str, number: int) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    issue = r.get_issue(number)
    labels = ", ".join(lbl.name for lbl in issue.labels) or "none"
    return (
        f"Issue #{issue.number}: {issue.title}\n"
        f"State: {issue.state}\n"
        f"Author: {issue.user.login}\n"
        f"Labels: {labels}\n"
        f"Comments: {issue.comments}\n"
        f"URL: {issue.html_url}\n"
        f"Created: {issue.created_at.isoformat()}\n\n"
        f"{issue.body or '(no body)'}"
    )


def _create_issue(owner: str, repo: str, title: str, body: str, labels: list) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    kwargs = {"title": title, "body": body}
    if labels:
        kwargs["labels"] = labels
    issue = r.create_issue(**kwargs)
    return f"Created issue #{issue.number}: {issue.title}\nURL: {issue.html_url}"


def _list_pull_requests(owner: str, repo: str, state: str, limit: int) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    prs = list(r.get_pulls(state=state)[:limit])
    if not prs:
        return f"No {state} pull requests found in {owner}/{repo}."
    lines = [f"Pull requests ({state}) in {owner}/{repo}:\n"]
    for pr in prs:
        lines.append(f"  #{pr.number} [{pr.state}] {pr.title}")
        lines.append(f"    {pr.head.label} → {pr.base.label}  |  URL: {pr.html_url}")
    return "\n".join(lines)


def _get_pull_request(owner: str, repo: str, number: int) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    pr = r.get_pull(number)
    return (
        f"PR #{pr.number}: {pr.title}\n"
        f"State: {pr.state}  |  Draft: {pr.draft}\n"
        f"Author: {pr.user.login}\n"
        f"Branch: {pr.head.label} → {pr.base.label}\n"
        f"Commits: {pr.commits}  |  Changed files: {pr.changed_files}\n"
        f"Additions: +{pr.additions}  Deletions: -{pr.deletions}\n"
        f"Mergeable: {pr.mergeable}\n"
        f"URL: {pr.html_url}\n"
        f"Created: {pr.created_at.isoformat()}\n\n"
        f"{pr.body or '(no description)'}"
    )


def _create_pull_request(owner: str, repo: str, title: str, body: str, head: str, base: str, draft: bool) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    pr = r.create_pull(title=title, body=body, head=head, base=base, draft=draft)
    return f"Created PR #{pr.number}: {pr.title}\nURL: {pr.html_url}"


def _get_file_contents(owner: str, repo: str, path: str, ref: str | None) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    kwargs = {"path": path}
    if ref:
        kwargs["ref"] = ref
    content = r.get_contents(**kwargs)
    if isinstance(content, list):
        names = "\n".join(f"  {c.name}" for c in content)
        return f"Directory listing for {path}:\n{names}"
    decoded = content.decoded_content.decode("utf-8", errors="replace")
    size_kb = content.size / 1024
    return f"File: {content.path}  ({size_kb:.1f} KB)\n\n{decoded}"


def _list_commits(owner: str, repo: str, branch: str | None, limit: int) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    kwargs = {}
    if branch:
        kwargs["sha"] = branch
    commits = list(r.get_commits(**kwargs)[:limit])
    if not commits:
        return "No commits found."
    lines = [f"Commits in {owner}/{repo}{'/' + branch if branch else ''}:\n"]
    for c in commits:
        msg_first_line = c.commit.message.splitlines()[0]
        lines.append(f"  {c.sha[:7]}  {c.commit.author.date.strftime('%Y-%m-%d')}  {c.commit.author.name}")
        lines.append(f"           {msg_first_line}")
    return "\n".join(lines)


def _list_branches(owner: str, repo: str) -> str:
    r = gh.get_repo(f"{owner}/{repo}")
    branches = list(r.get_branches())
    if not branches:
        return f"No branches found in {owner}/{repo}."
    default = r.default_branch
    lines = [f"Branches in {owner}/{repo}:\n"]
    for b in branches:
        marker = " (default)" if b.name == default else ""
        lines.append(f"  {b.name}{marker}")
    return "\n".join(lines)


def _search_repositories(query: str, limit: int) -> str:
    results = list(gh.search_repositories(query=query)[:limit])
    if not results:
        return f"No repositories found for: {query}"
    lines = [f"Repository search results for '{query}':\n"]
    for r in results:
        lines.append(f"  {r.full_name}  ★{r.stargazers_count}")
        lines.append(f"    {r.description or '(no description)'}")
        lines.append(f"    {r.html_url}")
    return "\n".join(lines)


def _get_user(username: str | None) -> str:
    user = gh.get_user(username) if username else gh.get_user()
    return (
        f"User: {user.login}\n"
        f"Name: {user.name}\n"
        f"Bio: {user.bio}\n"
        f"Company: {user.company}\n"
        f"Location: {user.location}\n"
        f"Public repos: {user.public_repos}\n"
        f"Followers: {user.followers}  |  Following: {user.following}\n"
        f"URL: {user.html_url}\n"
        f"Created: {user.created_at.isoformat()}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="github-mcp-server",
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
