// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Mark Moore
import QtQuick
import qs.Common
import qs.Modules.Plugins
import qs.Widgets

PluginSettings {
    id: root
    pluginId: "vectorWallpaper"

    // ── Header ───────────────────────────────────────────────────────────────
    StyledText {
        width: parent.width
        text: "Vector Wallpaper"
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Font.Bold
        color: Theme.surfaceText
    }

    StyledText {
        width: parent.width
        text: "Generates a random SVG wallpaper using your shell's Primary Container color as the palette seed. Click the bar widget or the CC toggle to generate instantly."
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
        wrapMode: Text.WordWrap
    }

    // ── Style ────────────────────────────────────────────────────────────────
    SelectionSetting {
        settingKey: "wallpaperStyle"
        label: "Wallpaper Style"
        description: "Visual style of the generated wallpaper"
        defaultValue: "all"
        options: [
            { value: "all",            label: "Random (pick each time)" },
            { value: "geometric",      label: "Geometric – polygons & grids" },
            { value: "organic",        label: "Organic – blobs & curves" },
            { value: "circuit",        label: "Circuit – PCB traces & nodes" },
            { value: "cosmos",         label: "Cosmos – stars & nebulae" },
            { value: "gradient_waves", label: "Gradient Waves – layered sine curves" }
        ]
    }

    // ── Wallpaper setter ─────────────────────────────────────────────────────
    SelectionSetting {
        settingKey: "wallpaperSetter"
        label: "Wallpaper Setter"
        description: "Which tool to use to apply the wallpaper"
        defaultValue: "swww"
        options: [
            { value: "swww",      label: "swww (recommended – niri/Hyprland)" },
            { value: "swaybg",    label: "swaybg (Sway/wlroots)" },
            { value: "hyprpaper", label: "hyprpaper (Hyprland native)" },
            { value: "custom",    label: "Custom command (edit below)" }
        ]
    }

    StringSetting {
        settingKey: "wallpaperSetterCustom"
        label: "Custom Setter Command"
        description: "Used when 'Custom' is selected above. Use {path} as the SVG path placeholder. Example: feh --bg-fill {path}"
        placeholder: "e.g. feh --bg-fill {path}"
        defaultValue: ""
    }

    // ── Automation ───────────────────────────────────────────────────────────
    ToggleSetting {
        settingKey: "autoOnTheme"
        label: "Regenerate on Theme Change"
        description: "Automatically generate a new wallpaper when the shell theme changes"
        defaultValue: true
    }

    ToggleSetting {
        settingKey: "autoOnStartup"
        label: "Generate on Startup"
        description: "Generate a wallpaper automatically when DMS starts"
        defaultValue: true
    }

    // ── Info ─────────────────────────────────────────────────────────────────
    StyledText {
        width: parent.width
        text: "Color source"
        font.pixelSize: Theme.fontSizeMedium
        font.weight: Font.Medium
        color: Theme.surfaceText
        topPadding: Theme.spacingM
    }

    Row {
        spacing: Theme.spacingS
        width: parent.width

        Rectangle {
            width: 20; height: 20
            radius: 5
            color: Theme.primaryContainer
            border.color: Theme.outlineStrong
            border.width: 1
            anchors.verticalCenter: parent.verticalCenter
        }

        StyledText {
            text: "Theme.primaryContainer — changes automatically with your wallpaper/theme"
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceVariantText
            wrapMode: Text.WordWrap
            width: parent.width - 28
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    StyledText {
        width: parent.width
        text: "The generator uses this color's hue to seed a harmonious palette. Dark/light mode is inferred from the color's brightness."
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
        wrapMode: Text.WordWrap
    }

    // ── Requirements note ────────────────────────────────────────────────────
    StyledText {
        width: parent.width
        text: "Requirements"
        font.pixelSize: Theme.fontSizeMedium
        font.weight: Font.Medium
        color: Theme.surfaceText
        topPadding: Theme.spacingM
    }

    StyledText {
        width: parent.width
        text: "• python3 (stdlib only — no pip installs needed)\n• swww, swaybg, or hyprpaper for applying the wallpaper\n• gen_wallpaper.py must stay in the same plugin folder"
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
        wrapMode: Text.WordWrap
    }
}
