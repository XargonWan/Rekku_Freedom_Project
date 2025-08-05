# ARM64 Architecture Limitations

## ChromeDriver Compatibility

The `selenium_chatgpt` LLM engine is **not compatible** with ARM64/aarch64 architectures due to ChromeDriver limitations.

### Technical Details

- **Issue**: ChromeDriver does not provide official ARM64 binaries
- **Affected Plugin**: `selenium_chatgpt` 
- **Architecture Detection**: Automatic detection prevents startup on ARM64 systems
- **Error Handling**: Clear error message with alternative suggestions

### Platform Support Matrix

| Architecture | selenium_chatgpt | openai_chatgpt | manual |
|--------------|------------------|----------------|--------|
| x86-64       | ✅ Supported     | ✅ Supported   | ✅ Supported |
| ARM64        | ❌ Not Supported | ✅ Supported   | ✅ Supported |

### Alternative Solutions

When running on ARM64 systems, use these LLM engines instead:

1. **openai_chatgpt**: Full OpenAI API integration
2. **manual**: Manual prompt handling
3. **Any other non-Selenium engine**: Check available plugins

### Container Build Process

The Dockerfile automatically detects the target architecture:

- **x86-64**: ChromeDriver is installed and configured
- **ARM64**: ChromeDriver installation is skipped with warning messages

### Error Messages

When attempting to use selenium_chatgpt on ARM64:

```
❌ selenium_chatgpt plugin is not supported on ARM64 architecture.
Current machine type: aarch64
ChromeDriver does not officially support ARM64.
Please use a different LLM engine (openai_chatgpt, manual, etc.).
```

### Development Notes

- Architecture check occurs in `SeleniumChatGPTPlugin.__init__()`
- Uses `platform.machine()` for detection
- Prevents startup rather than runtime failures
- Maintains compatibility with existing x86-64 deployments
