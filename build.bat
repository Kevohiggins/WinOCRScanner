@echo off
echo === Starting Compilation with PyInstaller... ===
if exist dist rd /s /q dist
.venv\Scripts\python -m PyInstaller "WinOCRScanner.spec" --distpath dist --noconfirm

echo === Copying manual.html to the compiled root folder ===
copy "manual.html" "dist\WinOCR Scanner\"

echo === Creating Update Package (Update.zip) ===
if exist update_pkg rd /s /q update_pkg
mkdir update_pkg
copy "dist\WinOCR Scanner\WinOCR Scanner.exe" "update_pkg\"
copy "dist\WinOCR Scanner\manual.html" "update_pkg\"

.venv\Scripts\python -c "import zipfile, os; zip_ref = zipfile.ZipFile('dist/WinOCR_Scanner_Update.zip', 'w', zipfile.ZIP_DEFLATED); [zip_ref.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), 'update_pkg')) for root, _, files in os.walk('update_pkg') for file in files]; zip_ref.close()"
rd /s /q update_pkg

echo === Done! Check the dist folder. ===