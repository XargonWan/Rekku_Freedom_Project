import pytest
from core.command_registry import execute_command, list_commands, handle_command_message


@pytest.mark.asyncio
async def test_help_command_registered():
    assert "help" in list_commands()
    text = await execute_command("help")
    assert "Rekku – Available Commands" in text
    assert "/context" in text


@pytest.mark.asyncio
async def test_unknown_command_returns_none():
    """Test that unknown commands return None via handle_command_message instead of raising exceptions."""
    result = await handle_command_message("/unknown_command_that_does_not_exist")
    assert result is None


@pytest.mark.asyncio
async def test_execute_command_raises_for_unknown():
    """Test that execute_command still raises exceptions for unknown commands."""
    with pytest.raises(ValueError, match="Unknown command"):
        await execute_command("unknown_command_that_does_not_exist")
