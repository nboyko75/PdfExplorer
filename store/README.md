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

## Notes

- The app is packaged as a desktop Win32 application using an MSIX manifest.
- The generated package is suitable as a starting point for Store submission, but the final identity and certification metadata must be updated using your Microsoft Developer account before upload.
- `build_msix.ps1` expects the Windows 10/11 SDK to be installed (`makeappx.exe` and `signtool.exe`).
