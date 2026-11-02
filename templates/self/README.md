# psique of {{name}}

Meta repo of {{name}}'s agent context (`{{github}}`), created on {{date}} by `tools/onboard.py init` of
superego. It holds no context of its own: `manifest.json` lists the layers in the order they load.

| Level | What it is | Who changes it |
|---|---|---|
| superego | general rules and tools (shared repo, version pinned in `ref`) | only the superego owner |
| collective | what the team shares (read-only here) | PR, with `onboard.py contribute` |
| ego | the company or project (read-only here) | PR, with `onboard.py contribute` |
| id | you: preferences, development plan, personal memories (private) | you, directly |

Memories and skills without `level:` in the frontmatter go to `id` (`default_level`), never to a shared layer.

## Commands

    python -I <your-folder>/superego/tools/onboard.py update --push    # the hourly job does this
    python -I <your-folder>/superego/tools/onboard.py update --upgrade # bumps the pinned superego version
    python -I <your-folder>/superego/tools/onboard.py doctor
    python -I <your-folder>/superego/tools/onboard.py uninstall

This repo is private and lives in your account. Put nothing from another company or person in it.
