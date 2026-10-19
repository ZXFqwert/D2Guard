"""Drive real sequential user turns through Pi RPC, preserving every native byte."""
import json,queue,subprocess,threading,time


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
