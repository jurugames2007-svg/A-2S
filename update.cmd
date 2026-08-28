@echo off
rem ============================================================
rem  A2S - auto-actualizacion EN EL SITIO (sin re-descargar el repo)
rem
rem  Uso desde este directorio:
rem      update tkm              actualiza (fetch + fast-forward)
rem      update tkm --check      solo mira si hay novedades
rem      update tkm --force      sincroniza a origin descartando lo local
rem
rem  Para poder escribir "update tkm" desde CUALQUIER carpeta,
rem  anade esto a tu perfil de PowerShell ($PROFILE):
rem      function update { & "C:\Users\Leo\Desktop\A-2S\update.cmd" @args }
rem  (o: Set-Alias update C:\Users\Leo\Desktop\A-2S\update.cmd)
rem ============================================================
setlocal
if exist "%~dp0npm\bin\a2s.mjs" (
    node "%~dp0npm\bin\a2s.mjs" update %*
    exit /b %ERRORLEVEL%
)
rem Fallback sin Node: directo con Python.
py -3 -m a2s update %* 2>nul || python -m a2s update %*
exit /b %ERRORLEVEL%
