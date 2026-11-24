# Adds or removes the GALO folder from the user's PATH (used by the GALO installer).
# The registry value is read without expanding %VARIABLES%, so the rest of the PATH stays intact.
param(
    [ValidateSet('adicionar', 'remover')][string]$Acao,
    [string]$Pasta
)
$chave = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
$atual = $chave.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
$partes = @()
if ($atual) { $partes = @($atual -split ';' | Where-Object { $_ -ne '' }) }
$partes = @($partes | Where-Object { $_.TrimEnd('\') -ine $Pasta.TrimEnd('\') })
if ($Acao -eq 'adicionar') { $partes += $Pasta }
if ($partes.Count -gt 0) {
    $chave.SetValue('Path', ($partes -join ';'), [Microsoft.Win32.RegistryValueKind]::ExpandString)
} else {
    $chave.DeleteValue('Path', $false)
}
$chave.Close()
# Tell open programs that the environment changed (WM_SETTINGCHANGE), without logging off.
[Environment]::SetEnvironmentVariable('GALO_ATUALIZAR_AMBIENTE', '1', 'User')
[Environment]::SetEnvironmentVariable('GALO_ATUALIZAR_AMBIENTE', $null, 'User')
