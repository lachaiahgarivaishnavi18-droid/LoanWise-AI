param([Parameter(Mandatory=$true)][string]$PgBin,[int]$Port=55432)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$resolvedBin=(Resolve-Path -LiteralPath $PgBin).Path
$pythonPath=Join-Path $projectRoot '.venv\Scripts\python.exe'
$testRoot=Join-Path $projectRoot ('runtime\postgres-tests\'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$cluster=Join-Path $testRoot 'cluster'
$password=[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
$passwordFile=Join-Path $testRoot 'bootstrap-password'
[IO.File]::WriteAllText($passwordFile,$password)
$names=@('DATABASE_URL','LOANWISE_TEST_DATABASE_URL','LOANWISE_LEGACY_DATABASE_URL','PGPASSWORD','RUNTIME_DIR','DATA_DIR','MODEL_DIR','DEMO_MODE')
$previous=@{}
foreach($name in $names){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
$started=$false
try {
    & (Join-Path $resolvedBin 'initdb.exe') -D $cluster -U loanwise_test --pwfile=$passwordFile --auth=scram-sha-256 --no-locale --encoding=UTF8
    if($LASTEXITCODE -ne 0){throw 'PostgreSQL initialization failed'}
    Remove-Item -LiteralPath $passwordFile
    & (Join-Path $resolvedBin 'pg_ctl.exe') -D $cluster -l (Join-Path $testRoot 'postgres.log') -o "-h 127.0.0.1 -p $Port -c shared_buffers=32MB -c max_connections=30" -w -t 30 start
    if($LASTEXITCODE -ne 0){throw 'PostgreSQL startup failed'}
    $started=$true
    $env:PGPASSWORD=$password
    foreach($database in @('loanwise_integration','loanwise_pytest','loanwise_legacy')){
        & (Join-Path $resolvedBin 'createdb.exe') -h 127.0.0.1 -p $Port -U loanwise_test $database
        if($LASTEXITCODE -ne 0){throw 'Test database creation failed'}
    }
    $prefix="postgresql+psycopg://loanwise_test:${password}@127.0.0.1:${Port}/"
    $env:DATABASE_URL=$prefix+'loanwise_integration'
    $env:DEMO_MODE='false'
    $env:RUNTIME_DIR=Join-Path $testRoot 'runtime'
    $env:DATA_DIR=Join-Path $testRoot 'data'
    $env:MODEL_DIR=Join-Path $testRoot 'models'
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        & $pythonPath -m alembic upgrade head
        if($LASTEXITCODE -ne 0){throw 'PostgreSQL migration failed'}
        & $pythonPath -m app.cli seed
        if($LASTEXITCODE -ne 0){throw 'PostgreSQL demo seed failed'}
        $env:DATABASE_URL=$prefix+'loanwise_pytest'
        & $pythonPath -m alembic upgrade head
        if($LASTEXITCODE -ne 0){throw 'PostgreSQL test schema migration failed'}
        $env:LOANWISE_TEST_DATABASE_URL=$env:DATABASE_URL
        $env:LOANWISE_LEGACY_DATABASE_URL=$prefix+'loanwise_legacy'
        & $pythonPath -m pytest -q
        if($LASTEXITCODE -ne 0){throw 'PostgreSQL integration tests failed'}
    } finally {Pop-Location}
    $version=& (Join-Path $resolvedBin 'postgres.exe') --version
    $result=@{postgres_version=$version;passed=$true;port=$Port;timestamp=[DateTime]::UtcNow.ToString('o')}
    $result | ConvertTo-Json | Set-Content (Join-Path $testRoot 'result.json')
    $verification=Join-Path $projectRoot 'runtime\verification'
    New-Item -ItemType Directory -Path $verification -Force | Out-Null
    $result | ConvertTo-Json | Set-Content (Join-Path $verification 'postgres.json')
    Write-Output "PostgreSQL integration passed. Report: $testRoot\result.json"
} finally {
    if($started){& (Join-Path $resolvedBin 'pg_ctl.exe') -D $cluster -m fast -w stop}
    if(Test-Path -LiteralPath $passwordFile){Remove-Item -LiteralPath $passwordFile}
    foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
}
