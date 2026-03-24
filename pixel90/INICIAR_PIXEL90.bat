@echo off
title PIXEL90 - Sistema de Gestion
color 0B
echo.
echo  ██████╗ ██╗██╗  ██╗███████╗██╗      █████╗  ██████╗
echo  ██╔══██╗██║╚██╗██╔╝██╔════╝██║     ██╔══██╗██╔═████╗
echo  ██████╔╝██║ ╚███╔╝ █████╗  ██║     ╚██████║██║██╔██║
echo  ██╔═══╝ ██║ ██╔██╗ ██╔══╝  ██║      ╚═══██║████╔╝██║
echo  ██║     ██║██╔╝ ██╗███████╗███████╗ █████╔╝╚██████╔╝
echo  ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚════╝  ╚═════╝
echo.
echo  Sistema de Gestion Comercial
echo  ─────────────────────────────────────────────────────
echo.
echo  Iniciando servidor...
echo  Abri tu navegador en: http://localhost:5000
echo.
echo  Para cerrar el servidor: presiona Ctrl+C
echo.
start "" "http://localhost:5000"
python app.py
pause
