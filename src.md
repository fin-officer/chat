protocol-integration/
├── Dockerfile
├── pyproject.toml
├── README.md
├── ansible/
│   ├── inventories/
│   │   ├── development/
│   │   │   ├── hosts.yml
│   │   │   └── group_vars/
│   │   │       └── all.yml
│   │   └── production/
│   │       ├── hosts.yml
│   │       └── group_vars/
│   │           └── all.yml
│   ├── playbooks/
│   │   ├── deploy.yml
│   │   ├── test-shell.yml
│   │   ├── test-mcp.yml
│   │   └── test-rest.yml
│   └── roles/
│       ├── common/
│       ├── protocol-deploy/
│       └── protocol-test/
├── tests/
│   ├── __init__.py
│   ├── test_base_protocol.py
│   ├── test_shell.py
│   ├── test_rest_api.py
│   └── test_mcp.py
└── protocol_integration/
    ├── __init__.py
    ├── core/
    │   ├── __init__.py
    │   ├── protocol.py
    │   ├── message.py
    │   └── routing.py
    ├── protocols/
    │   ├── __init__.py
    │   ├── chat.py
    │   ├── email.py
    │   ├── discord.py
    │   └── slack.py
    ├── interfaces/
    │   ├── __init__.py
    │   ├── shell/
    │   │   ├── __init__.py
    │   │   ├── cli.py
    │   │   └── interactive.py
    │   ├── rest/
    │   │   ├── __init__.py
    │   │   ├── app.py
    │   │   ├── routes.py
    │   │   └── schemas.py
    │   └── mcp/
    │       ├── __init__.py
    │       ├── adapter.py
    │       └── handlers.py
    ├── llm/
    │   ├── __init__.py
    │   ├── client.py
    │   └── adapter.py
    └── utils/
        ├── __init__.py
        ├── logging.py
        └── security.py