"""Isolation of search and hook state across independently composed homes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class SearchIsolationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.tools = self.base / 'repo' / 'tools'
        shutil.copytree(Path(__file__).resolve().parents[1] / 'tools', self.tools)
        self.a, self.b = self.base / 'alpha', self.base / 'beta'
        for root, word in ((self.a, 'alphaunique'), (self.b, 'betaunique')):
            path = root / 'projects' / 'p' / 'memory' / 'item.md'
            path.parent.mkdir(parents=True)
            path.write_text(f'---\nname: {word}\n---\n{word}\n', encoding='utf-8')
        self.env = {**os.environ, 'HOME': str(self.base), 'USERPROFILE': str(self.base),
                    'CLAUDE_CONFIG_DIR': str(self.a)}
        for key in ('CODEX_HOME', 'HOMEDRIVE', 'HOMEPATH', 'COMPANIES_FILE'):
            self.env.pop(key, None)

    def tearDown(self):
        self.temp.cleanup()

    def run_search(self, *args, env=None):
        return subprocess.run([sys.executable, '-I', str(self.tools / 'search_memory.py'), *args],
                              capture_output=True, text=True, env=env or self.env)

    def test_env_homes_and_explicit_root_have_separate_indexes(self):
        a = self.run_search('--build', '--quiet')
        b = self.run_search('--build', '--quiet', '--root', str(self.b))
        self.assertEqual((a.returncode, b.returncode), (0, 0), a.stderr + b.stderr)
        for root, own, other in ((self.a, 'alphaunique', 'betaunique'), (self.b, 'betaunique', 'alphaunique')):
            index = (root / '.search-memory' / 'search-index.json').read_text(encoding='utf-8')
            catalog = (root / '.search-memory' / 'INDEX.md').read_text(encoding='utf-8')
            self.assertIn(own, index + catalog)
            self.assertNotIn(other, index + catalog)
        self.assertFalse((self.base / 'repo' / 'INDEX.md').exists())
        self.assertIn('alphaunique', self.run_search('alphaunique').stdout)
        self.assertIn('No match', self.run_search('betaunique').stdout)
        self.assertIn('betaunique', self.run_search('betaunique', '--root', str(self.b)).stdout)

    def test_codex_company_mapping_and_unknown_home_fail_closed(self):
        codex_a = self.base / 'codex-a'
        codex_b = self.base / 'codex-b'
        config = self.base / 'companies.json'
        config.write_text(json.dumps({'companies': {
            'a': {'home': {'claude': str(self.a), 'codex': str(codex_a)}},
            'b': {'home': {'claude': str(self.b), 'codex': str(codex_b)}}}}), encoding='utf-8')
        env = {**self.env, 'COMPANIES_FILE': str(config), 'CODEX_HOME': str(codex_b)}
        env.pop('CLAUDE_CONFIG_DIR')
        self.assertIn('betaunique', self.run_search('betaunique', env=env).stdout)
        self.assertIn('No match', self.run_search('alphaunique', env=env).stdout)
        env['CODEX_HOME'] = str(self.base / 'unmapped')
        result = self.run_search('alphaunique', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no unique company', result.stderr)
        self.assertIn('alphaunique', self.run_search('alphaunique', '--root', str(self.a), env=env).stdout)

    def test_missing_home_fails_and_composed_global_is_indexed(self):
        env = {**self.env, 'CLAUDE_CONFIG_DIR': str(self.base / 'missing')}
        result = self.run_search('--build', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('root does not exist', result.stderr)
        self.assertFalse((self.base / 'missing').exists())
        global_file = self.b / 'global' / 'company.md'
        global_file.parent.mkdir()
        global_file.write_text('betaglobalunique', encoding='utf-8')
        self.assertIn('company.md', self.run_search('betaglobalunique', '--root', str(self.b)).stdout)

    def test_default_personal_home_keeps_legacy_paths(self):
        env = {**self.env, 'USERPROFILE': str(self.base), 'HOME': str(self.base)}
        env.pop('CLAUDE_CONFIG_DIR')
        default = self.base / '.claude'
        default.mkdir()
        result = self.run_search('--build', '--quiet', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.base / 'repo' / 'index' / 'search-index.json').is_file())
        self.assertTrue((self.base / 'repo' / 'INDEX.md').is_file())

    def test_root_with_glob_characters_never_reads_a_sibling(self):
        for folder in ('company[ab]', 'normalcompany'):
            with self.subTest(folder=folder):
                root = self.base / folder
                other = self.base / ('companya' if '[' in folder else 'othercompany')
                for home, marker in ((root, 'selectedonly'), (other, 'foreignonly')):
                    for relative in ('projects/p/memory/item.md', 'rules/item.md',
                                     'global/item.md', 'skills/item/SKILL.md'):
                        path = home / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(f'---\nname: {marker}\n---\n{marker}\n', encoding='utf-8')
                built = self.run_search('--build', '--quiet', '--root', str(root))
                self.assertEqual(built.returncode, 0, built.stderr)
                index = json.loads((root / '.search-memory' / 'search-index.json').read_text(encoding='utf-8'))
                self.assertEqual([doc['name'] for doc in index['docs']], ['selectedonly'] * 4)
                self.assertIn('selectedonly', self.run_search('selectedonly', '--root', str(root)).stdout)
                self.assertIn('No match', self.run_search('foreignonly', '--root', str(root)).stdout)

    def test_changed_content_and_glossary_invalidate_cache_even_with_old_mtime(self):
        import time
        source = self.a / 'projects' / 'p' / 'memory' / 'item.md'
        glossary = self.a / 'ubiquitous-language.md'
        glossary.write_text('| brain | old | **alphaunique** |\n', encoding='utf-8')
        old = time.time() - 1000
        os.utime(source, (old, old))
        os.utime(glossary, (old, old))
        self.assertEqual(self.run_search('--build', '--quiet').returncode, 0)
        source.write_text('---\nname: currentpublic\n---\ncurrentpublic\n', encoding='utf-8')
        glossary.write_text('| brain | new | **currentpublic** |\n', encoding='utf-8')
        os.utime(source, (old, old))
        os.utime(glossary, (old, old))
        self.assertIn('No match', self.run_search('alphaunique').stdout)
        self.assertIn('currentpublic', self.run_search('brain').stdout)
        self.assertEqual(self.run_search('--build', '--quiet').returncode, 0)
        cache = json.loads((self.a / '.search-memory' / 'search-index.json').read_text(encoding='utf-8'))
        self.assertEqual(cache['docs'][0]['name'], 'currentpublic')
        cache['version'] = 2
        cache_path = self.a / '.search-memory' / 'search-index.json'
        cache_path.write_text(json.dumps(cache), encoding='utf-8')
        self.assertEqual(self.run_search('--build', '--quiet').returncode, 0)
        self.assertEqual(json.loads(cache_path.read_text(encoding='utf-8'))['version'], 3)
        glossary.write_text('| brain | new | **nowmissing** |\n', encoding='utf-8')
        os.utime(glossary, (old, old))
        self.assertIn('No match', self.run_search('brain').stdout)

    def test_resolve_root_api_validates_explicit_and_environment_homes(self):
        script = ("import sys; sys.path.insert(0, sys.argv[1]); "
                  "from search_memory import resolve_root; print(resolve_root(sys.argv[2]))")
        command = [sys.executable, '-I', '-c', script, str(self.tools)]
        selected = subprocess.run([*command, str(self.b)], env=self.env, capture_output=True, text=True)
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(Path(selected.stdout.strip()), self.b)
        missing = subprocess.run([*command, str(self.base / 'absent')], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('root does not exist', missing.stderr)

    def test_hook_rebuilds_only_the_selected_home(self):
        path = self.a / 'projects' / 'p' / 'memory' / 'item.md'
        run = subprocess.run([sys.executable, '-I', str(self.tools / 'index_hook.py')],
                             input=json.dumps({'tool_input': {'file_path': str(path)}}),
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue((self.a / '.search-memory' / 'search-index.json').exists())
        self.assertFalse((self.b / '.search-memory').exists())

if __name__ == '__main__':
    unittest.main()
