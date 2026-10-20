"""Drive real sequential user turns through Pi RPC, preserving every native byte."""
import json,queue,subprocess,threading,time
from pathlib import Path


def interactive(process, first_message, out, record, channel, idle_seconds=1800):
    """Transport user prompts/abort to one native Pi RPC process, never replay context."""
    channel = Path(channel)
    channel.mkdir(parents=True, exist_ok=True)
    incoming = queue.Queue()

    def read():
        for line in iter(process.stdout.readline, b''):
            out.write(line.decode('utf-8', errors='replace')); out.flush()
            try:
                incoming.put(json.loads(line))
            except ValueError:
                incoming.put({'type': 'invalid_native_json'})
        incoming.put({'type': 'process_eof'})

    threading.Thread(target=read, daemon=True).start()
    turn, busy, closing, touched = -1, False, False, time.monotonic()

    def status(phase):
        temp = channel/'status.tmp'
        temp.write_text(json.dumps({'phase': phase, 'turn': turn, 'updated': time.time()}), encoding='utf-8')
        temp.replace(channel/'status.json')

    def send(command):
        process.stdin.write((json.dumps(command, ensure_ascii=False)+'\n').encode())
        process.stdin.flush()

    def prompt(text):
        nonlocal turn, busy, touched
        turn += 1
        busy = True
        touched = time.monotonic()
        status('running')
        record({'type': 'user_turn_submitted', 'index': turn, 'text': text})
        send({'id': 'user-'+str(turn), 'type': 'prompt', 'message': text})

    prompt(first_message)
    try:
        while True:
            command_path = channel/'command.json'
            if command_path.exists():
                command = json.loads(command_path.read_text(encoding='utf-8'))
                kind = command.get('type')
                if kind == 'prompt' and not busy and not closing:
                    prompt(command['message'])
                elif kind in ('abort', 'close'):
                    closing = kind == 'close'
                    if busy:
                        status('stopping')
                        send({'id': kind+'-'+str(turn), 'type': 'abort'})
                    elif closing:
                        command_path.unlink()
                        break
                else:
                    record({'type': 'host_command_rejected', 'command': kind, 'reason': 'session_busy'})
                command_path.unlink()
            try:
                event = incoming.get(timeout=.1)
            except queue.Empty:
                if not busy and time.monotonic()-touched > idle_seconds:
                    record({'type': 'conversation_closed', 'reason': 'idle_timeout'})
                    break
                continue
            if event.get('type') == 'process_eof':
                return process.wait()
            if event.get('type') == 'agent_end':
                record({'type': 'user_turn_completed', 'index': turn})
                busy, touched = False, time.monotonic()
                status('idle')
                if closing:
                    break
            if event.get('type') == 'response' and event.get('success') is False:
                record({'type': 'rpc_rejected', 'command': event.get('command'), 'error': event.get('error')})
                if event.get('command') == 'prompt':
                    busy = False
                    status('idle')
        process.stdin.close()
        return process.wait(timeout=10)
    finally:
        status('closed')


def conversation(process,messages,out,record,timeout,stop_requested=None):
    incoming=queue.Queue()
    def read():
        for line in iter(process.stdout.readline,b''):
            out.write(line.decode('utf-8',errors='replace'));out.flush()
            try:incoming.put(json.loads(line))
            except ValueError:incoming.put({'type':'invalid_native_json'})
        incoming.put({'type':'process_eof'})
    threading.Thread(target=read,daemon=True).start()
    for i,text in enumerate(messages):
        deadline=time.monotonic()+timeout if timeout is not None else None
        command={'id':'user-'+str(i),'type':'prompt','message':text}
        process.stdin.write((json.dumps(command,ensure_ascii=False)+'\n').encode());process.stdin.flush()
        record({'type':'user_turn_submitted','index':i,'text':text})
        while True:
            remaining=deadline-time.monotonic() if deadline is not None else None
            if remaining is not None and remaining<=0:raise subprocess.TimeoutExpired(process.args,timeout)
            try:event=incoming.get(timeout=remaining)
            except queue.Empty:raise subprocess.TimeoutExpired(process.args,timeout)
            if event.get('type')=='agent_end':
                record({'type':'user_turn_completed','index':i})
                if stop_requested and stop_requested():
                    record({'type':'conversation_stopped','index':i,'reason':'pending_user_approval'})
                    process.stdin.close()
                    return process.wait(timeout=10)
                break
            if event.get('type')=='process_eof':return process.wait()
            if event.get('type')=='response' and event.get('success') is False:
                record({'type':'rpc_rejected','index':i,'command':event.get('command')});process.stdin.close();return process.wait(timeout=10)
    process.stdin.close()
    return process.wait(timeout=10)
