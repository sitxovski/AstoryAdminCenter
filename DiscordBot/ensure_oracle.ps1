# Copyright (c) 2026 @sitxovski (Discord)
# Вотчдог Oracle: запускает демона, только если он не запущен.
# Ставится в планировщик каждые 5 минут; лишние экземпляры невозможны
# (в самом боте есть замок на порт 47653).
$running = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match 'oracle_bot\.py' }
if (-not $running) {
    Start-Process -FilePath "pythonw.exe" -ArgumentList "oracle_bot.py" `
        -WorkingDirectory "@@ASTORY_DEV_ROOT@@\AstoryAdminCenter\DiscordBot" -WindowStyle Hidden
}
