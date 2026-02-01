# Script pour créer une tâche planifiée Windows
# Exécute la récupération des données SPX chaque jour à 21h55 (5 min avant clôture US)

$taskName = "OpenGamma_DailyFetch"
$pythonPath = "C:\projet\open-gamma\venv\Scripts\python.exe"
$scriptPath = "C:\projet\open-gamma\scheduled_fetch.py"
$workingDir = "C:\projet\open-gamma"
$logFile = "C:\projet\open-gamma\logs\scheduled_fetch.log"

# Créer le dossier de logs
New-Item -ItemType Directory -Path "C:\projet\open-gamma\logs" -Force | Out-Null

# Supprimer la tâche si elle existe déjà
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Créer l'action (exécuter le script Python)
$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument $scriptPath `
    -WorkingDirectory $workingDir

# Créer le trigger (tous les jours à 21h55)
$trigger = New-ScheduledTaskTrigger -Daily -At "21:55"

# Paramètres de la tâche
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Créer la tâche (s'exécute avec les droits de l'utilisateur actuel)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Récupère les données SPX depuis Tastytrade chaque jour avant la clôture US"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Tâche planifiée créée avec succès!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Nom: $taskName"
Write-Host "Heure: 21h55 (tous les jours)"
Write-Host "Script: $scriptPath"
Write-Host ""
Write-Host "Pour tester immédiatement, exécutez:"
Write-Host "  schtasks /run /tn `"$taskName`"" -ForegroundColor Yellow
Write-Host ""
Write-Host "Pour voir la tâche dans Task Scheduler:"
Write-Host "  taskschd.msc" -ForegroundColor Yellow
