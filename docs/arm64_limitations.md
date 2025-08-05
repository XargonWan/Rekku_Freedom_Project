# Multi-Architecture Browser Support

## nodriver Integration

The `selenium_chatgpt` LLM engine now uses **nodriver** instead of ChromeDriver, providing **full multi-architecture support**.

### Technical Details

- **Solution**: Migrated from undetected-chromedriver to nodriver
- **Browser Support**: Chrome and Chromium on all architectures
- **Architecture Support**: Full ARM64/aarch64 and x86-64 compatibility
- **Auto-Detection**: Automatic browser binary detection

### Platform Support Matrix

| Architecture | selenium_chatgpt | openai_chatgpt | manual |
|--------------|------------------|----------------|--------|
| x86-64       | ✅ Supported     | ✅ Supported   | ✅ Supported |
| ARM64        | ✅ Supported     | ✅ Supported   | ✅ Supported |

### Browser Compatibility

The system automatically detects and uses available browsers:

1. **x86-64 systems**: Google Chrome (preferred) or Chromium
2. **ARM64 systems**: Chromium (installed via PPA) or Google Chrome if available

### Container Build Process

The Dockerfile automatically handles browser installation:

- **x86-64**: Google Chrome from official repository
- **ARM64**: Chromium from xtradeb PPA (no snap required)
- **nodriver**: Handles browser automation without ChromeDriver

### nodriver Benefits

- **No ChromeDriver dependency**: Eliminates architecture compatibility issues
- **Native browser automation**: Direct browser control via DevTools Protocol
- **Multi-architecture**: Works seamlessly on ARM64 and x86-64
- **Automatic detection**: Finds and uses available browser binaries
- **Persistent sessions**: Maintains login sessions across restarts

### Migration Notes

- **From undetected-chromedriver**: Automatic migration, no configuration changes needed
- **API Compatibility**: Maintains Selenium-like API through wrapper class
- **Performance**: Similar or better performance with reduced dependencies

### Development Notes

- Architecture-agnostic browser automation
- Uses `NodriverSeleniumWrapper` for API compatibility
- Automatic browser binary detection and configuration
- No manual ChromeDriver installation or management required
