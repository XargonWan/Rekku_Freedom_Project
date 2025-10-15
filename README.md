> [!NOTE]
> This project was made more generic and itś been renamed **SyntH - Synthetic Heart** allowing any user to easly create their own persona, this branch is outdated and with the old naming, please check the `develop` branch.
> The main branch will be updated soon enough to reflect the new changes as soon as `develop` branch stability will be satisfying.
> Contributons are welcome.

<img src="docs/res/RFP_logo.png" alt="RFP Logo" width="300"/>

![Docker Pulls](https://img.shields.io/docker/pulls/xargonwan/rekku_freedom_project)
| Branch    | Build Status                                                                                                                                         | Docs Status                                                                                                                                      |
|-----------|------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `main`    | [![CI Status](https://img.shields.io/github/actions/workflow/status/XargonWan/Rekku_Freedom_Project/build-release.yml)](https://github.com/XargonWan/Rekku_Freedom_Project/actions)      | [![Docs Status](https://readthedocs.org/projects/rekku-freedom-project/badge/?version=latest)](https://rekku-freedom-project.readthedocs.io/en/latest/?badge=latest) |
| `develop` | [![Develop CI Status](https://img.shields.io/github/actions/workflow/status/XargonWan/Rekku_Freedom_Project/build-release.yml?branch=develop)](https://github.com/XargonWan/Rekku_Freedom_Project/actions) | [![Docs Status](https://readthedocs.org/projects/rekku-freedom-project/badge/?version=latest)](https://rekku-freedom-project.readthedocs.io/en/latest/?badge=latest) |

**Rekku Freedom Project** provides a modular stack for creating autonomous AI personas. Interfaces, language models and action plugins can be swapped at runtime.

Built around a lightweight plugin system, RFP lets you combine different chat interfaces and LLM engines to craft persistent characters.  The project currently focuses on one persona, **Rekku**, but the architecture is designed to support multiple synthetic beings in the future.

### Features

- Switchable LLM engines (manual trainer, ChatGPT API or a Selenium-driven ChatGPT session)
- Multiple chat interfaces including Telegram and Discord
- Action plugins such as a persistent terminal and scheduled events
- Optional context memory injection with `/context`
- Docker deployment with automatic database backups

## Quickstart

1. Copy `.env.example` to `.env` and fill the required values.
2. Start the stack:
   ```bash
   docker compose up
   ```
3. If using the Selenium engine, open `http://<host>:5006` and log into ChatGPT.

See the [documentation](https://rekku-freedom-project.readthedocs.io) for installation details, advanced features and contribution guidelines.

## Docker image repository
You can browse and manage Docker images for this project on [Docker Hub](https://hub.docker.com/repository/docker/xargonwan/rekku_freedom_project).

## Contributing

Pull requests are welcome! Please read the guidelines in the documentation before submitting.
