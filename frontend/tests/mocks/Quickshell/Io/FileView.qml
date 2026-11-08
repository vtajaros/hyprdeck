import QtQuick

Item {
    property string path: ""
    property string text: ""
    property bool printErrors: false
    property bool watchChanges: false
    property bool blockLoading: false
    signal fileChanged()
}
