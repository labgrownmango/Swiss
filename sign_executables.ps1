Start-Transcript -Path "C:\Users\jost-\OneDrive\Desktop(1)\Projekte\swiss\sign_log.txt" -Force

# Create self-signed code signing certificate
$certSubject = "CN=SwissToolsLocalDevelopment"
Write-Host "Generating self-signed code signing certificate..."

# Check if certificate already exists
$existingCert = Get-ChildItem -Path "Cert:\CurrentUser\My" | Where-Object { $_.Subject -like "*$certSubject*" } | Select-Object -First 1

if ($existingCert) {
    $cert = $existingCert
    Write-Host "Using existing certificate: $($cert.Thumbprint)"
} else {
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $certSubject -CertStoreLocation "Cert:\CurrentUser\My"
    Write-Host "Created new certificate: $($cert.Thumbprint)"
}

# Export public key to User's Desktop so they can trust it manually if desired
$desktopCertPath = "C:\Users\jost-\OneDrive\Desktop(1)\SwissToolsLocalDev.cer"
Write-Host "Exporting trusted certificate to Desktop: $desktopCertPath"
Export-Certificate -Cert $cert -FilePath $desktopCertPath | Out-Null

# Import to TrustedPublisher for CurrentUser (this is 100% silent and never prompts!)
Write-Host "Importing certificate into TrustedPublisher store..."
certutil -user -f -addstore TrustedPublisher $desktopCertPath | Out-Null

# Sign Messenger Executable
$messengerExe = "D:\Privacy Messenger\electron-signed\electron.exe"
if (Test-Path $messengerExe) {
    Write-Host "Signing Messenger: $messengerExe"
    Set-AuthenticodeSignature -FilePath $messengerExe -Certificate $cert
} else {
    Write-Warning "Messenger executable not found at $messengerExe"
}

# Sign Swiss Backend Executable (if compiled)
$backendExe = "C:\Users\jost-\OneDrive\Desktop(1)\Projekte\swiss\backend\dist\backend.exe"
if (Test-Path $backendExe) {
    Write-Host "Signing Swiss Backend: $backendExe"
    Set-AuthenticodeSignature -FilePath $backendExe -Certificate $cert
} else {
    Write-Warning "Swiss backend executable not found at $backendExe"
}

# Sign Swiss Electron Main Executable (if installed)
$swissElectronExe = "C:\Users\jost-\Apps\Swiss\Swiss Tools\Swiss.exe"
if (Test-Path $swissElectronExe) {
    Write-Host "Signing Swiss Tools Electron app: $swissElectronExe"
    Set-AuthenticodeSignature -FilePath $swissElectronExe -Certificate $cert
}

# Sign Swiss NSIS Installer (if built)
$swissInstallerExe = "C:\Users\jost-\OneDrive\Desktop(1)\Projekte\swiss\dist\Swiss Setup 1.0.0.exe"
if (Test-Path $swissInstallerExe) {
    Write-Host "Signing Swiss Tools Installer: $swissInstallerExe"
    Set-AuthenticodeSignature -FilePath $swissInstallerExe -Certificate $cert
}

Write-Host "Signing operations completed successfully! 🛡️"
Stop-Transcript
