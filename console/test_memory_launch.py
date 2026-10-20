import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import server


class MemoryLaunchTests(unittest.TestCase):
    def test_real_writer_precedes_independent_arena_copies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'scenarios').mkdir(); (root/'runs').mkdir()
            (root/'scenarios/memory.json').write_text(json.dumps({'setup_task':'Save handoff'}))
            with patch.object(server, 'HERE', root):
                console = server.Console(root, 'python')
            job={'id':'test','scenario':'memory','environment':'clean','status':'running',
                 '_log':root/'job.log','steps':[{'protect':p,'status':'queued','run_id':None} for p in ('off','on')]}
            calls=[]
            fixtures=[]
            def run(command, **kwargs):
                calls.append(command)
                fixtures.append(kwargs['env']['D2_FIXTURE_CANARY'])
                memory=Path(command[command.index('--memory-root')+1])
                if '--task' in command:
                    self.assertNotIn('--memory-reader',command)
                    (memory/'handoff.json').write_text('{"content":"original"}')
                else:
                    self.assertIn('--memory-reader',command)
                    self.assertEqual(json.loads((memory/'handoff.json').read_text())['content'], 'original')
                    (memory/'handoff.json').write_text('{"content":"changed by this lane"}')
                    rid='20261020-120000-'+('000001' if command[command.index('--protect')+1]=='off' else '000002')
                    folder=root/'runs'/rid; folder.mkdir()
                    (folder/'manifest.json').write_text(json.dumps({'scenario':'memory','environment':'clean',
                        'protection':command[command.index('--protect')+1],'guard_engine':'d2v2'}))
                    (folder/'result.json').write_text('{"model_run_ok":true}')
                    kwargs['stdout'].write('RUN '+rid+' environment=clean\n'); kwargs['stdout'].flush()
                return 0
            with patch.object(server.subprocess,'call',side_effect=run):
                console._run_job(job)
            self.assertEqual(len(calls),3)
            self.assertEqual(len(set(fixtures)),1)
            self.assertIn('--task',calls[0])
            self.assertEqual(job['status'],'finished')
            self.assertNotEqual(job['steps'][0]['run_id'],job['steps'][1]['run_id'])

    def test_missing_written_memory_does_not_start_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'scenarios').mkdir(); (root/'runs').mkdir()
            (root/'scenarios/memory.json').write_text('{"setup_task":"Save handoff"}')
            with patch.object(server,'HERE',root):
                console=server.Console(root,'python')
            job={'id':'test','scenario':'memory','environment':'clean','status':'running',
                 '_log':root/'job.log','steps':[{'protect':'on','status':'queued','run_id':None}]}
            with patch.object(server.subprocess,'call',return_value=0) as run:
                console._run_job(job)
            self.assertEqual(run.call_count,1)
            self.assertEqual(job['status'],'failed')


if __name__ == '__main__':
    unittest.main()
