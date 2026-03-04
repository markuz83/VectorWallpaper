# VectorWallpaper — DankMaterialShell Plugin

Generates a randomised SVG wallpaper that's colour-matched to your shell's
**Primary Container** value. Every time your theme changes, a fresh wallpaper
is generated and applied automatically.

## Files

```
VectorWallpaper/
├── plugin.json                  # DMS plugin manifest
├── VectorWallpaper.qml          # Main widget (bar pill + CC toggle)
├── VectorWallpaperSettings.qml  # Settings panel
├── gen_wallpaper.py             # Python SVG generator (stdlib only)
└── README.md                    # This file
```

## Installation

```bash
# Copy the plugin folder to DMS plugins directory
cp -r VectorWallpaper ~/.config/DankMaterialShell/plugins/

# Make the generator executable
chmod +x ~/.config/DankMaterialShell/plugins/VectorWallpaper/gen_wallpaper.py
```

Then in DMS:
1. **Settings → Plugins → Scan for Plugins**
2. Toggle **Vector Wallpaper** on
3. Add it to your DankBar widget list
4. Restart shell: `dms restart`

## Requirements

| Dependency | Purpose |
|---|---|
| `python3` | SVG generation (stdlib only, no pip) |
| `swww` | Apply wallpaper (niri/Hyprland) |
| `swaybg` | Apply wallpaper (Sway/wlroots) |
| `hyprpaper` | Apply wallpaper (Hyprland native) |

Install your preferred setter, e.g.:
```bash
# Arch
paru -S swww

# Then start the daemon (add to compositor autostart too)
swww-daemon &
```

## Styles

| Style | Description |
|---|---|
| `geometric` | Translucent polygons, triangles, grid lines |
| `organic` | Blurred blobs, flowing bezier curves |
| `circuit` | PCB traces, connection nodes with glow |
| `cosmos` | Star field, nebulae, shooting streaks |
| `gradient_waves` | Layered sine-wave landscape |
| `all` | Randomly picks one each run |

## How It Works

1. DMS exposes `Theme.primaryContainer` — the Material You primary container colour.
2. The QML component converts it to a hex string and passes `--color #rrggbb` to the Python generator.
3. Python derives the hue from that hex value and builds an analogous/triadic/complementary palette around it. Dark or light mode is inferred from the colour's lightness.
4. The SVG is written to `/tmp/dms_wallpaper_<seed>.svg`.
5. The chosen wallpaper setter (`swww`, `swaybg`, or `hyprpaper`) applies it.

## Usage Tips

- **Click the bar widget** or **toggle in Control Center** to regenerate instantly.
- Enable **"Regenerate on Theme Change"** to keep wallpaper in sync with matugen/dank16 theme switches.
- Use `--seed` in the generator directly to reproduce a specific wallpaper:
  ```bash
  python3 gen_wallpaper.py --color "#6750A4" --style cosmos --seed 42
  ```
- Output SVGs are pure vector — they scale perfectly to any resolution.
