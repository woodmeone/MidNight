"""Pulse — autonomous heartbeat for midnight-pulse (自主心跳).

Protocol (inspired by VCP's Flowlock, original implementation):
  [[Pulse::Start]]              — start heartbeat mode
  [[Pulse::Next::秒数]]          — set next heartbeat interval (default 2s)
  [[Pulse::NextPrompt]]...[[/Pulse::NextPrompt]]  — custom prompt for next round
  [[Pulse::Complete]] + report  — task completed successfully
  [[Pulse::Fail]] + reason     — task failed
  [[Pulse::Stop]]              — stop heartbeat (no completion/fail)

Priority: Complete > Fail > Stop > Next/Start
Max rounds: 15 (configurable)
Timeout: 300s (configurable)

CLI: python pulse.py --api-url URL --api-key KEY --model MODEL --prompt "任务" [--rounds 15] [--timeout 300]
"""
import json
import os
import re
import sys
import time
import requests


PULSE_PATTERNS = {
    'start': re.compile(r'\[\[Pulse::Start\]\]', re.IGNORECASE),
    'complete': re.compile(r'\[\[Pulse::Complete\]\]', re.IGNORECASE),
    'fail': re.compile(r'\[\[Pulse::Fail\]\]', re.IGNORECASE),
    'stop': re.compile(r'\[\[Pulse::Stop\]\]', re.IGNORECASE),
    'next_heartbeat': re.compile(r'\[\[Pulse::Next::(\d+)\]\]', re.IGNORECASE),
    'next_prompt': re.compile(r'\[\[Pulse::NextPrompt\]\](.*?)\[\[/Pulse::NextPrompt\]\]', re.DOTALL | re.IGNORECASE),
}

DEFAULT_HEARTBEAT_DELAY = 2  # seconds
MAX_ROUNDS = 15
TIMEOUT_SECONDS = 300


def parse_pulse(response: str) -> dict:
    """Parse Pulse directives from model response.

    Returns {
        action: 'complete'|'fail'|'stop'|'start'|'continue',
        next_heartbeat: int (seconds),
        next_prompt: str|None,
        report: str (stripped of directives)
    }
    """
    result = {
        'action': 'continue',
        'next_heartbeat': DEFAULT_HEARTBEAT_DELAY,
        'next_prompt': None,
        'report': response,
    }

    # Parse all directives first (regardless of action priority)
    has_complete = bool(PULSE_PATTERNS['complete'].search(response))
    has_fail = bool(PULSE_PATTERNS['fail'].search(response))
    has_stop = bool(PULSE_PATTERNS['stop'].search(response))
    has_start = bool(PULSE_PATTERNS['start'].search(response))

    hb = PULSE_PATTERNS['next_heartbeat'].search(response)
    if hb:
        result['next_heartbeat'] = int(hb.group(1))

    np = PULSE_PATTERNS['next_prompt'].search(response)
    if np:
        result['next_prompt'] = np.group(1).strip()

    # Determine action by priority: Complete > Fail > Stop > Start
    if has_complete:
        result['action'] = 'complete'
    elif has_fail:
        result['action'] = 'fail'
    elif has_stop:
        result['action'] = 'stop'
    elif has_start:
        result['action'] = 'start'

    # Strip all directives for clean report
    cleaned = response
    for pat in PULSE_PATTERNS.values():
        cleaned = pat.sub('', cleaned)
    result['report'] = cleaned.strip()

    return result


def call_model(api_url: str, api_key: str, model: str, messages: list) -> str:
    """Call the model API. Returns response content."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    resp = requests.post(
        f"{api_url.rstrip('/')}/chat/completions",
        headers=headers,
        json=payload,
        timeout=60
    )
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def pulse_loop(api_url: str, api_key: str, model: str,
               initial_prompt: str, system_prompt: str = "",
               max_rounds: int = MAX_ROUNDS, timeout: int = TIMEOUT_SECONDS) -> dict:
    """Run the heartbeat loop.

    Returns {status, report, rounds, total_time}.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Initial user message with the task
    messages.append({"role": "user", "content": initial_prompt})

    start_time = time.time()
    current_prompt = initial_prompt
    heartbeat_delay = DEFAULT_HEARTBEAT_DELAY
    heartbeat_active = False

    for round_num in range(1, max_rounds + 1):
        # Check timeout
        if time.time() - start_time > timeout:
            return {
                'status': 'timeout',
                'report': f"达到超时限制 ({timeout}s)",
                'rounds': round_num - 1,
                'total_time': time.time() - start_time,
            }

        # Call model
        try:
            response = call_model(api_url, api_key, model, messages)
        except Exception as e:
            return {
                'status': 'error',
                'report': f"API 调用失败: {str(e)}",
                'rounds': round_num - 1,
                'total_time': time.time() - start_time,
            }

        # Parse directives
        parsed = parse_pulse(response)

        # Add assistant response to history
        messages.append({"role": "assistant", "content": parsed['report']})

        # Handle terminal actions
        if parsed['action'] == 'complete':
            return {
                'status': 'completed',
                'report': parsed['report'],
                'rounds': round_num,
                'total_time': time.time() - start_time,
            }
        elif parsed['action'] == 'fail':
            return {
                'status': 'failed',
                'report': parsed['report'],
                'rounds': round_num,
                'total_time': time.time() - start_time,
            }
        elif parsed['action'] == 'stop':
            return {
                'status': 'stopped',
                'report': parsed['report'],
                'rounds': round_num,
                'total_time': time.time() - start_time,
            }

        # Start heartbeat
        if parsed['action'] == 'start':
            heartbeat_active = True

        if not heartbeat_active:
            # Not in heartbeat mode, task will be idle
            return {
                'status': 'idle',
                'report': '未启动心跳模式（未输出 [[Pulse::Start]]）',
                'rounds': round_num,
                'total_time': time.time() - start_time,
            }

        # Prepare next prompt
        heartbeat_delay = parsed['next_heartbeat']
        next_prompt = parsed['next_prompt'] if parsed['next_prompt'] else \
            "[系统提示: 心跳继续运行，请继续执行任务。完成时输出 [[Pulse::Complete]] 和报告。]"

        # If this is the last round, don't bother waiting
        if round_num >= max_rounds:
            break

        # Wait for heartbeat interval
        time.sleep(heartbeat_delay)

        # Add next prompt
        messages.append({"role": "user", "content": next_prompt})

    return {
        'status': 'max_rounds',
        'report': f"达到最大轮数限制 ({max_rounds} 轮)，任务未自动完成。",
        'rounds': max_rounds,
        'total_time': time.time() - start_time,
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    api_url = os.environ.get('MIDNIGHT_API_URL', '')
    api_key = os.environ.get('MIDNIGHT_API_KEY', '')
    model = os.environ.get('MIDNIGHT_MODEL', 'deepseek-v4-flash')
    prompt = ''
    system_prompt = ''
    max_rounds = MAX_ROUNDS
    timeout = TIMEOUT_SECONDS

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--api-url' and i + 1 < len(argv):
            api_url = argv[i + 1]
            i += 2
        elif arg == '--api-key' and i + 1 < len(argv):
            api_key = argv[i + 1]
            i += 2
        elif arg == '--model' and i + 1 < len(argv):
            model = argv[i + 1]
            i += 2
        elif arg == '--prompt' and i + 1 < len(argv):
            prompt = argv[i + 1]
            i += 2
        elif arg == '--system' and i + 1 < len(argv):
            system_prompt = argv[i + 1]
            i += 2
        elif arg == '--rounds' and i + 1 < len(argv):
            max_rounds = int(argv[i + 1])
            i += 2
        elif arg == '--timeout' and i + 1 < len(argv):
            timeout = int(argv[i + 1])
            i += 2
        else:
            print(f"Unknown: {arg}", file=sys.stderr)
            return 2

    if not api_url or not api_key or not prompt:
        print("Usage: pulse.py --api-url URL --api-key KEY --model MODEL --prompt '任务' [--system '系统提示'] [--rounds N] [--timeout N]", file=sys.stderr)
        return 1

    result = pulse_loop(api_url, api_key, model, prompt, system_prompt=system_prompt,
                        max_rounds=max_rounds, timeout=timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in ('completed', 'stopped') else 1


if __name__ == '__main__':
    sys.exit(main())