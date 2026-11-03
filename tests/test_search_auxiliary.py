import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import eval_search
import search_memory as search


class AuxiliarySourcesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put('rules/existing.md', 'existingmarker')
        self.put('skills/alpha/SKILL.md', 'registeredmarker')
        self.put('skills/beta/SKILL.md', 'registeredmarker')
        self.put('guidance.md', 'rootguidancemarker')
        self.put('skills/alpha/references/shared.md', 'alphareferencemarker')
        self.put('skills/beta/references/shared.md', 'betareferencemarker')

    def put(self, path, content):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding='utf-8')

    def manifest(self, documents):
        self.put('search-sources.json', json.dumps({'version': 1, 'documents': documents}))

    def entries(self):
        return [
            {'path': 'guidance.md', 'kind': 'rule', 'role': 'guidance', 'reason': 'reviewed'},
            {'path': 'skills/alpha/references/shared.md', 'kind': 'skill-reference',
             'role': 'reference', 'parent_skill': 'alpha', 'reason': 'reviewed'},
            {'path': 'skills/beta/references/shared.md', 'kind': 'skill-reference',
             'role': 'reference', 'parent_skill': 'beta', 'reason': 'reviewed'},
        ]

    def test_manifest_is_opt_in_and_adds_reviewed_sources_with_distinct_names(self):
        root = str(self.root)
        self.assertFalse(search.search('rootguidancemarker', root))
        self.manifest(self.entries())
        index = search.build(root)
        self.assertEqual(search.search('rootguidancemarker', root, index=index)[0].doc.kind, 'rule')
        refs = [d for d in index['docs'] if d['kind'] == 'skill-reference']
        self.assertEqual(len(refs), 2)
        self.assertEqual(len({d['name'] for d in refs}), 2)
        self.assertIn('Skill references', search.catalog(index))
        self.assertEqual(search.search('alphareferencemarker', root, index=index)[0].doc.path,
                         str(self.root / 'skills/alpha/references/shared.md'))

    def test_invalid_manifest_and_paths_fail_closed(self):
        bad = [('../foreign.md', 'rule'), ('C:/foreign.md', 'rule'), ('/foreign.md', 'rule'),
               ('CLAUDE.md', 'rule'), ('AGENTS.md', 'rule'), ('INDEX.md', 'rule'),
               ('MEMORY.md', 'rule'), ('nested/file.md', 'rule'), ('notes.txt', 'rule'),
               ('skills/alpha/references/shared.md', 'rule'),
               ('skills/beta/references/shared.md', 'skill-reference')]
        for path, kind in bad:
            with self.subTest(path=path):
                self.manifest([{'path': path, 'kind': kind, 'role': 'reference',
                                'parent_skill': 'alpha', 'reason': 'reviewed'}])
                with self.assertRaises((ValueError, OSError)):
                    search.build(str(self.root))
        self.manifest(self.entries() + self.entries()[:1])
        with self.assertRaises(ValueError):
            search.build(str(self.root))
        for broken in ({'version': 2, 'documents': []}, {'version': 1, 'documents': [{}]},
                       {'version': 1, 'documents': [{**self.entries()[0], 'role': 'bogus'}]}):
            self.put('search-sources.json', json.dumps(broken))
            with self.assertRaises(ValueError):
                search.build(str(self.root))
        self.put('search-sources.json', '{')
        with self.assertRaises(ValueError):
            search.build(str(self.root))

    def test_manifest_and_content_change_or_removal_invalidates_cache(self):
        entries = self.entries()
        self.manifest(entries)
        root = str(self.root)
        self.assertTrue(search.write_index(root)[1])
        self.assertFalse(search.write_index(root)[1])
        entries[0]['reason'] = 'new audit'
        self.manifest(entries)
        self.assertTrue(search.write_index(root)[1])
        self.put('guidance.md', 'changedguidancemarker')
        self.assertTrue(search.write_index(root)[1])
        (self.root / 'guidance.md').unlink()
        with self.assertRaises(FileNotFoundError):
            search.load_index(root)
        self.manifest(entries[1:])
        self.assertTrue(search.write_index(root)[1])
        self.assertFalse(search.search('changedguidancemarker', root))

    def test_empty_reference_is_indexed_and_catalog_written(self):
        entry = self.entries()[1]
        self.manifest([entry])
        for content, name in (('', entry['path']), ('---\nname: emptyreference\n---\n', 'emptyreference')):
            with self.subTest(content=content):
                self.put(entry['path'], content)
                index, rebuilt = search.write_index(str(self.root))
                self.assertTrue(rebuilt)
                self.assertTrue(any(doc['name'] == name for doc in index['docs']))
                catalog_path = self.root / '.search-memory' / 'INDEX.md'
                self.assertIn(f'**{name}**:', catalog_path.read_text(encoding='utf-8'))
                self.assertFalse(search.write_index(str(self.root))[1])

    def test_source_realpath_cannot_escape_its_owner(self):
        original = os.path.realpath
        for entry in (self.entries()[0], self.entries()[1]):
            with self.subTest(kind=entry['kind']):
                self.manifest([entry])
                target = search.long_path(str(self.root / entry['path']))
                def escaped(path, *args, **kwargs):
                    if os.fspath(path) == target:
                        return str(self.root.parent / 'outside.md')
                    return original(path, *args, **kwargs)
                with patch('os.path.realpath', side_effect=escaped):
                    with self.assertRaises(ValueError):
                        search.build(str(self.root))

    def test_missing_registered_skill_and_missing_reference_fail(self):
        entry = self.entries()[1]
        self.manifest([entry])
        (self.root / 'skills/alpha/SKILL.md').unlink()
        with self.assertRaises(FileNotFoundError):
            search.build(str(self.root))
        self.put('skills/alpha/SKILL.md', 'registeredmarker')
        (self.root / entry['path']).unlink()
        with self.assertRaises(FileNotFoundError):
            search.build(str(self.root))

    def test_path_gold_is_exact_and_missing_gold_is_distinct(self):
        self.manifest(self.entries())
        index = search.build(str(self.root))
        hit = eval_search.case_rank({'query': 'betareferencemarker',
                                     'expect_path': 'skills/beta/references/shared.md'}, str(self.root), index)
        self.assertEqual(hit, (1, True))
        missing = eval_search.case_rank({'query': 'betareferencemarker',
                                         'expect_path': 'skills/missing/references/shared.md'}, str(self.root), index)
        self.assertEqual(missing, (None, False))
        legacy = eval_search.case_rank({'query': 'existingmarker', 'expect': 'existing'}, str(self.root), index)
        self.assertEqual(legacy, (1, True))

    def test_deep_home_discovers_sources_and_roundtrips_cache(self):
        deep = self.root / ('a' * 100) / ('b' * 100) / ('c' * 100)
        source = deep / 'projects' / 'project' / 'memory' / 'deep.md'
        os.makedirs(search.long_path(str(source.parent)), exist_ok=True)
        self.addCleanup(shutil.rmtree, search.long_path(str(deep)), True)
        with open(search.long_path(str(source)), 'w', encoding='utf-8') as fh:
            fh.write('---\nname: deepmarker\n---\ndeepmarker\n')
        root = search.resolve_root(str(deep))
        index, rebuilt = search.write_index(root)
        self.assertTrue(rebuilt)
        self.assertEqual(len(index['docs']), 1)
        self.assertEqual(search.search('deepmarker', root)[0].doc.path, str(source))
        self.assertFalse(search.write_index(root)[1])

    def test_layer_fragments_compose_without_copying_company_catalog_into_personal_layer(self):
        self.manifest(self.entries()[:1])
        fragment = 'search-sources.d/company.json'
        self.put(fragment, json.dumps({'version': 1, 'documents': self.entries()[1:]}))
        root = str(self.root)
        self.assertTrue(search.write_index(root)[1])
        self.assertEqual(search.search('betareferencemarker', root)[0].doc.kind, 'skill-reference')
        self.put(fragment, json.dumps({'version': 1, 'documents': self.entries()[1:2]}))
        self.assertTrue(search.write_index(root)[1])
        self.assertFalse(search.search('betareferencemarker', root))
        self.put(fragment, json.dumps({'version': 1, 'documents': self.entries()[:1]}))
        with self.assertRaises(ValueError):
            search.build(root)


if __name__ == '__main__':
    unittest.main()
