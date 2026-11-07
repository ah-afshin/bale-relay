param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Identify','Register')][string]$Action,
    [string]$Origin
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$settings = @{}
foreach ($line in Get-Content -LiteralPath (Join-Path $projectRoot '.env')) {
    if ($line -match '^\s*(BALE_TOKEN|WEBHOOK_SECRET)\s*=\s*(.*?)\s*$') {
        $value = $Matches[2]
        if ($value.Length -ge 2 -and (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"')))) {
            $value = $value.Substring(1,$value.Length-2)
        }
        $settings[$Matches[1]] = $value
    }
}
if (-not $settings['BALE_TOKEN']) { throw 'BALE_TOKEN is missing from .env' }
$base = 'https://tapi.bale.ai/bot' + $settings['BALE_TOKEN']
function Invoke-Bale([string]$Method,[hashtable]$Body) {
    try {
        $reply = Invoke-RestMethod -Method Post -Uri ($base+'/'+$Method) -Body $Body -TimeoutSec 40
        if (-not $reply.ok) { throw 'API rejected request' }
        return $reply.result
    } catch { throw 'Bale request failed. Check the token and network; credentials have not been printed.' }
}
if ($Action -eq 'Identify') {
    $info = Invoke-Bale 'getWebhookInfo' @{}
    if ($info.url) { throw 'A webhook already exists. Identify your account before registering the webhook.' }
    $marker = 'setup-' + [guid]::NewGuid().ToString('N').Substring(0,12)
    Write-Host ('Send this exact text to your bot in a private Bale chat: ' + $marker)
    Read-Host 'After sending it, press Enter' | Out-Null
    $updates = Invoke-Bale 'getUpdates' @{timeout=10;limit=100}
    $found = $false
    foreach ($update in $updates) {
        if ($update.message.chat.type -eq 'private' -and $update.message.text -ceq $marker -and $update.message.from.id -eq $update.message.chat.id) {
            Write-Output ('Your Bale user ID: ' + $update.message.from.id)
            $found = $true
        }
    }
    if (-not $found) { throw 'The matching private message was not found. Run Identify again.' }
} else {
    if ($Origin -notmatch '^https://[A-Za-z0-9.-]+/?$') { throw 'Provide an HTTPS origin with no path or query.' }
    $secret = $settings['WEBHOOK_SECRET']
    if (-not $secret -or $secret.Length -lt 32) { throw 'WEBHOOK_SECRET is missing or too short.' }
    Invoke-Bale 'setWebhook' @{url=$Origin.TrimEnd('/')+'/webhooks/bale/'+$secret} | Out-Null
    Write-Output 'Webhook registered. The secret URL has not been printed.'
}
