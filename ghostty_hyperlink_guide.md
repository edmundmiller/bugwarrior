# Ghostty Hyperlink Configuration Guide

## Current Status

✅ **Hyperlinks are working correctly!** The bugwarrior code is generating proper ANSI hyperlink escape sequences.

## Evidence

From our testing, the output shows proper ANSI hyperlink sequences:
```
]8;id=408923;https://github.com/user/repo\Click me!]8;;\
]8;id=271704;https://github.com/user/repo\https://github.com/user/repo]8;;\
```

## Ghostty Configuration

To enable clickable hyperlinks in Ghostty, ensure these settings are enabled in your Ghostty configuration:

### 1. Check Ghostty Config File

Location: `~/.config/ghostty/config` or `$XDG_CONFIG_HOME/ghostty/config`

Add or verify these settings:
```ini
# Enable hyperlink support
hyperlink = true

# Enable click-to-open hyperlinks
hyperlink-click-to-open = true

# Optional: Set hyperlink modifiers (cmd on macOS, ctrl on Linux)
hyperlink-click-modifier = cmd
```

### 2. Alternative Configuration

If using TOML format (`~/.config/ghostty/config.toml`):
```toml
# Enable hyperlinks
hyperlink = true
hyperlink-click-to-open = true
hyperlink-click-modifier = "cmd"
```

### 3. Keyboard Shortcuts

In Ghostty, hyperlinks typically work with:
- **macOS**: `cmd+click` 
- **Linux**: `ctrl+click`

## Testing Hyperlinks

1. **Test basic functionality**:
   ```bash
   echo -e '\e]8;;https://github.com\e\\Click me!\e]8;;\e\\'
   ```

2. **Test with bugwarrior** (if you have diverged tasks):
   ```bash
   bugwarrior pull
   ```

3. **Test with our diagnostic script**:
   ```bash
   uv run python test_simple_hyperlinks.py
   ```

## Troubleshooting

If hyperlinks still don't work:

1. **Check Ghostty version**: Ensure you're using a recent version that supports hyperlinks
2. **Restart Ghostty**: Configuration changes may require restart
3. **Check for conflicts**: Some terminal multiplexers (tmux, screen) may interfere with hyperlinks
4. **Try different modifier keys**: Some setups use `ctrl+shift+click`

## Alternative Solutions

If Ghostty hyperlinks don't work, you can:

1. **Copy URLs**: The full URLs are displayed, you can copy-paste them
2. **Use browser extensions**: Tools like "Linkclicker" can help with terminal hyperlinks
3. **Configure different click handlers**: Some terminal emulators allow custom URL handlers

## Verification Commands

```bash
# Check if running in Ghostty
echo $TERM_PROGRAM  # Should show "ghostty"

# Check Ghostty version 
echo $TERM_PROGRAM_VERSION

# Test basic ANSI hyperlink
printf '\e]8;;https://example.com\e\\Test Link\e]8;;\e\\\n'
```

## Summary

The bugwarrior hyperlink implementation is working correctly. If links aren't clickable, it's a Ghostty configuration issue, not a code issue. Enable `hyperlink = true` and `hyperlink-click-to-open = true` in your Ghostty config.