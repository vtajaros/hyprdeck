import QtQuick
import "../theme"

Item {
    id: root

    property string selectedCategory: "All"
    property var categories: []
    property int totalCount: 0
    signal categorySelected(string category)

    implicitWidth: 500
    implicitHeight: chipFlow.implicitHeight

    ChipFlow {
        id: chipFlow
        width: parent.width
        spacing: 6

            // "All" chip
            Rectangle {
                id: allChip
                readonly property bool isSelected: root.selectedCategory === "All"
                height: 28
                width: allRow.width + 16
                radius: 14
                color: isSelected
                    ? Deck.accent
                    : (allMouse.containsMouse ? Deck.elevated : Deck.alpha(Deck.surface, 0.7))
                border.width: 1
                border.color: isSelected ? Deck.accent : Deck.alpha(Deck.muted, 0.2)

                Row {
                    id: allRow
                    anchors.centerIn: parent
                    spacing: 6

                    Text {
                        text: "All"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: allChip.isSelected ? Font.Bold : Font.Normal
                        color: allChip.isSelected ? Deck.bg : Deck.fg
                    }

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: allCnt.implicitWidth + 8
                        height: 16
                        radius: 8
                        color: allChip.isSelected ? Deck.alpha(Deck.bg, 0.2) : Deck.alpha(Deck.muted, 0.15)

                        Text {
                            id: allCnt
                            anchors.centerIn: parent
                            text: String(root.totalCount)
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: allChip.isSelected ? Deck.bg : Deck.muted
                        }
                    }
                }

                MouseArea {
                    id: allMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.selectedCategory = "All";
                        root.categorySelected("All");
                    }
                }
            }

            // Individual category chips
            Repeater {
                model: root.categories

                delegate: Rectangle {
                    id: chip
                    readonly property bool isSelected: root.selectedCategory === modelData.name
                    height: 28
                    width: chipRow.width + 16
                    radius: 14
                    color: isSelected
                        ? Deck.accent
                        : (chipMouse.containsMouse ? Deck.elevated : Deck.alpha(Deck.surface, 0.7))
                    border.width: 1
                    border.color: isSelected ? Deck.accent : Deck.alpha(Deck.muted, 0.2)

                    Row {
                        id: chipRow
                        anchors.centerIn: parent
                        spacing: 6

                        Text {
                            text: modelData.name
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            font.weight: chip.isSelected ? Font.Bold : Font.Normal
                            color: chip.isSelected ? Deck.bg : Deck.fg
                        }

                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: cntText.implicitWidth + 8
                            height: 16
                            radius: 8
                            color: chip.isSelected ? Deck.alpha(Deck.bg, 0.2) : Deck.alpha(Deck.muted, 0.15)

                            Text {
                                id: cntText
                                anchors.centerIn: parent
                                text: String(modelData.count)
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                color: chip.isSelected ? Deck.bg : Deck.muted
                            }
                        }
                    }

                    MouseArea {
                        id: chipMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.selectedCategory = modelData.name;
                            root.categorySelected(modelData.name);
                        }
                    }
                }
            }
        }
    }
