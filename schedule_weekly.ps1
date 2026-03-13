# Windows Task Scheduler registration script for AI Research System
# This script schedules the AI Research System to run every Monday at 9:00 AM.

$Action = New-ScheduledTaskAction -Execute "python.exe" -Argument "main.py" -WorkingDirectory "c:\Users\tatat\AIresearch"
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

$TaskName = "AI_Research_Weekly_Report"

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force

Write-Host "Successfully scheduled '$TaskName' to run every Monday at 9:00 AM."
Write-Host "Note: Ensure 'python.exe' is in your PATH or update the script with the full path to python.exe."
