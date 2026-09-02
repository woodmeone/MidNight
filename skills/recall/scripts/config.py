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


def list_agents() -> list[dict]:
    """Scan all agents under BASE_DIR, return list of {name, description, path}.

    Only directories that contain a recall.db or agent.json are treated as agents.
    Each agent can have an agent.json file with a 'description' field.
    Agents without agent.json use their name as the description.
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
        if has_desc:
            try:
                with open(os.path.join(agent_dir, 'agent.json'), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('description'):
                        description = data['description']
            except (json.JSONDecodeError, OSError):
                pass
        agents.append({
            'name': name,
            'description': description,
            'path': agent_dir,
        })
    return agents


def get_agent_description(agent: str) -> str:
    """Get the description for a specific agent."""
    for a in list_agents():
        if a['name'] == agent:
            return a['description']
    return agent