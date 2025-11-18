@echo off
echo Encerrando processos nas portas 8000 e 8501...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$pids = @(); try { $pids += (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).OwningProcess | Select-Object -Unique } catch {}; try { $pids += (Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue).OwningProcess | Select-Object -Unique } catch {}; $pids = $pids | Where-Object { $_ -ne $null } | Select-Object -Unique; if ($pids) { $pids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue; Write-Host ('Encerrado PID ' + $_) } } else { Write-Host 'Nenhum processo encontrado nas portas 8000/8501' }"
pause

