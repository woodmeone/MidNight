"""Configuration for midnight-recall — agent-based physical isolation.

Each agent has its own database and diary directory, physically separated.
Default agent is 'default'. Supports auto-routing via semantic matching.

Base directory is configurable via MIDNIGHT_BASE_DIR (default ~/.midnight).
"""
import json
import os

DEFAULT_AGENT = 'default'
DEFAULT_BASE = os.path.expanduser("~/.midnight")
BASE_DIR = os.path.join(
    os.environ.get('MIDNIGHT_BASE_DIR', DEFAULT_BASE),
    'recall'
)


def get_agent_dir(agent: str = None) -> str:
    """Get the agent's data directory. Creates if needed."""
    agent = agent or os.environ.get('MIDNIGHT_AGENT') or DEFAULT_AGENT
    return os.path.join(BASE_DIR, agent)


def get_db_path(agent: str = None) -> str:
    """Get the agent's database path."""
    agent_dir = get_agent_dir(agent)
    return os.path.join(agent_dir, 'recall.db')


def get_dailynote_path(agent: str = None) -> str:
    """Get the agent's diary directory."""
    agent_dir = get_agent_dir(agent)
    return os.path.join(agent_dir, 'dailynote')


def get_self_path(agent: str = None) -> str:
    """Get the agent's identity file (self.md) path."""
    return os.path.join(get_agent_dir(agent), 'self.md')


def ensure_agent_dir(agent: str = None) -> str:
    """Ensure agent's data directory exists. Returns the path."""
    agent_dir = get_agent_dir(agent)
    os.makedirs(os.path.join(agent_dir, 'dailynote'), exist_ok=True)
    return agent_dir


def ensure_agent(agent: str = None, description: str = None) -> str:
    """声明身份 = 自动开户：建目录 + 立身份 (agent.json)，幂等。

    与 ensure_agent_dir 的区别：本函数让"有名字的智能体"在 list_agents() 中
    立刻可见（仅建目录不会生成 agent.json，而 list_agents 依据它来识别智能体）。
    约定：
      - `default` 是兜底槽位，不生成身份文件（不冒充具名 AI）。
      - 已开户则不覆盖已有 description；仅当缺 description 且本次提供时才补写。
    """
    if not agent:
        agent = os.environ.get('MIDNIGHT_AGENT') or DEFAULT_AGENT
    agent_dir = ensure_agent_dir(agent)
    if agent == DEFAULT_AGENT:
        return agent_dir

    meta_path = os.path.join(agent_dir, 'agent.json')
    data = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    if not data.get('description'):
        data['description'] = description or agent
    if not data.get('name'):
        data['name'] = agent
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return agent_dir


def list_agents() -> list[dict]:
    """Scan all agents under BASE_DIR, return list of {name, description, path, keywords}.

    Only directories that contain a recall.db or agent.json are treated as agents.
    Each agent can have an agent.json file with 'description' and optional 'keywords'
    (list of domain words used for keyword-anchored routing). Agents without
    agent.json use their name as the description.
    """
    agents = []
    if not os.path.exists(BASE_DIR):
        return agents

    for name in sorted(os.listdir(BASE_DIR)):
        agent_dir = os.path.join(BASE_DIR, name)
        if not os.path.isdir(agent_dir):
            continue
        # Require at least a recall.db or agent.json to be considered an agent
        has_db = os.path.exists(os.path.join(agent_dir, 'recall.db'))
        has_desc = os.path.exists(os.path.join(agent_dir, 'agent.json'))
        if not has_db and not has_desc:
            continue
        description = name
        keywords = []
        if has_desc:
            try:
                with open(os.path.join(agent_dir, 'agent.json'), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('description'):
                        description = data['description']
                    kw = data.get('keywords')
                    if isinstance(kw, list):
                        keywords = [str(k) for k in kw]
            except (json.JSONDecodeError, OSError):
                pass
        agents.append({
            'name': name,
            'description': description,
            'path': agent_dir,
            'keywords': keywords,
        })
    return agents


def get_agent_description(agent: str) -> str:
    """Get the description for a specific agent."""
    for a in list_agents():
        if a['name'] == agent:
            return a['description']
    return agent