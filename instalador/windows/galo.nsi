; Instalador da GALO para Windows. Compilado pelo instalador/construir.py com o makensis (NSIS).
; Instala só para o usuário (sem pedir administrador), como o instalador do Python faz por padrão.
;
;   makensis -DVERSAO=0.2.0 -DORIGEM=<pasta com os arquivos> -DSAIDA=<instalador.exe> galo.nsi

Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!ifndef VERSAO
  !define VERSAO "0.0.0"
!endif
!define CHAVE_APP "Software\GALO"
!define CHAVE_DESINSTALAR "Software\Microsoft\Windows\CurrentVersion\Uninstall\GALO"
!define CHAVE_CLASSES "Software\Classes"
!define POWERSHELL "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe"

Name "GALO ${VERSAO}"
OutFile "${SAIDA}"
InstallDir "$LOCALAPPDATA\Programs\GALO"
InstallDirRegKey HKCU "${CHAVE_APP}" "Pasta"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "GALO — programe em português"
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "${VERSAO}.0"
VIAddVersionKey /LANG=1046 "ProductName" "GALO"
VIAddVersionKey /LANG=1046 "FileDescription" "Instalador da linguagem de programação GALO"
VIAddVersionKey /LANG=1046 "FileVersion" "${VERSAO}"
VIAddVersionKey /LANG=1046 "ProductVersion" "${VERSAO}"
VIAddVersionKey /LANG=1046 "LegalCopyright" "Projeto GALO — licença MIT"

!define MUI_ICON "${ORIGEM}\galo.ico"
!define MUI_UNICON "${ORIGEM}\galo.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Bem-vindo à GALO ${VERSAO}"
!define MUI_WELCOMEPAGE_TEXT "A GALO é uma linguagem de programação em português.$\r$\n$\r$\nEste instalador coloca no seu computador tudo o que a linguagem precisa (não é preciso ter Python instalado), o comando galo para usar em qualquer pasta, o reconhecimento dos arquivos .galo e a extensão para editores de código.$\r$\n$\r$\nNão é preciso ser administrador."
!define MUI_FINISHPAGE_TITLE "A GALO está instalada!"
!define MUI_FINISHPAGE_TEXT "Abra um terminal novo (Prompt de Comando ou PowerShell) e experimente:$\r$\n$\r$\n    galo --versao$\r$\n    galo repl$\r$\n$\r$\nArquivos .galo agora abrem com a GALO num duplo clique."
!define MUI_FINISHPAGE_LINK "Conhecer a GALO e ver exemplos"
!define MUI_FINISHPAGE_LINK_LOCATION "https://joaopaulocmark.github.io/GALO/"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${ORIGEM}\LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Section "GALO (obrigatório)" SecGalo
  SectionIn RO
  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\runtime"          ; atualização: remove a versão anterior do Python embutido
  File /r "${ORIGEM}\*.*"
  WriteUninstaller "$INSTDIR\desinstalar.exe"
  WriteRegStr HKCU "${CHAVE_APP}" "Pasta" "$INSTDIR"
  WriteRegStr HKCU "${CHAVE_APP}" "Versao" "${VERSAO}"

  ; "Aplicativos instalados" do Windows
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "DisplayName" "GALO ${VERSAO}"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "DisplayVersion" "${VERSAO}"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "Publisher" "Projeto GALO"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "DisplayIcon" "$INSTDIR\galo.ico"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "URLInfoAbout" "https://joaopaulocmark.github.io/GALO/"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "UninstallString" '"$INSTDIR\desinstalar.exe"'
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "QuietUninstallString" '"$INSTDIR\desinstalar.exe" /S'
  WriteRegDWORD HKCU "${CHAVE_DESINSTALAR}" "NoModify" 1
  WriteRegDWORD HKCU "${CHAVE_DESINSTALAR}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "${CHAVE_DESINSTALAR}" "EstimatedSize" $0

  ; pré-compila o pacote galo: os programas começam a rodar mais rápido
  DetailPrint "Preparando a GALO..."
  nsExec::ExecToLog '"$INSTDIR\runtime\python.exe" -I -m compileall -q "$INSTDIR\runtime\Lib\site-packages\galo"'
  Pop $0
SectionEnd

Section "Comando galo em qualquer terminal (PATH)" SecPath
  DetailPrint "Adicionando a GALO ao PATH..."
  nsExec::ExecToLog '"${POWERSHELL}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\caminho.ps1" -Acao adicionar -Pasta "$INSTDIR"'
  Pop $0
SectionEnd

Section "Abrir arquivos .galo com a GALO" SecArquivos
  WriteRegStr HKCU "${CHAVE_CLASSES}\.galo" "" "GALO.Programa"
  WriteRegStr HKCU "${CHAVE_CLASSES}\.galo" "Content Type" "text/plain"
  WriteRegStr HKCU "${CHAVE_CLASSES}\.galo" "PerceivedType" "text"
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Programa" "" "Programa GALO"
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Programa\DefaultIcon" "" "$INSTDIR\galo.ico"
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Programa\shell" "" "executar"
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Programa\shell\executar" "" "Executar com GALO"
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Programa\shell\executar\command" "" '"$INSTDIR\galo.cmd" abrir "%1"'
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Programa\shell\editar" "" "Editar"
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Programa\shell\editar\command" "" '"$WINDIR\notepad.exe" "%1"'
  WriteRegStr HKCU "${CHAVE_CLASSES}\.galoc" "" "GALO.Compilado"
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Compilado" "" "Programa GALO compilado"
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Compilado\DefaultIcon" "" "$INSTDIR\galo.ico"
  WriteRegStr HKCU "${CHAVE_CLASSES}\GALO.Compilado\shell\open\command" "" '"$INSTDIR\galo.cmd" abrir "%1"'
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Section "Extensão para VS Code, Cursor e VSCodium" SecEditores
  DetailPrint "Procurando editores de código..."
  nsExec::ExecToLog '"$INSTDIR\galo.cmd" extensao'
  Pop $0
SectionEnd

LangString DESC_GALO ${LANG_PORTUGUESEBR} "A linguagem GALO e tudo o que ela precisa para funcionar (inclui um Python próprio, separado de outros que você tenha)."
LangString DESC_PATH ${LANG_PORTUGUESEBR} "Permite digitar galo em qualquer pasta, no Prompt de Comando ou no PowerShell."
LangString DESC_ARQUIVOS ${LANG_PORTUGUESEBR} "Ícone da GALO nos arquivos .galo; com dois cliques o programa roda (e clicando com o botão direito há a opção Editar)."
LangString DESC_EDITORES ${LANG_PORTUGUESEBR} "Cores, autocompletar e erros enquanto você digita, nos editores que estiverem instalados."
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecGalo} $(DESC_GALO)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecPath} $(DESC_PATH)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecArquivos} $(DESC_ARQUIVOS)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecEditores} $(DESC_EDITORES)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  ; tira a pasta do PATH antes de apagar o script que faz isso
  nsExec::ExecToLog '"${POWERSHELL}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\caminho.ps1" -Acao remover -Pasta "$INSTDIR"'
  Pop $0

  ; associações (só se ainda apontam para a GALO)
  ReadRegStr $0 HKCU "${CHAVE_CLASSES}\.galo" ""
  ${If} $0 == "GALO.Programa"
    DeleteRegKey HKCU "${CHAVE_CLASSES}\.galo"
  ${EndIf}
  ReadRegStr $0 HKCU "${CHAVE_CLASSES}\.galoc" ""
  ${If} $0 == "GALO.Compilado"
    DeleteRegKey HKCU "${CHAVE_CLASSES}\.galoc"
  ${EndIf}
  DeleteRegKey HKCU "${CHAVE_CLASSES}\GALO.Programa"
  DeleteRegKey HKCU "${CHAVE_CLASSES}\GALO.Compilado"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'

  ; só os arquivos da GALO (nunca a pasta inteira, caso a pessoa tenha escolhido uma pasta com outras coisas)
  RMDir /r "$INSTDIR\runtime"
  Delete "$INSTDIR\galo.cmd"
  Delete "$INSTDIR\galo.ico"
  Delete "$INSTDIR\galo.vsix"
  Delete "$INSTDIR\caminho.ps1"
  Delete "$INSTDIR\LICENSE.txt"
  Delete "$INSTDIR\LEIA-ME.txt"
  Delete "$INSTDIR\desinstalar.exe"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "${CHAVE_DESINSTALAR}"
  DeleteRegKey HKCU "${CHAVE_APP}"
SectionEnd
