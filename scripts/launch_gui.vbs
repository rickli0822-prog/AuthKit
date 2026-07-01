Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = scriptDir & "\launch_gui.pyw"

pythonw = ""
Set exec = sh.Exec("cmd /c where pythonw")
If exec.Status = 0 Then
  lines = Split(Replace(exec.StdOut.ReadAll(), vbCr, ""), vbLf)
  If UBound(lines) >= 0 Then
  pythonw = Trim(lines(0))
  End If
End If

If pythonw = "" Then
  pythonw = "pythonw.exe"
End If

cmd = """" & pythonw & """ """ & pyw & """"
sh.Run cmd, 0, False
