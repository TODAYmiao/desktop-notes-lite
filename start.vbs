Option Explicit
' Desktop Notes Lite launcher (console-free).
' Prefers the project venv, falls back to pythonw.exe from PATH.
' Note: main.py adds the repo folder and .pylibs to sys.path by itself,
' so no PYTHONPATH juggling is required here.
Dim fso, sh, dir, exe, script, venv
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
script = dir & "\main.py"
venv = dir & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(script) Then
  MsgBox "main.py not found next to this launcher.", 16, "Desktop Notes Lite"
  WScript.Quit 1
End If

If fso.FileExists(venv) Then
  exe = venv
Else
  exe = "pythonw.exe"
End If

sh.CurrentDirectory = dir
sh.Run """" & exe & """ """ & script & """", 0, False
