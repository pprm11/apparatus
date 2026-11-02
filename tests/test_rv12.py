import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from test_company_compose import CompanySandbox, write

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import compose


class UpdatePersonaTest(CompanySandbox):
    def setUp(self):
        super().setUp()
        self.home = Path(self.tmp) / 'home'
        self.claude, self.codex = self.home / '.claude', self.home / '.codex'
        self.claude.mkdir(parents=True)
        self.codex.mkdir()
        persona = Path(self.codes) / 'persona'
        write(str(persona / 'layer.json'), json.dumps({'level': 'persona', 'mode': 'readonly'}))
        write(str(persona / 'skills' / 'root-cause' / 'SKILL.md'), '---\nname: root-cause\ndescription: Diagnose.\n---\nbody\n')
        ident = Path(self.codes) / 'id'
        cfg = json.loads((ident / 'layer.json').read_text(encoding='utf-8'))
        cfg['skill_aliases'] = 'aliases.json'
        (ident / 'layer.json').write_text(json.dumps(cfg), encoding='utf-8')
        write(str(ident / 'aliases.json'), json.dumps({'aliases': {'root-cause': {'target': 'root-cause', 'description': 'Diagnostica.'}}}))
        man = json.loads(Path(self.manifest).read_text(encoding='utf-8'))
        man['layers'] = [l for l in man['layers'] if l['level'] in ('superego', 'id')]
        man['layers'].insert(1, {'level': 'persona', 'path': str(persona), 'mode': 'readonly', 'active': True})
        Path(self.manifest).write_text(json.dumps(man), encoding='utf-8')
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), CLAUDE_CONFIG_DIR=str(self.claude),
                        CODEX_HOME=str(self.codex), SUPEREGO_HOME=str(self.home / 'state'), GIT_TERMINAL_PROMPT='0',
                        GIT_ALLOW_PROTOCOL='file')
        initial = subprocess.run([sys.executable, '-I', str(ROOT / 'tools' / 'compose.py'), '--manifest', self.manifest,
                                  '--claude-home', str(self.claude), '--codex-home', str(self.codex)],
                                 env=self.env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(initial.returncode, 0, initial.stderr)

    def update(self):
        return subprocess.run([sys.executable, '-I', str(ROOT / 'tools' / 'onboard.py'), '--claude-home', str(self.claude),
                               '--codex-home', str(self.codex), 'update', '--manifest', self.manifest, '--no-pull'],
                              env=self.env, capture_output=True, text=True, encoding='utf-8')

    def test_update_twice_keeps_composed_overlay(self):
        skill = self.claude / 'skills' / 'root-cause' / 'SKILL.md'
        before = skill.read_bytes()
        self.assertIn(b'Diagnostica.', before)
        for _ in range(2):
            result = self.update()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(skill.read_bytes(), before)

    def test_update_edit_preflight_stops_before_other_restore_writes(self):
        skill = self.claude / 'skills' / 'root-cause' / 'SKILL.md'
        skill.write_text('manual edit\n', encoding='utf-8')
        source = Path(self.codes) / 'superego' / 'global' / 'rules-general.md'
        source.write_text('NEW SHARED CONTENT\n', encoding='utf-8')
        before = {p.relative_to(self.home).as_posix(): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        after = {p.relative_to(self.home).as_posix(): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(after, before)


    def test_dry_run_does_not_recover_a_pending_transaction(self):
        source = Path(self.codes) / 'persona' / 'skills' / 'root-cause'
        dest = self.claude / 'skills'
        original = compose.os.replace
        fired = False
        def fail_receipt_once(src, dst):
            nonlocal fired
            if Path(dst) == dest / '.persona-skills.json' and not fired:
                fired = True
                raise OSError('injected receipt failure')
            return original(src, dst)
        alias = {'root-cause': {'target': 'root-cause', 'description': 'Diagnostica.'}}
        with mock.patch.object(compose.os, 'replace', side_effect=fail_receipt_once), \
             mock.patch.object(compose, '_recover_skill_transaction', side_effect=lambda path: (_ for _ in ()).throw(RuntimeError('unavailable')) if Path(path).exists() else None):
            with self.assertRaises((OSError, RuntimeError)):
                compose.sync_company_skills({'root-cause': str(source)}, str(dest), False, aliases=alias, marker_name='.persona-skills.json')
        before = {p.relative_to(self.home).as_posix(): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        result = subprocess.run([sys.executable, '-I', str(ROOT / 'tools' / 'compose.py'), '--manifest', self.manifest,
                                 '--claude-home', str(self.claude), '--codex-home', str(self.codex), '--skills-only', '--dry-run'],
                                env=self.env, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        after = {p.relative_to(self.home).as_posix(): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(after, before)
        result = subprocess.run([sys.executable, '-I', str(ROOT / 'tools' / 'compose.py'), '--manifest', self.manifest,
                                 '--claude-home', str(self.claude), '--codex-home', str(self.codex), '--skills-only'],
                                env=self.env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)


class TransactionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.dst = self.base / 'skills'
        self.a = self.base / 'src-a'
        self.b = self.base / 'src-b'
        self.old = self.base / 'src-old'
        for src, name in ((self.a, 'alpha'), (self.b, 'beta'), (self.old, 'obsolete')):
            write(str(src / 'SKILL.md'), f'---\nname: {name}\ndescription: Test.\n---\nold\n')
        self.marker = '.persona-skills.json'
        compose.sync_company_skills({'alpha': str(self.a), 'obsolete': str(self.old)}, str(self.dst), False, marker_name=self.marker)
        (self.a / 'SKILL.md').write_text('---\nname: alpha\ndescription: Test.\n---\nupdated\n', encoding='utf-8')

    def snapshot(self):
        return {p.relative_to(self.dst).as_posix(): p.read_bytes() for p in self.dst.rglob('*') if p.is_file() and not p.name.startswith('.skill-lock-')}

    def invoke(self):
        return compose.sync_company_skills({'alpha': str(self.a), 'beta': str(self.b)}, str(self.dst), False, marker_name=self.marker)

    def test_copy_failure_keeps_old_trees_and_receipt(self):
        before = self.snapshot()
        original = compose.shutil.copytree
        def fail_second(src, dst, *args, **kwargs):
            if Path(src) == self.b:
                raise OSError('injected copy failure')
            return original(src, dst, *args, **kwargs)
        with mock.patch.object(compose.shutil, 'copytree', side_effect=fail_second):
            with self.assertRaises(OSError):
                self.invoke()
        self.assertEqual(self.snapshot(), before)
        self.invoke()
        self.assertFalse((self.dst / 'obsolete').exists())
        self.assertIn('updated', (self.dst / 'alpha' / 'SKILL.md').read_text(encoding='utf-8'))

    def test_rename_failure_rolls_back_old_trees_and_receipt(self):
        before = self.snapshot()
        original = compose.os.replace
        count = 0
        def fail_once(src, dst):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected rename failure')
            return original(src, dst)
        with mock.patch.object(compose.os, 'replace', side_effect=fail_once):
            with self.assertRaises(OSError):
                self.invoke()
        self.assertEqual(self.snapshot(), before)
        self.invoke()

    def test_receipt_failure_keeps_old_trees_and_receipt(self):
        before = self.snapshot()
        original = compose.write_text
        def fail_receipt(path, text):
            if Path(path).name == self.marker:
                raise OSError('injected receipt failure')
            return original(path, text)
        with mock.patch.object(compose, 'write_text', side_effect=fail_receipt):
            with self.assertRaises(OSError):
                self.invoke()
        self.assertEqual(self.snapshot(), before)
        self.invoke()

    def test_interrupted_commit_recovers_before_retry(self):
        before = self.snapshot()
        original = compose.os.replace
        count = 0
        def fail_once(src, dst):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected interruption')
            return original(src, dst)
        with mock.patch.object(compose.os, 'replace', side_effect=fail_once), \
             mock.patch.object(compose, '_recover_skill_transaction', side_effect=lambda path: (_ for _ in ()).throw(RuntimeError('recovery unavailable')) if Path(path).exists() else None):
            with self.assertRaises((OSError, RuntimeError)):
                self.invoke()
        self.invoke()
        self.assertFalse((self.dst / 'obsolete').exists())
        self.assertIn('updated', (self.dst / 'alpha' / 'SKILL.md').read_text(encoding='utf-8'))

    def test_recovery_refuses_intervening_manual_edit(self):
        original = compose.os.replace
        count = 0
        def fail_once(src, dst):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected interruption')
            return original(src, dst)
        with mock.patch.object(compose.os, 'replace', side_effect=fail_once), \
             mock.patch.object(compose, '_recover_skill_transaction', side_effect=lambda path: (_ for _ in ()).throw(RuntimeError('recovery unavailable')) if Path(path).exists() else None):
            with self.assertRaises((OSError, RuntimeError)):
                self.invoke()
        skill = self.dst / 'alpha' / 'SKILL.md'
        skill.parent.mkdir(exist_ok=True)
        skill.write_text('manual edit after interruption\n', encoding='utf-8')
        with self.assertRaises((SystemExit, RuntimeError)):
            self.invoke()
        self.assertEqual(skill.read_text(encoding='utf-8'), 'manual edit after interruption\n')

    def test_late_receipt_rename_failure_removes_new_skill_and_restores_old(self):
        before = self.snapshot()
        original = compose.os.replace
        fired = False
        def fail_receipt_once(src, dst):
            nonlocal fired
            if Path(dst) == self.dst / self.marker and not fired:
                fired = True
                raise OSError('injected receipt rename failure')
            return original(src, dst)
        with mock.patch.object(compose.os, 'replace', side_effect=fail_receipt_once):
            with self.assertRaises(OSError):
                self.invoke()
        self.assertEqual(self.snapshot(), before)
        self.invoke()

    def test_manual_edit_during_staging_aborts_before_any_swap(self):
        original = compose.shutil.copytree
        edited = self.dst / 'alpha' / 'SKILL.md'
        def edit_during_copy(src, dst, *args, **kwargs):
            if Path(src) == self.b:
                edited.write_text('manual during staging\n', encoding='utf-8')
            return original(src, dst, *args, **kwargs)
        with mock.patch.object(compose.shutil, 'copytree', side_effect=edit_during_copy):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertEqual(edited.read_text(encoding='utf-8'), 'manual during staging\n')
        self.assertTrue((self.dst / 'obsolete' / 'SKILL.md').exists())

    def test_commit_journal_rename_failure_rolls_back_everything(self):
        before = self.snapshot()
        original = compose.os.replace
        fired = False
        def fail_commit_once(src, dst):
            nonlocal fired
            if Path(dst).name == 'journal.json' and not fired:
                fired = True
                raise OSError('injected journal rename failure')
            return original(src, dst)
        with mock.patch.object(compose.os, 'replace', side_effect=fail_commit_once):
            with self.assertRaises(OSError):
                self.invoke()
        self.assertEqual(self.snapshot(), before)
        self.invoke()

    def test_second_writer_cannot_recover_active_transaction(self):
        code = """import sys,time
sys.path.insert(0,sys.argv[1])
import compose
with compose._skill_lock(sys.argv[2], '.persona-skills.json', False):
 print('locked',flush=True)
 time.sleep(20)
"""
        proc = subprocess.Popen([sys.executable, '-I', '-c', code, str(ROOT / 'tools'), str(self.dst)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        try:
            self.assertEqual(proc.stdout.readline().strip(), 'locked')
            before = self.snapshot()
            with self.assertRaises((SystemExit, BlockingIOError)):
                self.invoke()
            self.assertEqual(self.snapshot(), before)
        finally:
            proc.terminate()
            proc.communicate(timeout=10)

    def test_process_crash_after_rename_recovers_on_next_run(self):
        code = """import os,sys
sys.path.insert(0,sys.argv[1])
import compose
original=compose.os.replace
count=0
def die_on_second(src,dst):
 global count
 count+=1
 if count==2: os._exit(92)
 return original(src,dst)
compose.os.replace=die_on_second
compose.sync_company_skills({'alpha':sys.argv[3],'beta':sys.argv[4]},sys.argv[2],False,marker_name='.persona-skills.json')
"""
        proc = subprocess.run([sys.executable, '-I', '-c', code, str(ROOT / 'tools'), str(self.dst), str(self.a), str(self.b)], capture_output=True)
        self.assertEqual(proc.returncode, 92)
        self.invoke()
        self.assertFalse((self.dst / 'obsolete').exists())
        self.assertIn('updated', (self.dst / 'alpha' / 'SKILL.md').read_text(encoding='utf-8'))

    def test_process_crash_during_staging_recovers_on_next_run(self):
        code = """import os,sys
sys.path.insert(0,sys.argv[1])
import compose
def die(*args,**kwargs): os._exit(91)
compose.shutil.copytree=die
compose.sync_company_skills({'alpha':sys.argv[3],'beta':sys.argv[4]},sys.argv[2],False,marker_name='.persona-skills.json')
"""
        proc = subprocess.run([sys.executable, '-I', '-c', code, str(ROOT / 'tools'), str(self.dst), str(self.a), str(self.b)], capture_output=True)
        self.assertEqual(proc.returncode, 91)
        self.invoke()
        self.assertFalse((self.dst / 'obsolete').exists())
        self.assertIn('updated', (self.dst / 'alpha' / 'SKILL.md').read_text(encoding='utf-8'))



class CompanyReceiptTest(CompanySandbox):
    def setUp(self):
        super().setUp()
        self.persona = Path(self.codes) / 'persona'
        write(str(self.persona / 'layer.json'), json.dumps({'level': 'persona', 'mode': 'readonly'}))
        write(str(self.persona / 'skills' / 'example' / 'SKILL.md'), '---\nname: example\ndescription: Test.\n---\nold\n')
        man = json.loads(Path(self.manifest).read_text(encoding='utf-8'))
        man['layers'].insert(1, {'level': 'persona', 'path': str(self.persona), 'mode': 'readonly', 'active': True})
        Path(self.manifest).write_text(json.dumps(man), encoding='utf-8')
        import layers
        self.man = layers.load_manifest(self.manifest)
        self.data = {'companies': {'alpha': {}}}
        self.out = Path(self.tmp) / 'company'
        self.assertEqual(compose.compose_company(self.man, 'alpha', self.data, str(self.out), note=lambda _: None), 0)
        write(str(self.persona / 'skills' / 'example' / 'SKILL.md'), '---\nname: example\ndescription: Test.\n---\nnew\n')

    def snapshot_skills(self):
        paths = [p for p in (self.out / 'skills').rglob('*') if p.is_file() and not p.name.startswith('.skill-lock-')]
        paths.append(self.out / '.persona-skills.json')
        return {p.relative_to(self.out).as_posix(): p.read_bytes() for p in paths}

    def test_company_receipt_failure_rolls_back_skill_batch(self):
        before = self.snapshot_skills()
        original = compose.os.replace
        fired = False
        def fail_receipt_once(src, dst):
            nonlocal fired
            if Path(dst) == self.out / '.persona-skills.json' and not fired:
                fired = True
                raise OSError('injected company receipt failure')
            return original(src, dst)
        with mock.patch.object(compose.os, 'replace', side_effect=fail_receipt_once):
            with self.assertRaises(OSError):
                compose.compose_company(self.man, 'alpha', self.data, str(self.out), note=lambda _: None)
        self.assertEqual(self.snapshot_skills(), before)
        self.assertEqual(compose.compose_company(self.man, 'alpha', self.data, str(self.out), note=lambda _: None), 0)

    def test_company_edit_between_preflight_and_lock_is_preserved(self):
        skill = self.out / 'skills' / 'example' / 'SKILL.md'
        receipt = (self.out / '.persona-skills.json').read_bytes()
        original = compose.sync_company_skills
        def edit_before_lock(*args, **kwargs):
            skill.write_text('MANUAL_EDIT\n', encoding='utf-8')
            return original(*args, **kwargs)
        with mock.patch.object(compose, 'sync_company_skills', side_effect=edit_before_lock):
            with self.assertRaises(SystemExit):
                compose.compose_company(self.man, 'alpha', self.data, str(self.out), note=lambda _: None)
        self.assertEqual(skill.read_text(encoding='utf-8'), 'MANUAL_EDIT\n')
        self.assertEqual((self.out / '.persona-skills.json').read_bytes(), receipt)

    def test_company_edit_after_locked_validation_is_not_accepted_as_before_image(self):
        skill = self.out / 'skills' / 'example' / 'SKILL.md'
        receipt = (self.out / '.persona-skills.json').read_bytes()
        original = compose._company_receipt_guard
        calls = 0
        def edit_after_guard(*args, **kwargs):
            nonlocal calls
            result = original(*args, **kwargs)
            calls += 1
            if calls == 2:
                skill.write_text('SECOND_MANUAL_EDIT\n', encoding='utf-8')
            return result
        with mock.patch.object(compose, '_company_receipt_guard', side_effect=edit_after_guard):
            with self.assertRaises(SystemExit):
                compose.compose_company(self.man, 'alpha', self.data, str(self.out), note=lambda _: None)
        self.assertEqual(skill.read_text(encoding='utf-8'), 'SECOND_MANUAL_EDIT\n')
        self.assertEqual((self.out / '.persona-skills.json').read_bytes(), receipt)


class NoOpLockTest(unittest.TestCase):
    def test_empty_skill_set_without_receipt_does_not_create_lock_or_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'home'
            home.mkdir()
            before = sorted(home.iterdir())
            self.assertEqual(compose.sync_company_skills({}, str(home / 'skills'), False), [])
            self.assertEqual(sorted(home.iterdir()), before)
            self.assertFalse((home / 'skills').exists())

    def test_noop_preserves_existing_foreign_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'home'
            home.mkdir()
            lock = Path(compose._skill_lock_path(str(home / 'skills'), '.persona-skills.json'))
            lock.write_text('foreign', encoding='utf-8')
            self.assertEqual(compose.sync_company_skills({}, str(home / 'skills'), False, marker_name='.persona-skills.json'), [])
            self.assertEqual(lock.read_text(encoding='utf-8'), 'foreign')
            self.assertFalse((home / 'skills').exists())
