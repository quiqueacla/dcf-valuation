# Genera un fichero PEM con los certificados raíz e intermedios del almacén de Windows.
#
# Para redes con inspección TLS (p. ej. Netskope o Zscaler): la CA corporativa que firma
# el tráfico está instalada en Windows, pero uv y curl_cffi (usado por yfinance) no leen
# ese almacén. Con este fichero en SSL_CERT_FILE (uv) y CURL_CA_BUNDLE (yfinance) los dos
# confían en las mismas CA que el navegador.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\windows_ca_bundle.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\windows_ca_bundle.ps1 -SetUserEnv
#
# -SetUserEnv guarda además SSL_CERT_FILE y CURL_CA_BUNDLE como variables de usuario
# (persistentes; abre una terminal nueva para que surtan efecto). Sin él, solo se ponen
# en la sesión actual si se ejecuta con ". .\scripts\windows_ca_bundle.ps1".
# Vuelve a ejecutarlo si cambia la CA corporativa.

param(
    [string]$OutFile = (Join-Path $HOME ".certs\ca_windows.pem"),
    [switch]$SetUserEnv
)

$ErrorActionPreference = "Stop"

# Raíces del equipo y del usuario e intermedias del equipo, sin duplicados.
$certs = Get-ChildItem Cert:\LocalMachine\Root, Cert:\CurrentUser\Root, Cert:\LocalMachine\CA |
    Sort-Object Thumbprint -Unique

$pem = [System.Text.StringBuilder]::new()
foreach ($cert in $certs) {
    [void]$pem.AppendLine("-----BEGIN CERTIFICATE-----")
    [void]$pem.AppendLine([Convert]::ToBase64String($cert.RawData, "InsertLineBreaks"))
    [void]$pem.AppendLine("-----END CERTIFICATE-----")
}

New-Item -ItemType Directory -Force (Split-Path $OutFile) | Out-Null
[IO.File]::WriteAllText($OutFile, $pem.ToString(), [Text.Encoding]::ASCII)
Write-Host "Guardados $($certs.Count) certificados en $OutFile"

$env:SSL_CERT_FILE = $OutFile
$env:CURL_CA_BUNDLE = $OutFile
if ($SetUserEnv) {
    [Environment]::SetEnvironmentVariable("SSL_CERT_FILE", $OutFile, "User")
    [Environment]::SetEnvironmentVariable("CURL_CA_BUNDLE", $OutFile, "User")
    Write-Host "SSL_CERT_FILE y CURL_CA_BUNDLE guardadas como variables de usuario."
}
