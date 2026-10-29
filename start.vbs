Option Explicit
Dim fso, sh, dir, exe, script
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
exe = dir & "\.venv\Scripts\pythonw.exe"
script = dir & "\main.py"
If Not fso.FileExists(exe) Then
  MsgBox "Python environment not found. See README.md for setup steps.", 16, "Desktop Notes Lite"
  WScript.Quit 1
End If
sh.CurrentDirectory = dir
sh.Run """" & exe & """ """ & script & """", 0, False
