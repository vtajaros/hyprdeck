import QtQuick

Item {
    property var command: []
    property string workingDirectory: ""
    property var stdout: null
    property var stderr: null
    property bool running: false
    signal exited(int code, int status)
    function exec() {}
}
