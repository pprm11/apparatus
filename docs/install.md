# How to install the agent context (Claude Code and Codex)

For anyone joining a project that already uses this layered context and who does not own apparatus. When it
finishes you have the project's collective (the only shared layer, read-only), your own `ego` (your private
application of the collective) and your private `id` in your GitHub account, a ready `~/.claude/CLAUDE.md` and
`~/.codex/AGENTS.md`, and a job that updates everything every hour. Nothing from the owner or from other
companies is installed: the installer checks this before and after (`ci/privacy-terms.json`).

`<owner>` below is the GitHub account that invited you. The ready-made commands, with the right names, come in the
invitation message.

## Before you start

1. Accept the GitHub invitations you received by e-mail (apparatus and the project's collective). Without the acceptance the clone fails.
2. Have your own GitHub account. The installer creates **private** repositories in it: `self`, `id` and an `ego-NAME` for each collective (your notes, preferences and work context for that company). The ego is always yours: the installer refuses another person's ego.

## Step by step

1. **Install git and gh and log in to GitHub.**

   Windows (PowerShell):

       winget install --id Git.Git -e
       winget install --id GitHub.cli -e
       gh auth login

   macOS:

       brew install git gh
       gh auth login

   Linux (Debian, Ubuntu):

       sudo apt-get install -y git
       # gh: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
       gh auth login

   In `gh auth login` choose GitHub.com, HTTPS and the browser. Open a new terminal after installing.

2. **Download apparatus** (the shared, read-only part). `<your-folder>` is the folder that will hold all the layer
   repos; pick any folder inside your home. Later steps use the same folder through `--codes <your-folder>` or the
   `PSIQUE_ROOT` environment variable (without either, the installer uses the folder that holds this checkout):

       gh repo clone <owner>/apparatus <your-folder>/apparatus


   This clone works with an invitation to apparatus, or without one from the public mirror
   `<owner>/apparatus` (one commit per publish, no private history; see [Public mirror](public-mirror.md)).
   Only the collective still needs an invitation.

   The program stays at the checkout root. The layer lives in `<your-folder>/apparatus/superego/`.
   Its manifest path is `<apparatus>/superego`, where `<apparatus>` is the checkout.
   Old manifests pointing at the checkout root still work. The loader finds the nested folder.

3. **Run the installer** (it finds Python 3.10 or newer and installs it if missing).

   Windows:

       & "<your-folder>\apparatus\install.ps1" init --codes <your-folder> --layer collective:NAME=https://github.com/<owner>/collective-NAME --root NAME=<your-folder>/NAME

   macOS and Linux:

       <your-folder>/apparatus/install.sh init --codes <your-folder> --layer collective:NAME=https://github.com/<owner>/collective-NAME --root NAME=<your-folder>/NAME

4. **Answer what it asks** (or pass `--name` and `--github` to skip the questions):

   | Question | What to answer |
   |---|---|
   | Your name | how you want to be called in the files of your `id` |
   | Your GitHub username | yours, not the owner's |

   **Collective step:** without `--layer collective:...` it lists the collectives (`collective-*`) you can access and
   asks which to attach, in which project folders each one applies (only there, never mixed with another company),
   or whether you want to skip (`--no-collective`) or create a new one, private in your account, with the CI and
   the list of other companies' terms (`--new-collective NAME --deny-company TERM`). With two or more companies, the
   default home loads none of them and each one gets its own in `~/.agent-homes/NAME`.

   `--layer collective:NAME=URL` attaches a collective (name and URL); your `ego-NAME` is created with it. `--root`
   says which folder holds that company's projects. The installer clones the layers, creates your `self`, your
   `id` and your `ego-NAME` from the templates, copies everything to `~/.claude`, generates `CLAUDE.md` and
   `AGENTS.md`, schedules the job and runs the `doctor`.

5. **Vault (optional, asked at the end of init).** This is your own Bitwarden, your age key and the encrypted
   backup of your secrets in your `id`. You do these steps yourself: create the account at bitwarden.com (or
   vault.bitwarden.eu, use `--bw-region eu`), set a long master password, turn on two-step verification and save the
   recovery code. The installer installs `bw` and `age`, asks for `bw login` and the master password in your
   terminal, generates the age key, stores it as the note `age-identity` in YOUR vault, checks it by hash without
   printing it and saves only the public key. The private key never goes to disk or to the screen. Success is the
   line `vault: age key created and verified in the vault`. To do it later: `onboard.py vault`.

6. **Check.** The end of the output should say `0 failed`. Then open the agents once: `claude` (and `codex login`
   if you use Codex). To run the checker whenever you like:

       python -I <your-folder>/apparatus/tools/onboard.py doctor

At the end of init it registers the jobs in your system, runs a sync and shows the result. The jobs are `update`
(hourly) and `secrets` (only with the vault). The owner's `harvest` and `weekly` are bash scripts that write inside
the apparatus checkout, which is read-only for you, so they do not exist in your installation. Manage them with
`onboard.py jobs status|enable NAME|disable NAME|run NAME`. The `doctor` shows, per job, whether it is registered,
the last result and the next run.

Running step 3 again is safe: it only completes what is missing. If you already had your own `~/.claude/CLAUDE.md`
or `~/.codex/AGENTS.md`, the copy stays next to it as `*.pre-self` and comes back on uninstall.

## Day to day

- **Update** (the job does it hourly): `python -I <your-folder>/apparatus/tools/onboard.py update --push`. It pulls
  the shared layers, recomposes the files and backs up your `id` and your `ego` layers.
- **New superego version** (it is pinned to a version): `python -I <your-folder>/apparatus/tools/onboard.py update --upgrade`.
- **Your own memories and skills** go to your private `id` (those without `level:` in the header too). To make one
  valid for the team, propose it through the PR flow below.
- **Propose a change to a shared layer** (the shared layers are read-only for you):

      python -I <your-folder>/apparatus/tools/onboard.py contribute start collective my-term
      # edit the files in the folder it prints (drafts in proposed/), then:
      python -I <your-folder>/apparatus/tools/onboard.py contribute submit <FOLDER> -m "feat: add term X"

  With write permission it pushes the branch and opens the PR; without it, it tries through a fork (a private
  repository of a personal account may not allow that: in this case ask the owner for write access). The
  repository's CI blocks names of other companies.

## If something goes wrong

| Symptom | Cause | What to do |
|---|---|---|
| `no access to <owner>/...` | invitation not accepted or not sent yet | accept the GitHub e-mail or ask for the invitation; run step 3 again |
| `gh is not logged in` | `gh auth login` is missing | run it and repeat step 3 |
| `missing: git` or `missing: gh` | tool not installed or old terminal | step 1 and open a new terminal |
| `LEAKED ... source` | a shared layer carries a name that is not yours | nothing was installed; send the line to the layer owner |
| `jobs: not registered` (warning) | your system's scheduler refused | run `python -I <your-folder>/apparatus/tools/scheduler.py install --manifest <your-folder>/self/manifest.json --apply` |
| `claude` or `codex` warning | not installed | optional: `npm install -g @anthropic-ai/claude-code` or `@openai/codex` |
| macOS without Python | Homebrew missing | install Homebrew (brew.sh) and run again |

## Uninstall

    python -I <your-folder>/apparatus/tools/onboard.py uninstall --dry-run   # only shows
    python -I <your-folder>/apparatus/tools/onboard.py uninstall

It removes the jobs, the files copied to `~/.claude`, the generated `AGENTS.md`, the Codex skill links, the local
clones of the layers, the per-company homes, the installer's state and logs and the folders it created; it gives
back your `*.pre-self` files. It prints each removed item. Running it again does nothing. A clone of yours
(`self`, `id`) with work that exists only locally is kept and flagged. It never deletes anything remote
(GitHub, Bitwarden). The local age key is removed only with `--remove-age-key` and your confirmation. Deleting your
repositories on GitHub requires `--delete-remote-repos`, `--confirm-remote-delete <github-user>` and typing
`DELETE` (without a terminal: `--i-am-sure`). The credential helper that `gh auth setup-git` put in the global git
config stays, because it belongs to `gh`.

## I already have an account: bring everything to a new machine

    python -I <your-folder>/apparatus/tools/onboard.py restore --github <github-user> --codes <your-folder>

It clones your `self` and every layer it lists, opens your vault, fetches the `age-identity` note, decrypts
`sealed/` and the secrets backup without overwriting existing files, restores, composes, registers the jobs and
runs the `doctor`. Use it after steps 1 and 2 above (git, gh, apparatus). With the vault locked it carries on
without the secrets and tells you what was left out.

## For whoever invites

Before sending the command, in the owner account (replace `<github-user>`):

    gh api -X PUT repos/<owner>/apparatus/collaborators/<github-user> -f permission=pull
    gh api -X PUT repos/<owner>/collective-NAME/collaborators/<github-user> -f permission=pull

Use `permission=push` on the collective where the person contributes by PR. Only apparatus and the collective are
shared: never invite anyone to the `id`, the `self` or anyone's ego (the ego is each person's private
application). On a personal account GitHub does not enforce "PR only" (no branch protection on a private
repository): anyone with write access can push directly; the CI runs and `gitleaks` scans the history, but they do
not block.

Existing installs may still have psique/id-context/superego folders: they keep working, and tools/migrate.py renames them.
