import QtQuick
import QtQuick.Layouts
import Quickshell
import "theme"
import "services"
import "components"
import "pages"

FloatingWindow {
    id: win

    title: "Hyprland Keybind Studio"
    implicitWidth: 1000
    implicitHeight: 700
    color: HKS.bg

    property string currentPage: "all" // "all" | "settings"

    Rectangle {
        anchors.fill: parent
        color: HKS.bg

        // Main layout: Sidebar (left) + Content Area (right)
        Row {
            anchors.fill: parent
            anchors.bottomMargin: statusBar.height

            // Left Sidebar
            Rectangle {
                width: 210
                height: parent.height
                color: HKS.surface
                border.width: 0

                // 1px subtle divider on right
                Rectangle {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 1
                    color: HKS.alpha(HKS.muted, 0.15)
                }

                Column {
                    anchors.fill: parent
                    anchors.margins: HKS.space12
                    spacing: HKS.space16

                    // App Brand Header
                    Row {
                        spacing: 10
                        anchors.left: parent.left
                        anchors.right: parent.right

                        Rectangle {
                            width: 32
                            height: 32
                            radius: 6
                            color: HKS.alpha(HKS.accent, 0.2)
                            border.width: 1
                            border.color: HKS.accent

                            Text {
                                anchors.centerIn: parent
                                text: ""
                                font.family: HKS.fontFamily
                                font.pixelSize: 16
                                color: HKS.accent
                            }
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text {
                                text: "Keybind Studio"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                font.weight: Font.Bold
                                color: HKS.fg
                            }
                            Text {
                                text: "Hyprland (HKS)"
                                font.family: HKS.fontFamily
                                font.pixelSize: 10
                                color: HKS.muted
                            }
                        }
                    }

                    // Navigation Items
                    Column {
                        width: parent.width
                        spacing: 4

                        SidebarItem {
                            width: parent.width
                            icon: ""
                            text: "All Keybindings"
                            active: win.currentPage === "all"
                            onClicked: win.currentPage = "all"
                        }

                        SidebarItem {
                            width: parent.width
                            icon: ""
                            text: "Conflicts"
                            disabled: true
                            badge: "soon"
                        }

                        SidebarItem {
                            width: parent.width
                            icon: ""
                            text: "Settings"
                            active: win.currentPage === "settings"
                            onClicked: win.currentPage = "settings"
                        }
                    }
                }
            }

            // Right Main Content
            Item {
                width: parent.width - 210
                height: parent.height

                AllKeybindings {
                    anchors.fill: parent
                    visible: win.currentPage === "all"
                    onRequestClose: win.visible = false
                }

                // Settings Page Stub
                Item {
                    anchors.fill: parent
                    visible: win.currentPage === "settings"

                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space24
                        spacing: HKS.space16

                        Text {
                            text: "Settings & Information"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeLarge
                            font.weight: Font.Bold
                            color: HKS.fg
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: HKS.alpha(HKS.muted, 0.2)
                        }

                        // App / Config Details Card
                        Rectangle {
                            width: parent.width
                            height: infoCol.implicitHeight + 24
                            radius: HKS.radiusSmall
                            color: HKS.surface
                            border.width: 1
                            border.color: HKS.alpha(HKS.muted, 0.2)

                            Column {
                                id: infoCol
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 8

                                Row {
                                    spacing: 8
                                    Text { width: 140; text: "Repository Root:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                                    Text { text: KeybindData.rootPath; color: HKS.fg; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall }
                                }
                                Row {
                                    spacing: 8
                                    Text { width: 140; text: "Entrypoint:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                                    Text { text: KeybindData.environment ? (KeybindData.environment.entrypoint || "-") : "-"; color: HKS.fg; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall }
                                }
                                Row {
                                    spacing: 8
                                    Text { width: 140; text: "Language:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                                    Text { text: KeybindData.environment ? (KeybindData.environment.language || "-") : "-"; color: HKS.accent; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall }
                                }
                                Row {
                                    spacing: 8
                                    Text { width: 140; text: "Hyprland Version:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                                    Text { text: KeybindData.environment ? (KeybindData.environment.hyprland_version || "unknown") : "unknown"; color: HKS.fg; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall }
                                }
                                Row {
                                    spacing: 8
                                    Text { width: 140; text: "Theme Source:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                                    Text { text: "~/.config/quickshell/theme/colors.json (Matugen / Quickshell)"; color: HKS.fg; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall }
                                }
                            }
                        }

                        // Theme Preview Swatches
                        Text {
                            text: "Active Palette Swatches"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.Bold
                            color: HKS.fg
                        }

                        Row {
                            spacing: 8
                            Repeater {
                                model: [
                                    { label: "bg", color: HKS.bg },
                                    { label: "surface", color: HKS.surface },
                                    { label: "elevated", color: HKS.elevated },
                                    { label: "accent", color: HKS.accent },
                                    { label: "fg", color: HKS.fg },
                                    { label: "muted", color: HKS.muted },
                                    { label: "warning", color: HKS.warning },
                                    { label: "critical", color: HKS.critical }
                                ]
                                delegate: Column {
                                    spacing: 4
                                    Rectangle {
                                        width: 44
                                        height: 32
                                        radius: 4
                                        color: modelData.color
                                        border.width: 1
                                        border.color: HKS.alpha(HKS.muted, 0.3)
                                    }
                                    Text {
                                        text: modelData.label
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 10
                                        color: HKS.muted
                                        anchors.horizontalCenter: parent.horizontalCenter
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Bottom Status Bar
        Rectangle {
            id: statusBar
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 28
            color: HKS.surface
            border.width: 0

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 1
                color: HKS.alpha(HKS.muted, 0.15)
            }

            Row {
                anchors.left: parent.left
                anchors.leftMargin: HKS.space12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 12

                Text {
                    text: {
                        var env = KeybindData.environment || {};
                        var st = KeybindData.stats || {};
                        var lang = env.language ? ("Language: " + env.language) : "";
                        var ep = env.entrypoint ? ("Entry: " + env.entrypoint.split("/").pop()) : "";
                        var hv = env.hyprland_version ? ("Hyprland: " + env.hyprland_version) : "";
                        var cnt = "Binds: " + KeybindData.binds.length;
                        var sbTime = (st.sandbox && st.sandbox.elapsed_ms !== undefined)
                            ? ("Elapsed: " + st.sandbox.elapsed_ms.toFixed(1) + "ms")
                            : "";
                        return [lang, ep, hv, cnt, sbTime].filter(Boolean).join("  •  ");
                    }
                    font.family: HKS.fontFamily
                    font.pixelSize: 10
                    color: HKS.muted
                }
            }

            Text {
                anchors.right: parent.right
                anchors.rightMargin: HKS.space12
                anchors.verticalCenter: parent.verticalCenter
                text: "Ctrl+R to reload  •  Esc to clear"
                font.family: HKS.fontFamily
                font.pixelSize: 10
                color: HKS.alpha(HKS.muted, 0.7)
            }
        }
    }
}
