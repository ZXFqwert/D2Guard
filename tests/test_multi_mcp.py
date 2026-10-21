"""Several MCP servers in one task: routing, server identity and provenance. Protocol checks only."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from d2v2.mcp_bridge import MCPRouter
from d2v2.core import CoreV2, mcp_route
from d2v2.compression import literal_scope
from test_v2 import FastStub, PROVIDER

SERVERS = [
    {'server_id': 'docs-a', 'mcp_return': 'Aster Tasks stores tasks in SQLite.'},
    {'server_id': 'notes-b', 'mcp_return': 'Release codename: Cobalt Finch.', 'mcp_write': True},
]


class RouterTests(unittest.TestCase):
    def test_single_server_keeps_plain_tool_names(self):
        events = []
        router = MCPRouter(events.append, {'mcp_return': 'facts'})
        try:
            self.assertFalse(router.multi)
            self.assertEqual(router.server_ids, ['local-docs'])
            self.assertEqual([t['name'] for t in router.tools], ['project_facts'])
            self.assertNotIn('server_id', router.tools[0])
            result = router.call('project_facts', {})
            self.assertEqual(result['content'][0]['text'], 'facts')
            self.assertEqual(result['server_id'], 'local-docs')
        finally:
            router.close()

    def test_two_servers_qualify_same_named_tools_and_route_each_call(self):
        events = []
        router = MCPRouter(events.append, {'mcp_servers': SERVERS})
        try:
            self.assertTrue(router.multi)
            names = sorted(t['name'] for t in router.tools)
            self.assertEqual(names, ['docs-a/project_facts', 'notes-b/project_facts', 'notes-b/save_note'])
            self.assertEqual({t['server_id'] for t in router.tools}, {'docs-a', 'notes-b'})
            a = router.call('docs-a/project_facts', {})
            b = router.call('notes-b/project_facts', {})
            self.assertEqual((a['server_id'], a['content'][0]['text']), ('docs-a', 'Aster Tasks stores tasks in SQLite.'))
            self.assertEqual((b['server_id'], b['content'][0]['text']), ('notes-b', 'Release codename: Cobalt Finch.'))
            self.assertEqual(router.call('notes-b/save_note', {'content': 'n'})['server_id'], 'notes-b')
            # Each server publishes its own descriptions under its own id.
            self.assertEqual(sorted({e['server_id'] for e in events if e['type'] == 'mcp_description'}), ['docs-a', 'notes-b'])
            with self.assertRaises(ValueError):
                router.call('project_facts', {})
            with self.assertRaises(ValueError):
                router.call('docs-a/save_note', {'content': 'n'})
        finally:
            router.close()

    def test_duplicate_or_invalid_server_ids_are_rejected(self):
        for servers in ([{'server_id': 'same'}, {'server_id': 'same'}], [{'server_id': 'ok'}, {'server_id': 'Bad Id'}]):
            with self.subTest(servers=servers), self.assertRaises(ValueError):
                MCPRouter(lambda e: None, {'mcp_servers': servers})

    def test_host_config_lists_several_servers(self):
        events = []
        router = MCPRouter(events.append, {}, {'servers': [{'server_id': 'one'}, {'server_id': 'two', 'transport': 'http'}]})
        try:
            self.assertEqual(router.server_ids, ['one', 'two'])
            self.assertEqual(router.call('two/project_facts', {})['server_id'], 'two')
        finally:
            router.close()


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.core = CoreV2(True, self.temp.name, PROVIDER, lambda name, item: None, fast=FastStub())
        self.core.observe({'event_id': 'user', 'type': 'agent_start', 'agent_id': 'main',
                           'task': 'Call docs-a/project_facts and notes-b/project_facts, then write summary.md.'})

    def tearDown(self):
        self.core.drain(2); self.core.store.db.close(); self.temp.cleanup()

    def test_mcp_route(self):
        self.assertEqual(mcp_route('docs-a', 'docs-a/project_facts'), ('docs-a', 'project_facts'))
        self.assertEqual(mcp_route(None, 'notes-b/project_facts'), ('notes-b', 'project_facts'))
        self.assertEqual(mcp_route('local-docs', 'project_facts'), ('local-docs', 'project_facts'))
        self.assertEqual(mcp_route(None, 'project_facts'), ('local-docs', 'project_facts'))

    def test_same_named_tools_on_two_servers_are_distinct_sources(self):
        for sid, text in (('docs-a', 'Aster Tasks stores tasks in SQLite.'), ('notes-b', 'Release codename: Cobalt Finch.')):
            self.core.observe({'event_id': 'r-' + sid, 'type': 'tool_result', 'tool': 'mcp_call', 'agent_id': 'main',
                               'call_id': 'c-' + sid, 'server_id': sid, 'args': {'name': sid + '/project_facts'}, 'text': text})
        db = self.core.store.db
        uris = sorted(r['uri'] for r in db.execute("SELECT uri FROM sources WHERE type='MCP_RET'"))
        self.assertEqual(uris, ['mcp://docs-a/project_facts', 'mcp://notes-b/project_facts'])
        servers = sorted(r['id'] for r in db.execute("SELECT id FROM nodes WHERE kind='MCP_SERVER'"))
        self.assertEqual(servers, ['mcp:docs-a', 'mcp:notes-b'])
        observed = {r['source']: r['target'] for r in db.execute("SELECT source,target FROM edges WHERE kind='MCP_OBSERVATION'")}
        self.assertEqual(set(observed), {'mcp:docs-a', 'mcp:notes-b'})
        self.assertNotEqual(observed['mcp:docs-a'], observed['mcp:notes-b'])

    def test_error_result_without_server_id_is_attributed_by_qualified_name(self):
        self.core.observe({'event_id': 'r-err', 'type': 'tool_result', 'tool': 'mcp_call', 'agent_id': 'main', 'call_id': 'c-err',
                           'args': {'name': 'notes-b/project_facts'}, 'text': 'MCP_TOOL_ERROR', 'is_error': True, 'error_origin': 'external'})
        uri = self.core.store.db.execute("SELECT uri FROM sources WHERE type='MCP_RET'").fetchone()['uri']
        self.assertEqual(uri, 'mcp://notes-b/project_facts')

    def test_user_naming_qualified_or_bare_tool_authorizes_it(self):
        delta = {'tool': 'mcp.call', 'target': '', 'op': 'call'}
        anchor = {'mcp': ['docs-a/project_facts']}
        self.assertTrue(literal_scope(delta, {'name': 'docs-a/project_facts'}, anchor))
        self.assertFalse(literal_scope(delta, {'name': 'notes-b/save_note'}, anchor))
        self.assertTrue(literal_scope(delta, {'name': 'docs-a/project_facts'}, {'mcp': ['project_facts']}))


if __name__ == '__main__':
    unittest.main()
