Dim projectDir, venvPython, mainScript, shell

projectDir  = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
venvPython  = projectDir & "\.venv\Scripts\pythonw.exe"
mainScript  = projectDir & "\main.py"

If Not CreateObject("Scripting.FileSystemObject").FileExists(venvPython) Then
    MsgBox "Virtual environment not found." & vbCrLf & _
           "Expected: " & venvPython & vbCrLf & vbCrLf & _
           "Run:  python -m venv venv  then  venv\Scripts\pip install -r requirements.txt", _
           vbCritical, "NB2PDF Launcher"
    WScript.Quit 1
End If

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = projectDir
shell.Run """" & venvPython & """ """ & mainScript & """", 0, False
