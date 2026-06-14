!macro DATABOX_REFRESH_SHORTCUT_ICON LINK_PATH
  Push "${LINK_PATH}"
  Call DataBoxRefreshShortcutIcon
!macroend

Function DataBoxRefreshShortcutIcon
  Exch $R9

  IfFileExists "$INSTDIR\databox-icon.ico" 0 done
  IfFileExists "$R9" 0 done

  CreateShortcut "$R9" "$INSTDIR\${MAINBINARYNAME}.exe" "" "$INSTDIR\databox-icon.ico" 0
  !insertmacro SetLnkAppUserModelId "$R9"

done:
  Pop $R9
FunctionEnd

!macro NSIS_HOOK_POSTINSTALL
  !insertmacro DATABOX_REFRESH_SHORTCUT_ICON "$DESKTOP\${PRODUCTNAME}.lnk"
  !insertmacro DATABOX_REFRESH_SHORTCUT_ICON "$SMPROGRAMS\${PRODUCTNAME}.lnk"
  !insertmacro DATABOX_REFRESH_SHORTCUT_ICON "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk"

  IfFileExists "$INSTDIR\databox-icon.ico" 0 done
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayIcon" "$\"$INSTDIR\databox-icon.ico$\""
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'

done:
!macroend
