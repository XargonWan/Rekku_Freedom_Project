import pytest
from core.command_registry import execute_command, list_commands


@pytest.mark.asyncio
async def test_help_command_registered():
    assert "help" in list_commands()
    text = await execute_command("help")
    assert "Rekku – Available Commands" in text
    assert "/context" in text
