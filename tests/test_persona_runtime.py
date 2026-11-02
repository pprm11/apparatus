import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_company_compose import CompanySandbox, write

class PersonaRuntimeTest(CompanySandbox):
    def setup_persona(self):
        man = json.loads(Path(self.manifest).read_text(encoding='utf-8'))
        persona = Path(self.codes) / 'persona'
        write(str(persona / 'layer.json'), json.dumps({'level': 'persona', 'mode': 'readonly'}))
        write(str(persona / 'skills' / 'root-cause' / 'SKILL.md'), '---\nname: root-cause\ndescription: Diagnose.\n---\nCanonical procedure.\n')
        man['layers'].insert(1, {'level': 'persona', 'path': str(persona), 'active': True, 'mode': 'readonly'})
        Path(self.manifest).write_text(json.dumps(man), encoding='utf-8')
        config = Path(self.codes) / 'id' / 'layer.json'
        data = json.loads(config.read_text(encoding='utf-8'))
        data['skill_aliases'] = 'locales/pt-BR/skills.json'
        config.write_text(json.dumps(data), encoding='utf-8')
        write(str(Path(self.codes) / 'id' / data['skill_aliases']), json.dumps({'aliases': {'causa-raiz': {'target': 'root-cause', 'description': 'Diagnostica causas.'}}}))

    def test_company_canonical_and_alias(self):
        self.setup_persona()
        out = os.path.join(self.tmp, 'out')
        result = self.cli('--company', 'alpha', '--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        root = Path(out) / 'skills'
        self.assertIn('Canonical procedure', (root / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertIn('root-cause', (root / 'causa-raiz' / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertEqual(self.cli('--company', 'alpha', '--out', out).returncode, 0)
        self.assertIn('causa-raiz', json.loads((Path(out) / '.persona-skills.json').read_text(encoding='utf-8'))['skills'])

    def test_unknown_target_fails_before_writing(self):
        self.setup_persona()
        p = Path(self.codes) / 'id' / 'locales' / 'pt-BR' / 'skills.json'
        p.write_text(json.dumps({'aliases': {'causa-raiz': {'target': 'missing', 'description': 'x'}}}), encoding='utf-8')
        out = os.path.join(self.tmp, 'out')
        result = self.cli('--company', 'alpha', '--out', out)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(out))

    def test_default_composition_and_export_ignore_generated(self):
        self.setup_persona()
        home = Path(self.tmp) / 'claude'
        codex = Path(self.tmp) / 'codex'
        codex.mkdir()
        write(str(home / 'harness' / 'codex.md'), 'adapter\n')
        result = self.cli('--claude-home', str(home), '--codex-home', str(codex))
        self.assertEqual(result.returncode, 0, result.stderr)
        for base in (home, codex):
            self.assertTrue((base / 'skills' / 'root-cause' / 'SKILL.md').is_file())
            self.assertTrue((base / 'skills' / 'causa-raiz' / 'SKILL.md').is_file())
        import layers
        man = layers.load_manifest(self.manifest)
        routed = layers.plan(man, str(home))
        self.assertFalse(any('root-cause' in src or 'causa-raiz' in src for entries in routed.values() for src, _ in entries))

    def test_filter_alias_and_canonical_in_codex(self):
        self.setup_persona()
        write(str(Path(self.codes) / 'superego' / 'harness' / 'skills.json'), json.dumps({'claude_only': ['root-cause']}))
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        write(str(home / 'harness' / 'codex.md'), 'adapter\n')
        write(str(home / 'harness' / 'skills.json'), json.dumps({'claude_only': ['root-cause']}))
        self.assertEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex)).returncode, 0)
        self.assertTrue((home / 'skills' / 'causa-raiz' / 'SKILL.md').is_file())
        self.assertFalse((codex / 'skills' / 'root-cause').exists())
        self.assertFalse((codex / 'skills' / 'causa-raiz').exists())

    def test_unmanaged_skills_and_export_are_preserved(self):
        self.setup_persona()
        out = Path(self.tmp) / 'out'
        self.assertEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        import layers
        man = layers.load_manifest(self.manifest)
        repo = Path(self.codes) / 'ego-alpha'
        write(str(repo / 'skills' / 'root-cause' / 'SKILL.md'), 'private existing\n')
        layers.export(man, str(out), 'ego')
        self.assertEqual((repo / 'skills' / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8'), 'private existing\n')
        self.assertFalse((repo / 'skills' / 'causa-raiz').exists())

    def test_private_wrapper_wins_but_unknown_target_still_fails(self):
        self.setup_persona()
        wrapper = Path(self.codes) / 'id' / 'skills' / 'causa-raiz' / 'SKILL.md'
        write(str(wrapper), 'private wrapper\n')
        out = Path(self.tmp) / 'out'
        self.assertEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        self.assertEqual((out / 'skills' / 'causa-raiz' / 'SKILL.md').read_text(encoding='utf-8'), 'private wrapper\n')
        p = Path(self.codes) / 'id' / 'locales' / 'pt-BR' / 'skills.json'
        p.write_text(json.dumps({'aliases': {'causa-raiz': {'target': 'missing', 'description': 'x'}}}), encoding='utf-8')
        self.assertNotEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)

    def test_same_name_overlay_preserves_canonical_source(self):
        self.setup_persona()
        p = Path(self.codes) / 'id' / 'locales' / 'pt-BR' / 'skills.json'
        p.write_text(json.dumps({'aliases': {'root-cause': {'target': 'root-cause', 'description': 'Causas e diagnostico.'}}}), encoding='utf-8')
        out = Path(self.tmp) / 'out'
        self.assertEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        self.assertIn('Causas e diagnostico.', (out / 'skills' / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertIn('Diagnose.', (Path(self.codes) / 'persona' / 'skills' / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8'))

    def test_default_canonical_collision_fails_without_overwriting(self):
        self.setup_persona()
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        old = home / 'skills' / 'root-cause' / 'SKILL.md'
        write(str(old), 'unmanaged skill\n')
        result = self.cli('--claude-home', str(home), '--codex-home', str(codex))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(old.read_text(encoding='utf-8'), 'unmanaged skill\n')
        self.assertFalse((home / 'CLAUDE.md').exists())

    def test_unmarked_level_less_readonly_collision_refuses_export(self):
        self.setup_persona()
        import layers
        home = Path(self.tmp) / 'claude'
        write(str(home / 'skills' / 'root-cause' / 'SKILL.md'), '---\nname: root-cause\n---\nbody\n')
        man = layers.load_manifest(self.manifest)
        with self.assertRaises(SystemExit):
            layers.export(man, str(home), 'ego')

    def test_company_codex_filters_canonical_and_alias(self):
        self.setup_persona()
        write(str(Path(self.codes) / 'superego' / 'harness' / 'skills.json'), json.dumps({'claude_only': ['root-cause']}))
        codex = Path(self.tmp) / 'codex'
        codex.mkdir()
        import subprocess
        result = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve().parent.parent / 'tools' / 'render_harness.py'), '--company', 'alpha', '--manifest', self.manifest, '--companies', self.companies, '--codes', self.codes, '--codex-home', str(codex)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((codex / 'skills' / 'root-cause').exists())
        self.assertFalse((codex / 'skills' / 'causa-raiz').exists())

    def test_skills_only_preserves_existing_context(self):
        self.setup_persona()
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        write(str(home / 'CLAUDE.md'), '@~/.claude/regras-de-agente.md\n')
        write(str(codex / 'AGENTS.md'), 'existing agent rules\n')
        result = self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((home / 'CLAUDE.md').read_text(encoding='utf-8'), '@~/.claude/regras-de-agente.md\n')
        self.assertEqual((codex / 'AGENTS.md').read_text(encoding='utf-8'), 'existing agent rules\n')
        self.assertTrue((codex / 'skills' / 'causa-raiz' / 'SKILL.md').is_file())

    def test_skills_only_uses_superego_harness_filter(self):
        self.setup_persona()
        write(str(Path(self.codes) / 'superego' / 'harness' / 'skills.json'), json.dumps({'claude_only': ['root-cause']}))
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        self.assertEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        self.assertTrue((home / 'skills' / 'causa-raiz' / 'SKILL.md').is_file())
        self.assertFalse((codex / 'skills' / 'root-cause').exists())
        self.assertFalse((codex / 'skills' / 'causa-raiz').exists())

    def test_alias_only_filter_also_excludes_canonical(self):
        self.setup_persona()
        write(str(Path(self.codes) / 'superego' / 'harness' / 'skills.json'), json.dumps({'claude_only': ['causa-raiz']}))
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        self.assertEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        self.assertFalse((codex / 'skills' / 'root-cause').exists())
        self.assertFalse((codex / 'skills' / 'causa-raiz').exists())

    def test_same_name_overlay_keeps_english_description(self):
        self.setup_persona()
        p = Path(self.codes) / 'id' / 'locales' / 'pt-BR' / 'skills.json'
        p.write_text(json.dumps({'aliases': {'root-cause': {'target': 'root-cause', 'description': 'Diagnostica causas.'}}}), encoding='utf-8')
        out = Path(self.tmp) / 'out'
        self.assertEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        content = (out / 'skills' / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('Diagnose.', content)
        self.assertIn('Diagnostica causas.', content)

    def test_edited_generated_alias_aborts_before_overwriting(self):
        self.setup_persona()
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        self.assertEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        alias = home / 'skills' / 'causa-raiz' / 'SKILL.md'
        alias.write_text('user edit\n', encoding='utf-8')
        self.assertNotEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        self.assertEqual(alias.read_text(encoding='utf-8'), 'user edit\n')

    def test_orphan_reference_is_not_pruned_from_repo(self):
        self.setup_persona()
        import layers
        home = Path(self.tmp) / 'claude'
        orphan = Path(self.codes) / 'id' / 'skills' / 'causa-raiz' / 'references' / 'private.md'
        write(str(orphan), 'private resource\n')
        layers.export(layers.load_manifest(self.manifest), str(home), 'id')
        self.assertEqual(orphan.read_text(encoding='utf-8'), 'private resource\n')

    def test_canonical_routes_to_private_policy_without_recursive_invocation(self):
        self.setup_persona()
        wrapper = Path(self.codes) / 'ego-alpha' / 'skills' / 'causa-raiz' / 'SKILL.md'
        write(str(wrapper), '---\nname: causa-raiz\ndescription: local\n---\nUse root-cause then apply local policy.\n')
        out = Path(self.tmp) / 'out'
        self.assertEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        canonical = (out / 'skills' / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('causa-raiz', canonical)
        self.assertIn('policy', canonical.lower())

    def test_generated_alias_transition_to_wrapper_aborts_and_keeps_both(self):
        self.setup_persona()
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        self.assertEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        alias = home / 'skills' / 'causa-raiz' / 'SKILL.md'
        before = alias.read_bytes()
        wrapper = Path(self.codes) / 'id' / 'skills' / 'causa-raiz' / 'SKILL.md'
        write(str(wrapper), 'private wrapper\n')
        self.assertNotEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        self.assertEqual(alias.read_bytes(), before)
        self.assertEqual(wrapper.read_text(encoding='utf-8'), 'private wrapper\n')

    def test_export_refuses_edited_generated_skill(self):
        self.setup_persona()
        import layers
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        self.assertEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        alias = home / 'skills' / 'causa-raiz' / 'SKILL.md'
        alias.write_text('edit\n', encoding='utf-8')
        with self.assertRaises(SystemExit):
            layers.export(layers.load_manifest(self.manifest), str(home), 'id')

    def test_default_canonical_includes_private_policy_pointer(self):
        self.setup_persona()
        wrapper = Path(self.codes) / 'id' / 'skills' / 'causa-raiz' / 'SKILL.md'
        write(str(wrapper), 'private policy\n')
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        write(str(home / 'skills' / 'causa-raiz' / 'SKILL.md'), 'private policy\n')
        self.assertEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        body = (home / 'skills' / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('causa-raiz', body)
        self.assertIn('policy', body.lower())

    def test_migrate_does_not_move_legacy_alias_to_canonical(self):
        self.setup_persona()
        import migrate
        man = json.loads(Path(self.manifest).read_text(encoding='utf-8'))
        home = Path(self.tmp) / 'home'
        write(str(home / 'skills' / 'causa-raiz' / 'SKILL.md'), 'old\n')
        changes = migrate.plan(man, home, migrate.load_map())
        self.assertFalse(any(ch['kind'] == 'skill' and ch['old'] == 'causa-raiz' for ch in changes))

    def test_exact_persona_copy_is_adopted_but_different_copy_is_not(self):
        self.setup_persona()
        import shutil
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        src = Path(self.codes) / 'persona' / 'skills' / 'root-cause'
        dst = home / 'skills' / 'root-cause'
        dst.parent.mkdir(parents=True)
        shutil.copytree(src, dst)
        self.assertEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        self.assertIn('root-cause', json.loads((home / 'skills' / '.persona-skills.json').read_text(encoding='utf-8'))['skills'])

    def test_migration_preserves_active_rule_files_and_imports(self):
        self.setup_persona()
        import migrate
        home = Path(self.tmp) / 'home'
        write(str(home / 'regras-de-agente.md'), 'active rule\n')
        write(str(home / 'rules' / 'agentes-e-sessoes.md'), 'active practice\n')
        write(str(home / 'CLAUDE.md'), '@~/.claude/regras-de-agente.md\n')
        migrate.apply(Path(self.manifest), home, migrate.load_map(), False, True)
        self.assertTrue((home / 'regras-de-agente.md').exists())
        self.assertTrue((home / 'rules' / 'agentes-e-sessoes.md').exists())
        self.assertIn('regras-de-agente.md', (home / 'CLAUDE.md').read_text(encoding='utf-8'))

    def test_reviewed_migration_hashguards_and_backs_up_before_removal(self):
        self.setup_persona()
        import compose, subprocess
        home = Path(self.tmp) / 'claude'
        skill = home / 'skills' / 'root-cause'
        write(str(skill / 'SKILL.md'), 'owned by user\n')
        original = (skill / 'SKILL.md').read_bytes()
        plan = Path(self.tmp) / 'transition.json'
        plan.write_text(json.dumps({'skills': {'root-cause': compose.tree_hash(str(skill))}}), encoding='utf-8')
        backup = Path(self.tmp) / 'backup'
        script = Path(__file__).resolve().parent.parent / 'tools' / 'persona_migration.py'
        cmd = [sys.executable, '-I', str(script), '--plan', str(plan), '--skills', str(home / 'skills'), '--backup', str(backup)]
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.assertTrue(skill.exists())
        (skill / 'SKILL.md').write_text('edited\n', encoding='utf-8')
        self.assertNotEqual(subprocess.run(cmd + ['--apply'], capture_output=True).returncode, 0)
        self.assertEqual((skill / 'SKILL.md').read_text(encoding='utf-8'), 'edited\n')
        (skill / 'SKILL.md').write_bytes(original)
        self.assertEqual(subprocess.run(cmd + ['--apply'], capture_output=True).returncode, 0)
        self.assertFalse(skill.exists())
        self.assertEqual((backup / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8'), 'owned by user\n')

    def test_refresh_picks_up_changed_readonly_source(self):
        self.setup_persona()
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        args = ('--claude-home', str(home), '--codex-home', str(codex), '--skills-only')
        self.assertEqual(self.cli(*args).returncode, 0)
        src = Path(self.codes) / 'persona' / 'skills' / 'root-cause' / 'SKILL.md'
        src.write_text(src.read_text(encoding='utf-8').replace('Canonical procedure.', 'Updated procedure.'), encoding='utf-8')
        self.assertEqual(self.cli(*args).returncode, 0)
        self.assertIn('Updated procedure.', (home / 'skills' / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8'))

    def test_orphan_home_alias_fails_without_losing_private_reference(self):
        self.setup_persona()
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        reference = home / 'skills' / 'causa-raiz' / 'references' / 'local.md'
        write(str(reference), 'private reference\n')
        result = self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(reference.read_text(encoding='utf-8'), 'private reference\n')
        self.assertFalse((home / 'skills' / 'root-cause').exists())

    def test_raw_restore_then_compose_adopts_exact_persona(self):
        self.setup_persona()
        import subprocess
        bash = r'C:\Program Files\Git\bin\bash.exe' if os.name == 'nt' else '/bin/bash'
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        script = Path(__file__).resolve().parent.parent / 'restore.sh'
        result = subprocess.run([bash, str(script).replace('\\', '/'), '--from', str(Path(self.codes) / 'persona').replace('\\', '/'), '--claude-home', str(home).replace('\\', '/')], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli('--claude-home', str(home), '--codex-home', str(codex))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((home / 'skills' / 'causa-raiz' / 'SKILL.md').is_file())
        self.assertTrue((codex / 'skills' / 'root-cause' / 'SKILL.md').is_file())

    def test_default_canonical_policy_requires_local_wrapper(self):
        self.setup_persona()
        wrapper = Path(self.codes) / 'id' / 'skills' / 'causa-raiz' / 'SKILL.md'
        write(str(wrapper), 'private policy\n')
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        result = self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((home / 'skills' / 'root-cause').exists())

    def test_adoption_rejects_extra_empty_directory(self):
        self.setup_persona()
        import shutil
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        src = Path(self.codes) / 'persona' / 'skills' / 'root-cause'
        dst = home / 'skills' / 'root-cause'
        dst.parent.mkdir(parents=True)
        shutil.copytree(src, dst)
        (dst / 'private-empty').mkdir()
        self.assertNotEqual(self.cli('--claude-home', str(home), '--codex-home', str(codex), '--skills-only').returncode, 0)
        self.assertTrue((dst / 'private-empty').is_dir())

    def test_alias_description_retains_english_boundaries(self):
        self.setup_persona()
        out = Path(self.tmp) / 'out'
        self.assertEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        alias = (out / 'skills' / 'causa-raiz' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('Diagnose.', alias)
        self.assertIn('Diagnostica causas.', alias)

    def test_same_name_overlay_does_not_hide_wrapper_policy(self):
        self.setup_persona()
        p = Path(self.codes) / 'id' / 'locales' / 'pt-BR' / 'skills.json'
        p.write_text(json.dumps({'aliases': {'root-cause': {'target': 'root-cause', 'description': 'Diagnostica.'}, 'causa-raiz': {'target': 'root-cause', 'description': 'Causas.'}}}), encoding='utf-8')
        write(str(Path(self.codes) / 'ego-alpha' / 'skills' / 'causa-raiz' / 'SKILL.md'), 'private policy\n')
        out = Path(self.tmp) / 'out'
        self.assertEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        content = (out / 'skills' / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('Diagnostica.', content)
        self.assertIn('causa-raiz', content)

    def test_company_generated_alias_edit_aborts_before_recomposition(self):
        self.setup_persona()
        out = Path(self.tmp) / 'out'
        self.assertEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        alias = out / 'skills' / 'causa-raiz' / 'SKILL.md'
        alias.write_text('edited policy\n', encoding='utf-8')
        self.assertNotEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        self.assertEqual(alias.read_text(encoding='utf-8'), 'edited policy\n')

    def test_export_company_home_rejects_edited_generated_alias(self):
        self.setup_persona()
        import layers
        out = Path(self.tmp) / 'out'
        self.assertEqual(self.cli('--company', 'alpha', '--out', str(out)).returncode, 0)
        (out / 'skills' / 'causa-raiz' / 'SKILL.md').write_text('edit\n', encoding='utf-8')
        with self.assertRaises(SystemExit):
            layers.export(layers.load_manifest(self.manifest), str(out), 'id')

    def test_all_private_policy_bindings_apply_only_to_selected_company(self):
        self.setup_persona()
        write(str(Path(self.codes) / 'id' / 'skills' / 'causa-raiz' / 'SKILL.md'), 'personal policy\n')
        write(str(Path(self.codes) / 'ego-alpha' / 'skills' / 'alpha-policy' / 'SKILL.md'), 'alpha policy\n')
        cfg = Path(self.codes) / 'ego-alpha' / 'layer.json'
        data = json.loads(cfg.read_text(encoding='utf-8'))
        data['skill_policies'] = {'root-cause': ['alpha-policy']}
        cfg.write_text(json.dumps(data), encoding='utf-8')
        for company in ('alpha', 'beta'):
            out = Path(self.tmp) / company
            result = self.cli('--company', company, '--out', str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            canonical = (out / 'skills' / 'root-cause' / 'SKILL.md').read_text(encoding='utf-8')
            self.assertIn('causa-raiz', canonical)
            self.assertEqual('alpha-policy' in canonical, company == 'alpha')
            self.assertEqual((out / 'skills' / 'alpha-policy' / 'SKILL.md').is_file(), company == 'alpha')

    def test_unknown_explicit_policy_binding_refuses_writes(self):
        self.setup_persona()
        cfg = Path(self.codes) / 'ego-alpha' / 'layer.json'
        data = json.loads(cfg.read_text(encoding='utf-8'))
        data['skill_policies'] = {'root-cause': ['missing-wrapper']}
        cfg.write_text(json.dumps(data), encoding='utf-8')
        out = Path(self.tmp) / 'out'
        result = self.cli('--company', 'alpha', '--out', str(out))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(out.exists())

    def test_generated_python_bytecode_does_not_block_but_source_edit_does(self):
        self.setup_persona()
        import layers, subprocess
        source = Path(self.codes) / 'persona' / 'skills' / 'root-cause' / 'scripts'
        write(str(source / 'helper.py'), 'VALUE = 42\n')
        write(str(source / 'runner.py'), 'import helper\nprint(helper.VALUE)\n')
        self.assertEqual(subprocess.run([sys.executable, str(source / 'runner.py')], capture_output=True).returncode, 0)
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        args = ('--claude-home', str(home), '--codex-home', str(codex), '--skills-only')
        self.assertEqual(self.cli(*args).returncode, 0)
        script = home / 'skills' / 'root-cause' / 'scripts' / 'runner.py'
        self.assertFalse(any((script.parent / '__pycache__').glob('*.pyc')))
        self.assertEqual(subprocess.run([sys.executable, str(script)], capture_output=True).returncode, 0)
        self.assertTrue(any((script.parent / '__pycache__').glob('*.pyc')))
        layers.export(layers.load_manifest(self.manifest), str(home), 'ego')
        self.assertEqual(self.cli(*args).returncode, 0)
        note = script.parent / '__pycache__' / 'notes.txt'
        write(str(note), 'user content\n')
        self.assertNotEqual(self.cli(*args).returncode, 0)
        note.unlink()
        (script.parent / 'helper.py').write_text('VALUE = 99\n', encoding='utf-8')
        self.assertNotEqual(self.cli(*args).returncode, 0)

    def test_symlink_disguised_as_bytecode_still_fails_closed(self):
        self.setup_persona()
        home, codex = Path(self.tmp) / 'claude', Path(self.tmp) / 'codex'
        codex.mkdir()
        args = ('--claude-home', str(home), '--codex-home', str(codex), '--skills-only')
        self.assertEqual(self.cli(*args).returncode, 0)
        folder = home / 'skills' / 'root-cause' / '__pycache__'
        folder.mkdir()
        link = folder / 'fake.pyc'
        try:
            link.symlink_to(home / 'skills' / 'root-cause' / 'SKILL.md')
        except OSError:
            self.skipTest('symlink creation unavailable')
        self.assertNotEqual(self.cli(*args).returncode, 0)

    def test_shared_layer_gate_accepts_private_routing_schema_and_rejects_invalid(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'ci'))
        import repo_gates
        root = Path(self.tmp) / 'schema'
        root.mkdir()
        cfg = {'level': 'id', 'skill_aliases': 'locales/pt-BR/skills.json',
               'skill_policies': {'context-recall': ['context-recall-local']}}
        write(str(root / 'locales' / 'pt-BR' / 'skills.json'), '{\"aliases\": {}}')
        write(str(root / 'skills' / 'context-recall-local' / 'SKILL.md'), 'wrapper')
        write(str(root / 'layer.json'), json.dumps(cfg))
        findings = list(repo_gates.check_layer(None, root, '', 'id', False))
        self.assertEqual(findings, [])
        cfg['skill_aliases'] = '../outside.json'
        cfg['skill_policies'] = {'context-recall': '../outside'}
        write(str(root / 'layer.json'), json.dumps(cfg))
        findings = list(repo_gates.check_layer(None, root, '', 'id', False))
        self.assertGreaterEqual(len(findings), 2)

    def test_context_map_recognizes_public_ownership_and_keeps_authorization(self):
        root = Path(__file__).resolve().parent.parent
        path = root / 'superego' / 'rules' / 'context-map.md'
        body = path.read_text(encoding='utf-8')
        self.assertLessEqual(len(path.read_bytes()), 1450)
        self.assertIn('readonly repo', body)
        self.assertIn('`level:` is not required', body)
        self.assertIn("only with the user's yes", body)
        self.assertIn('manifest default', body)
