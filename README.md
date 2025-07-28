<div align="center">
    <picture>
        <source srcset="assets/logo/dark-mode/acubed.png"  media="(prefers-color-scheme: dark)">
        <img src="assets/logo/no-dark-mode/acubed.png" alt="Logo" width="200px" height=auto>
    </picture>
</div>

[![Release](https://img.shields.io/github/v/release/stepmanai/ACubed)](https://img.shields.io/github/v/release/stepmanai/ACubed)
[![Build status](https://img.shields.io/github/actions/workflow/status/stepmanai/ACubed/main.yml?branch=main)](https://github.com/stepmanai/ACubed/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/stepmanai/ACubed/branch/main/graph/badge.svg)](https://codecov.io/gh/stepmanai/ACubed)
[![Commit activity](https://img.shields.io/github/commit-activity/m/stepmanai/ACubed)](https://img.shields.io/github/commit-activity/m/stepmanai/ACubed)
[![License](https://img.shields.io/github/license/stepmanai/ACubed)](https://img.shields.io/github/license/stepmanai/ACubed)

**ACubed** is a model training framework designed to bring data-driven stepfile difficulty prediction to open source rhythm games. Inspired by the spirit of [rCubed](https://github.com/flashflashrevolution/rCubed), a transformative upgrade to the Flash Flash Revolution (FFR) game engine, ACubed aims to modernize and enhance the ranking system through machine learning–based chart analysis.

At its core, ACubed provides tools to train, evaluate, and apply predictive models that estimate the difficulty of rhythm game charts based on note data, pattern structure, timing, and gameplay dynamics. By abstracting the stepfile format and separating model logic from game-specific implementations, ACubed is designed to be interoperable across rhythm games, enabling the creation of shared and consistent difficulty metrics across different rhythm games. This helps support transparent ranking systems, facilitates automated chart quality control, and enriches metadata for both players and developers.

Whether you're enhancing a legacy engine or building the next generation of rhythm games, ACubed provides a modular and extensible foundation for intelligent difficulty estimation and cross-platform standardization.

## Relevant Links

- **Github repository**: <https://github.com/stepmanai/ACubed/>
- **Documentation** <https://stepmanai.github.io/ACubed/>

- **Datasets**: <https://huggingface.co/datasets/stepmanai/ffr_charts>

## Prerequisites:

Based on [Copier's installation requirements](https://github.com/copier-org/copier?tab=readme-ov-file#installation), this project is natively supported on `Ubuntu 22.04` (`ubuntu:jammy`) and later versions.

For Windows users, you can download `Ubuntu 22.04` from the Microsoft Store after setting up Windows Subsystem for Linux (WSL). Instructions provided [here](https://learn.microsoft.com/en-us/windows/wsl/install).

## Getting Started with Your Project

### 1. Setup SSH Keys and Access Token in GitHub and Hugging Face

<details>
‎<summary><h6>‎ ‎ ‎ ‎ Click to expand steps</h6></summary>

#### a) Generate a new SSH key (if you don't have one)

```console
foo@bar:~$ ssh-keygen -t ed25519 -C "your_email@example.com"
Your identification has been saved in /home/foo/.ssh/id_ed25519
Your public key has been saved in /home/foo/.ssh/id_ed25519.pub
The key fingerprint is:
SHA256:AbCdEfGhIjKlMnOpQrStUvWxYz1234567890abcdEFG your_email@example.com
The key's randomart image is:
+--[ED25519 256]--+
|     ..++o.      |
|    ..oo+oo      |
|    o.oo+o       |
|   o ..+o        |
|  . +.S          |
|   o =           |
|    E .          |
|                 |
|                 |
+----[SHA256]-----+
```

#### b) Start the SSH agent and add the key.

```console
foo@bar:~$ eval "$(ssh-agent -s)"
Agent pid 111
foo@bar:~$ ssh-add ~/.ssh/id_ed25519
Identity added: /home/foo/.ssh/id_ed25519 (your_email@example.com)
```

#### c) Copy the public key to clipboard.

```console
foo@bar:~$ cat ~/.ssh/id_ed25519.pub
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeDummyKeyForTestingPurposesOnly1234567890 your_email@example.com
```

#### d) Add public key to [GitHub](https://github.com/settings/keys) and [Hugging Face](https://huggingface.co/settings/keys).

#### e) Verify SSH setup:

```console
foo@bar:~$ ssh -T git@github.com
Hi foo! You've successfully authenticated, but GitHub does not provide shell access.
foo@bar:~$ ssh -T git@hf.co
Hi foo, welcome to Hugging Face.
```

#### f) [Create User Access Token](https://huggingface.co/settings/tokens) in Hugging Face.

</details>

### 2. Setup Secrets to Access Rhythm Game Data

<details>
<summary><h6>‎ ‎ ‎ ‎ Flash Flash Revolution (FFR)</h6></summary>

#### a) Request API Key to access [FFR's API](https://www.flashflashrevolution.com/api/).

Make sure to log in [Flash Flash Revolution](https://www.flashflashrevolution.com/) before requesting for a User API Key.

<img width="1778" height="488" alt="image" src="https://github.com/user-attachments/assets/4c6a6537-4e81-4117-9101-3ccb57804a34" />

</details>

### 3. Clone the Repository to Your Local Environment via SSH

```console
foo@bar:~$ git clone git@github.com:stepmanai/ACubed.git
Cloning into 'ACubed'...
remote: Enumerating objects: 214, done.
remote: Counting objects: 100% (214/214), done.
remote: Compressing objects: 100% (146/146), done.
remote: Total 214 (delta 62), reused 169 (delta 28), pack-reused 0 (from 0)
Receiving objects: 100% (214/214), 323.97 KiB | 1.40 MiB/s, done.
Resolving deltas: 100% (62/62), done.
```

### 4. Install Required Local Dependencies in `ACubed` directory

<details>
‎<summary><h6>‎ ‎ ‎ ‎ Click to expand steps</h6></summary>

#### a) Install necessary Ubuntu packages via `apt` package manager.

- `make`: Tool for building and compiling software using Makefiles.
- `python3-pip`: Installs and manages Python 3 packages from the Python Package Index (PyPI).
- `jq`: Command-line utility for parsing, filtering, and manipulating JSON data.
- `git-lfs`: Git extension for versioning large files efficiently.

```console
foo@bar:~/ACubed$ sudo apt update
...
Fetched 39.3 MB in 17s (2282 kB/s)
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
110 packages can be upgraded. Run 'apt list --upgradable' to see them.
foo@bar:~/ACubed$ sudo apt install -y make python3-pip jq git-lfs
...
```

#### b) Install `uv`.

- `uv`: A fast Python package manager and build tool designed as a drop-in replacement for pip, pip-tools, and virtualenv.

```console
foo@bar:~/ACubed$ wget -qO- https://astral.sh/uv/install.sh | sh
downloading uv 0.8.3 x86_64-unknown-linux-gnu
no checksums to verify
installing to /home/foo/.local/bin
  uv
  uvx
everything's installed!
foo@bar:~/ACubed$ source $HOME/.local/bin/env
```

#### c) Initialize `git lfs`.

```console
foo@bar:~/ACubed$ curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | sudo bash
...
The repository is setup! You can now install packages.
foo@bar:~/ACubed$ git lfs install
Updated git hooks.
Git LFS initialized.
```

</details>

### 5. Set Up Your Development Environment

<details>
‎<summary><h6>‎ ‎ ‎ ‎ Click to expand steps</h6></summary>

#### a) Run `make` command to create virual environment.
    
```console
foo@bar:~/ACubed$ make install
🚀 Creating virtual environment using uv
Using CPython 3.10.12 interpreter at: /usr/bin/python3
Creating virtual environment at: .venv
...
```

#### b) Test pre-commit hooks

Verify that the checks in the pre-commit hooks does not fail by running the following command:

```console
foo@bar:~/ACubed$ uv run pre-commit run -a
Sync Git submodules......................................................Passed
check for case conflicts.................................................Passed
check for merge conflicts................................................Passed
check toml...............................................................Passed
check yaml...............................................................Passed
fix end of files.........................................................Passed
trim trailing whitespace.................................................Passed
ruff.....................................................................Passed
ruff-format..............................................................Passed
prettier.................................................................Passed
```

#### c) Initialize Visual Studio Code

Run the following command to open up a code editor:

```console
foo@bar:~/ACubed$ code .
...
```

#### d) Create `.env` file in Visual Studio Code using `.env.example`.

</details>

You are now ready to start development on your project!

Each time when code changes are made in the repository, run the pre-commit hooks to make sure that the build passes before opening a pull request, merging to main, or creating a new release. The project is designed so that the CI/CD pipeline will run these above code quality checks to enforce standardization.

To finalize the set-up for publishing to PyPI, see [here](https://fpgmaas.github.io/cookiecutter-uv/features/publishing/#set-up-for-pypi).
For activating the automatic documentation with MkDocs, see [here](https://fpgmaas.github.io/cookiecutter-uv/features/mkdocs/#enabling-the-documentation-on-github).
To enable the code coverage reports, see [here](https://fpgmaas.github.io/cookiecutter-uv/features/codecov/).

## Releasing a new version

- Create an API Token on [PyPI](https://pypi.org/).
- Add the API Token to your projects secrets with the name `PYPI_TOKEN` by visiting [this page](https://github.com/stepmanai/ACubed/settings/secrets/actions/new).
- Create a [new release](https://github.com/stepmanai/ACubed/releases/new) on Github.
- Create a new tag in the form `*.*.*`.

For more details, see [here](https://fpgmaas.github.io/cookiecutter-uv/features/cicd/#how-to-trigger-a-release).

---

Repository created by [stepmanai/project-bass](https://github.com/stepmanai/project-bass).

Repository structure based on [fpgmaas/cookiecutter-uv](https://github.com/fpgmaas/cookiecutter-uv).
