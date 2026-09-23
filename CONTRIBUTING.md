# Contributing to Realtime Smart Voice Assistant

Thank you for your interest in contributing! This project welcomes contributions from developers of all experience levels.

## Quick Start

1. **Fork** the repository on GitHub
2. **Clone** your fork locally
3. **Create** a new branch for your changes
4. **Make** your changes
5. **Test** your changes thoroughly
6. **Submit** a pull request

## Development Setup

1. **Clone your fork:**
   ```bash
   git clone https://github.com/your-username/realtime-smart-voice.git
   cd realtime-smart-voice
   ```

2. **Install dependencies:**
   Follow the [system prerequisites in README](README.md#1-install-prerequisites-once), then:
   ```bash
   ./run.sh --setup-only  # Uses uv to install Python 3.12, or an existing Python 3.12
   make dev-deps
   ```
   Setup creates a private `.env` template and downloads the wake model. It needs no API key and opens no audio devices. Existing settings are preserved.

3. **Run the offline checks:**
   ```bash
   make check
   ```
   No OpenAI key is needed for the automated tests. Runner tests simulate package managers, Python creation, and failed installs without modifying the host.

4. **Try a voice interaction:**
   Add your OpenAI API key to `.env`, then run `./run.sh --doctor` and `./run.sh`.
   Say “Hi Taco,” wait for the greeting, and ask a short question. Press Ctrl+C to stop.

## Making Changes

### Code Style
- Follow PEP 8 for Python code style
- Use descriptive variable and function names
- Add docstrings to classes and functions
- Keep functions focused and modular

### Testing
- Run `make check` for compilation, Ruff linting of source/tests/tools, and the offline pytest suite
- CI runs these checks on Python 3.12 without API keys, downloads, or audio devices
- Use scoped mocks; never replace modules globally during test collection
- Run the optional headless integration flow from README after conversation or music lifecycle changes
- Test your changes thoroughly on your local setup
- Ensure wake word detection still works
- Verify real-time conversation functionality
- Test error conditions and edge cases

### Commit Guidelines
- Use clear, descriptive commit messages
- Make atomic commits (one logical change per commit)
- Reference issues in commit messages when applicable

Example commit messages:
```
Add support for custom wake word sensitivity
Fix audio device selection on macOS
Update documentation for new configuration options
```

## Types of Contributions

### 🐛 Bug Reports
- Use GitHub Issues with the "bug" label
- Include steps to reproduce
- Specify your operating system and Python version
- Include only relevant, reviewed diagnostic excerpts from `logs/`; remove personal information and keys. Content logging is off by default.

### 💡 Feature Requests
- Use GitHub Issues with the "enhancement" label
- Describe the problem you're trying to solve
- Explain your proposed solution
- Consider backward compatibility

### 📝 Documentation
- Fix typos, improve clarity
- Add examples and tutorials
- Update installation instructions
- Improve code comments

### 🔧 Code Improvements
- Performance optimizations
- Code refactoring
- Adding tests
- Improving error handling
- Platform compatibility improvements

## Platform-Specific Considerations

### macOS (Intel & Apple Silicon)
- Test on both Intel and Apple Silicon if possible
- Verify sherpa-onnx installation and model loading
- Verify audio device handling

### Linux/Raspberry Pi
- Test audio dependencies installation
- Verify real-time performance
- Check memory usage on resource-constrained devices

### Windows (if supported)
- Test audio device compatibility
- Verify path handling differences
- Check dependency installation

## API Considerations

### OpenAI Realtime API
- Keep session configuration and event handling compatible with the Realtime API used by the client
- Respect rate limits and usage guidelines
- Handle connection failures gracefully

### sherpa-onnx Wake Words
- Verify cached model startup without network access
- Test configured phrases and unrelated speech for misses and false activations
- Mock microphone and downloads in automated tests; keep model files and personal recordings out of Git

## Pull Request Process

1. **Branch naming:**
   - `feature/description` for new features
   - `fix/description` for bug fixes
   - `docs/description` for documentation

2. **PR Description:**
   - Describe what changes you made and why
   - Reference any related issues
   - Include testing notes
   - Add screenshots/recordings if UI changes

3. **Review Process:**
   - Maintainers will review your PR
   - Be responsive to feedback
   - Make requested changes promptly
   - Keep discussions constructive

## Security Considerations

- **Never commit API keys or secrets**
- **Don't include personal audio recordings**
- **Be careful with log files that might contain personal data**
- Report security vulnerabilities through the [private reporting channel in SECURITY.md](SECURITY.md), not a public issue.
- Run `make security-deps` and `make audit` when changing dependencies or security boundaries. This queries package advisory services; it does not upload source or recordings.
- **Use environment variables for sensitive configuration**

## Getting Help

- **GitHub Discussions** for questions and general discussion
- **GitHub Issues** for bugs and feature requests
- **Code Comments** explain complex logic inline

## Recognition

Contributors will be acknowledged in:
- GitHub contributors list
- Release notes for significant contributions
- README credits section (for major contributions)

Thank you for helping make this project better! 🎤🤖
