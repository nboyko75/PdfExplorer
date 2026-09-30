# Microsoft Store installer packaging

This folder contains a minimal MSIX package scaffold for the Windows desktop app. It is intended to be used after the regular PyInstaller build is complete.

## Workflow

1. Build the application with the existing project script:
   - `build.cmd`
2. Review and update the package metadata in `store/AppxManifest.xml`:
   - `Identity Name`
   - `Publisher`
   - `DisplayName`
   - `PublisherDisplayName`
3. Add real Store assets under `store/Assets/`:
   - `Logo44.png`
   - `Logo150.png`
   - `StoreLogo.png`
4. Run the packaging script:
   - PowerShell: `./store/build_msix.ps1`
5. Sign the package with a valid Microsoft Store certificate and upload the resulting `.msix` or `.msixupload` artifact via Partner Center.

## Development certificate build

After running `build.cmd`, run from the project root:

```powershell
.\store\build_dev_msix.ps1
# Optional version override (the source manifest is left unchanged):
.\store\build_dev_msix.ps1 -Version 1.0.4.0
```

Requires Windows PowerShell 5.1 or later and the Windows 10/11 SDK.
The script selects the newest installed SDK, creates or reuses a self-signed
code-signing certificate matching the manifest Publisher, and writes
`store/DocExplorer.Dev.msix` and the public `store/DocExplorer.Dev.cer`.
The private key stays in `Cert:\CurrentUser\My`. Certificates are valid for one
year and reused until fewer than 30 days remain.

For local testing, run the printed `Import-Certificate` command in an elevated
PowerShell window to trust the certificate, then run the printed `Add-AppxPackage`
command as your normal user. The script does not install the package or change
certificate trust automatically. This self-signed package is for development;
keep using the existing workflow for Store submission.

## Store packaging notes

- Both packaging scripts generate `resources.pri` using the Windows SDK's
  `makepri.exe` and `store/priconfig.xml`. This registers the target-size,
  unplated icon variants under `Assets/Logo44.png`; copying those PNG files
  without the resource index does not make them selectable by Windows Shell.

- If WebView2 aborts an Excel HTML preview, DocExplorer falls back to Office's
  PDF export and displays the workbook in print layout. The workbook stays
  unchanged. Errors from previews that have already been replaced are ignored.

- Word and Excel HTML previews require `WebView2Loader.dll` in the frozen app's
  `_internal` directory and the Microsoft Edge WebView2 Runtime on the machine.
  `DocExplorer.spec` explicitly includes the loader because wxWidgets loads it
  dynamically. Rebuild with `build.cmd` before packaging after source changes;
  the MSIX scripts only package the existing `dist` output.

- The app is packaged as a desktop Win32 application using an MSIX manifest.
- The generated package is suitable as a starting point for Store submission, but the final identity and certification metadata must be updated using your Microsoft Developer account before upload.
- `build_msix.ps1` expects the Windows 10/11 SDK to be installed (`makeappx.exe` and `signtool.exe`).
