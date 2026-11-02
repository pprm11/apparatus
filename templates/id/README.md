# id-<name> (template)

Skeleton of the personal layer ("id") of the agent context: preferences, personal development plan (PDI),
career notes and anything about the user as a person rather than about a company. It is private, stays with
the user when they change company, and sensitive paths are stored encrypted.

Start one:

1. Copy this folder to a new private repo, for example `<your-folder>/id`, and run `git init`.
2. Replace the example in `global/padroes-do-usuario.md` with the real preferences, and rename
   `memory/project-key/` to the key of a real project (the project path with `:`, `\` and `/` replaced
   by `-`).
3. Add the repo to the meta repo's `manifest.json`, last in the list:
   `{"level": "id", "name": "id", "path": "<your-folder>/id", "repo": "git@github.com:<user>/id.git", "active": true}`.
4. Generate an age key pair, keep the private key in a password manager and put the public key where the
   sync expects it (see `sealed/README.md`).

## How the layer is found and filled

- `manifest.json` (meta repo) lists the active layers in load order, each with `level`, local `path` and
  `repo`. `tools/layers.py` and `tools/compose.py` read it.
- `level: id` in the frontmatter of a memory or of a skill's `SKILL.md` sends that file to this layer.
  Files without `level:` go to the manifest's `default_level`.
- `layer.json` says what this layer owns outside memories and skills: `globals` (root files of `~/.claude`,
  copied to `global/`), `rules`, `dirs` (mirrored folders, here `pdi`), `files` and `sealed` (paths kept
  encrypted).
- `tools/layers.py export` writes these files into the repo, and `tools/compose.py` builds
  `~/.claude/CLAUDE.md` from the layers' `global/` files in manifest order (superego, ego, id).
