"""Transport tests use a protocol stub, not Agent evaluation evidence."""
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from pi_session import interactive


class InteractiveRPCTests(unittest.TestCase):
    def test_followup_and_abort_use_one_native_process(self):
        script = """
import sys,json,os
for line in sys.stdin:
    c=json.loads(line)
    print(json.dumps({'type':'received','pid':os.getpid(),'command':c}),flush=True)
    if c['type']=='prompt' and c['message']!='wait':
        print(json.dumps({'type':'agent_end'}),flush=True)
    elif c['type']=='abort':
        print(json.dumps({'type':'agent_end'}),flush=True)
"""
        with tempfile.TemporaryDirectory() as tmp:
            channel = Path(tmp); output=io.StringIO(); events=[]
            process = subprocess.Popen([sys.executable,'-u','-c',script], stdin=subprocess.PIPE,stdout=subprocess.PIPE)
            errors=[]
            def drive():
                try: interactive(process,'first',output,events.append,channel)
                except BaseException as exc: errors.append(exc)
            worker=threading.Thread(target=drive); worker.start()
            def wait_for(phase,turn):
                end=time.monotonic()+8
                while time.monotonic()<end:
                    try: status=json.loads((channel/'status.json').read_text())
                    except (OSError,ValueError):status={}
                    if status.get('phase')==phase and status.get('turn')==turn:return
                    time.sleep(.02)
                self.fail('RPC status not reached: '+str(status))
            def send(command):
                p=channel/'command.tmp';p.write_text(json.dumps(command));p.replace(channel/'command.json')
            try:
                wait_for('idle',0)
                send({'type':'prompt','message':'wait'})
                wait_for('running',1)
                send({'type':'abort'})
                wait_for('idle',1)
                send({'type':'close'})
                worker.join(8)
                self.assertFalse(worker.is_alive())
                self.assertFalse(errors)
                received=[json.loads(line) for line in output.getvalue().splitlines() if json.loads(line)['type']=='received']
                self.assertEqual(len({e['pid'] for e in received}),1)
                self.assertEqual([e['command']['type'] for e in received],['prompt','prompt','abort'])
                self.assertEqual(sum(e['type']=='user_turn_completed' for e in events),2)
            finally:
                if process.poll() is None:process.kill()
                process.wait()
                worker.join(2)
                process.stdout.close()
