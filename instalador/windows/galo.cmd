@echo off
rem Comando "galo": usa o Python embutido nesta pasta, isolado de outros Pythons da maquina.
"%~dp0runtime\python.exe" -I -X utf8 -m galo %*
