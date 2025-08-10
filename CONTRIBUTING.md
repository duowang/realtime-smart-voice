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

2. **Set up your environment:**
   ```bash
   cp .env.example .env
   # Add your API keys to .env
   ```
   
   **Get your API keys:**
   - **OpenAI**: Get Realtime API access at [platform.openai.com](https://platform.openai.com)
   - **Picovoice**: Sign up at [console.picovoice.ai](https://console.picovoice.ai) and create "Hi Taco" wake word for your platform

3. **Install dependencies:**
   ```bash
   ./run.sh  # This will create venv and install dependencies
   ```

4. **Test the setup:**
   ```bash
   ./run.sh  # Should start the assistant
   ```

## Making Changes

### Code Style
- Follow PEP 8 for Python code style
- Use descriptive variable and function names
- Add docstrings to classes and functions
- Keep functions focused and modular

### Testing
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
- Include relevant log files from `logs/`

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
- Ensure correct .ppn file compatibility
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
- This is currently in beta - changes may be needed
- Respect rate limits and usage guidelines
- Handle connection failures gracefully

### Picovoice Porcupine
- Custom wake word files are platform-specific
- Test with both built-in and custom wake words
- Handle authentication errors properly

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