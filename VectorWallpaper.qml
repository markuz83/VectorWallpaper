// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Mark Moore
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins

PluginComponent {
    id: root

    // ── Settings (synced from pluginData automatically) ──────────────────────
    property string wallpaperStyle:  pluginData.wallpaperStyle  || "all"
    property bool   autoOnTheme:     pluginData.autoOnTheme     ?? true
    property bool   autoOnStartup:   pluginData.autoOnStartup   ?? true
    property int    lastSeed:        pluginData.lastSeed        || 0

    // ── Internal state ───────────────────────────────────────────────────────
    property bool   generating:    false
    property string lastOutput:    ""   // SVG path
    property string lastPngOutput: ""   // PNG path (empty until first generate)
    property string statusText:    "Ready"

    // ── Derived paths ────────────────────────────────────────────────────────
    readonly property string settingsPath:
        Qt.resolvedUrl("../../settings.json").toString().replace("file://", "")

    // ── Color helpers ────────────────────────────────────────────────────────
    function hexFromColor(c) {
        function toHex(x) {
            var h = Math.round(x * 255).toString(16)
            return h.length === 1 ? "0" + h : h
        }
        return "#" + toHex(c.r) + toHex(c.g) + toHex(c.b)
    }

    // Material You tokens passed to the generator
    readonly property color  shellColor:                Theme.primaryContainer  // used for the bar swatch
    readonly property bool   isDarkMode:                !SessionData.isLightMode
    readonly property string surfaceHex:                hexFromColor(Theme.surface)
    readonly property string primaryHex:                hexFromColor(Theme.primary)
    readonly property string secondaryHex:              hexFromColor(Theme.secondary)
    readonly property string tertiaryHex:               hexFromColor(Theme.tertiary)
    readonly property string primaryContainerHex:       hexFromColor(Theme.primaryContainer)
    readonly property string secondaryContainerHex:     hexFromColor(Theme.secondaryContainer)
    readonly property string tertiaryContainerHex:      hexFromColor(Theme.tertiaryContainer)
    readonly property string inversePrimaryHex:         hexFromColor(Theme.inversePrimary)

    // ── Watch for theme changes → auto-regenerate ───────────────────────────
    onShellColorChanged: {
        if (autoOnTheme && !generating) {
            generateWallpaper()
        }
    }

    // ── Generate on startup ──────────────────────────────────────────────────
    Component.onCompleted: {
        if (autoOnStartup) {
            generateWallpaper()
        }
    }

    // ── Core generate function ───────────────────────────────────────────────
    function generateWallpaper() {
        if (generating) return

        var seed = Math.floor(Math.random() * 2147483647)
        var screenW = Qt.application.screens[0] ? Qt.application.screens[0].width  : 1920
        var screenH = Qt.application.screens[0] ? Qt.application.screens[0].height : 1080

        var scriptPath = Qt.resolvedUrl("./gen_wallpaper.py").toString().replace("file://", "")

        generatorProcess.command = [
            "python3", scriptPath,
            "--colors", primaryHex, secondaryHex, tertiaryHex,
                        primaryContainerHex, secondaryContainerHex, tertiaryContainerHex,
            "--surface", surfaceHex,
            "--accent",  inversePrimaryHex,
            "--mode",    isDarkMode ? "dark" : "light",
            "--style",   wallpaperStyle,
            "--seed",    seed.toString(),
            "--width",   screenW.toString(),
            "--height",  screenH.toString()
        ]

        generating = true
        statusText = "Generating…"
        generatorProcess.running = true

        if (pluginService) {
            pluginService.savePluginData(pluginId, "lastSeed", seed)
        }
    }

    // ── Save current PNG as a timestamped favourite ──────────────────────────
    function saveAsFavorite() {
        if (lastPngOutput.length === 0 || generating) return
        var dir = lastPngOutput.substring(0, lastPngOutput.lastIndexOf("/"))
        var favPath = dir + "/dms_wallpaper_fav_" + Date.now() + ".png"
        favoriteProcess.favPath = favPath
        favoriteProcess.command = ["cp", lastPngOutput, favPath]
        favoriteProcess.running = true
    }

    // ── Process: Python SVG generator ───────────────────────────────────────
    Process {
        id: generatorProcess

        property string outputPath: ""

        stdout: SplitParser {
            onRead: line => {
                if (line.trim().length > 0) {
                    generatorProcess.outputPath = line.trim()
                }
            }
        }

        stderr: SplitParser {
            onRead: line => {
                if (line.trim().length > 0) {
                    console.warn("[VectorWallpaper] stderr:", line)
                    root.statusText = "Error: " + line
                }
            }
        }

        onExited: (exitCode) => {
            root.generating = false
            if (exitCode === 0 && outputPath.length > 0) {
                root.lastOutput = outputPath
                root.statusText = "Converting…"
                var pngPath = outputPath.replace(/\.svg$/, ".png")
                svgToPngProcess.pngPath = pngPath
                svgToPngProcess.command = ["rsvg-convert", "-o", pngPath, outputPath]
                svgToPngProcess.running = true
                outputPath = ""
            } else {
                root.statusText = "Failed (exit " + exitCode + ")"
                ToastService.showError("Vector Wallpaper", "Generation failed – check logs")
            }
        }
    }

    // ── Process: SVG → PNG via rsvg-convert ─────────────────────────────────
    Process {
        id: svgToPngProcess

        property string pngPath: ""

        stderr: SplitParser {
            onRead: line => {
                if (line.trim().length > 0) {
                    console.warn("[VectorWallpaper] rsvg-convert:", line)
                }
            }
        }

        onExited: (exitCode) => {
            if (exitCode === 0) {
                root.lastPngOutput = pngPath
                wallpaperSetProcess.command = root.buildSetCommand(pngPath)
                wallpaperSetProcess.running = true
            } else {
                root.statusText = "PNG conversion failed"
                ToastService.showError("Vector Wallpaper",
                    "SVG→PNG conversion failed. Is rsvg-convert installed?")
            }
            pngPath = ""
        }
    }

    // ── Process: apply wallpaper ─────────────────────────────────────────────
    Process {
        id: wallpaperSetProcess

        onExited: (exitCode) => {
            if (exitCode === 0) {
                root.statusText = "Applied ✓"
                ToastService.showInfo("Vector Wallpaper", "New wallpaper applied")
                updateSettingsProcess.newWallpaperPath = root.lastPngOutput
                updateSettingsProcess.running = true
            } else {
                root.statusText = "Set failed"
                ToastService.showWarning("Vector Wallpaper",
                    "PNG generated but wallpaper setter failed. Is swww/swaybg installed?")
            }
        }
    }

    // ── Process: patch wallpaperPath in DMS settings.json ───────────────────
    Process {
        id: updateSettingsProcess

        property string newWallpaperPath: ""

        environment: ({
            "DMS_SETTINGS": root.settingsPath,
            "DMS_WALLPAPER": newWallpaperPath
        })

        command: [
            "python3", "-c",
            "import json,os; f=os.environ['DMS_SETTINGS']; p=os.environ['DMS_WALLPAPER']; " +
            "d=json.load(open(f)); d['wallpaperPath']=p; open(f,'w').write(json.dumps(d,indent=2))"
        ]

        onExited: (exitCode) => {
            if (exitCode !== 0) {
                console.warn("[VectorWallpaper] Failed to update wallpaperPath in settings.json")
            }
            newWallpaperPath = ""
        }
    }

    // ── Process: copy current PNG to a favourite ─────────────────────────────
    Process {
        id: favoriteProcess

        property string favPath: ""

        onExited: (exitCode) => {
            if (exitCode === 0) {
                ToastService.showInfo("Vector Wallpaper",
                    "Saved ★ " + favPath.substring(favPath.lastIndexOf("/") + 1))
            } else {
                ToastService.showError("Vector Wallpaper", "Failed to save favourite")
            }
            favPath = ""
        }
    }

    // ── Build the wallpaper-set command ──────────────────────────────────────
    function buildSetCommand(imgPath) {
        var setter = pluginData.wallpaperSetter || "swww"
        if (setter === "swww") {
            return ["swww", "img", imgPath,
                    "--transition-type", "fade",
                    "--transition-duration", "1"]
        } else if (setter === "swaybg") {
            return ["swaybg", "-i", imgPath, "-m", "fill"]
        } else if (setter === "hyprpaper") {
            return ["sh", "-c",
                "hyprctl hyprpaper preload '" + imgPath + "' && " +
                "hyprctl hyprpaper wallpaper '," + imgPath + "'"]
        } else {
            var customCmd = pluginData.wallpaperSetterCustom || ""
            return ["sh", "-c", customCmd.replace("{path}", imgPath)]
        }
    }

    // ── DankBar pills ────────────────────────────────────────────────────────
    horizontalBarPill: Component {
        Row {
            spacing: 0

            // ── Generate section ─────────────────────────────────────────────
            Item {
                implicitWidth:  genRow.implicitWidth + Theme.spacingS * 2
                implicitHeight: genRow.implicitHeight

                Row {
                    id: genRow
                    anchors.centerIn: parent
                    spacing: Theme.spacingS

                    Rectangle {
                        width: 14; height: 14
                        radius: 3
                        color: root.shellColor
                        border.color: Theme.outlineStrong
                        border.width: 1
                        anchors.verticalCenter: parent.verticalCenter

                        Rectangle {
                            anchors.centerIn: parent
                            width: 8; height: 8
                            radius: 4
                            color: Theme.primary
                            visible: root.generating
                            RotationAnimator on rotation {
                                from: 0; to: 360
                                duration: 900
                                loops: Animation.Infinite
                                running: root.generating
                            }
                        }
                    }

                    StyledText {
                        text: root.generating ? "Generating…" : "Wallpaper"
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.surfaceText
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.generateWallpaper()
                }
            }

            // ── Divider ──────────────────────────────────────────────────────
            Rectangle {
                width: 1; height: 10
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.outlineVariant
                opacity: 0.4
            }

            // ── Favourite section ────────────────────────────────────────────
            Item {
                implicitWidth:  Theme.spacingS + 14 + Theme.spacingS
                implicitHeight: genRow.implicitHeight

                DankIcon {
                    name: "star"
                    size: 12
                    color: root.lastPngOutput.length > 0 ? Theme.primary : Theme.onSurfaceVariant
                    opacity: root.lastPngOutput.length > 0 ? 1.0 : 0.35
                    anchors.centerIn: parent
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: root.lastPngOutput.length > 0
                        ? Qt.PointingHandCursor : Qt.ArrowCursor
                    enabled: root.lastPngOutput.length > 0
                    onClicked: root.saveAsFavorite()
                }
            }
        }
    }

    verticalBarPill: Component {
        Column {
            spacing: 0

            // ── Generate section ─────────────────────────────────────────────
            Item {
                implicitWidth:  pillCol.implicitWidth
                implicitHeight: pillCol.implicitHeight

                Column {
                    id: pillCol
                    anchors.centerIn: parent
                    spacing: Theme.spacingXS

                    DankIcon {
                        name: root.generating ? "refresh" : "wallpaper"
                        size: Theme.iconSize
                        color: root.generating ? Theme.primary : Theme.surfaceText
                        anchors.horizontalCenter: parent.horizontalCenter

                        RotationAnimator on rotation {
                            from: 0; to: 360
                            duration: 900
                            loops: Animation.Infinite
                            running: root.generating
                        }
                    }

                    StyledText {
                        text: root.generating ? "…" : "Wall"
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.surfaceText
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.generateWallpaper()
                }
            }

            // ── Favourite section ────────────────────────────────────────────
            Item {
                implicitWidth:  pillCol.implicitWidth
                implicitHeight: Theme.iconSize + Theme.spacingXS

                DankIcon {
                    name: "star"
                    size: Theme.iconSize - 4
                    color: root.lastPngOutput.length > 0 ? Theme.primary : Theme.onSurfaceVariant
                    opacity: root.lastPngOutput.length > 0 ? 1.0 : 0.35
                    anchors.centerIn: parent
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: root.lastPngOutput.length > 0
                        ? Qt.PointingHandCursor : Qt.ArrowCursor
                    enabled: root.lastPngOutput.length > 0
                    onClicked: root.saveAsFavorite()
                }
            }
        }
    }

    // ── Control Center widget ────────────────────────────────────────────────
    ccWidgetIcon: root.generating ? "refresh" : "wallpaper"
    ccWidgetPrimaryText: "Vector Wallpaper"
    ccWidgetSecondaryText: root.statusText + " • " + root.wallpaperStyle
    ccWidgetIsActive: !root.generating

    onCcWidgetToggled: {
        root.generateWallpaper()
    }
}
