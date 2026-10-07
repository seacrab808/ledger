# Read-only probe. Do not record usernames, computer names, addresses or SSH config.
param([string]$OutputPath = 'records/windows-host.json')
$ErrorActionPreference = 'Stop'
$taskOs = Get-CimInstance Win32_OperatingSystem
$taskSystem = Get-CimInstance Win32_ComputerSystem
$taskCpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$taskDrive = Get-PSDrive -Name C
$taskPage = @(Get-CimInstance Win32_PageFileUsage)
$taskRecord = [ordered]@{
    captured_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    system = 'Windows'
    caption = $taskOs.Caption
    version = $taskOs.Version
    build = $taskOs.BuildNumber
    cpu_model = $taskCpu.Name
    physical_cores = $taskCpu.NumberOfCores
    logical_cpus = $taskCpu.NumberOfLogicalProcessors
    total_physical_memory_bytes = [long]$taskSystem.TotalPhysicalMemory
    os_visible_memory_bytes = [long]$taskOs.TotalVisibleMemorySize * 1024
    available_memory_bytes = [long]$taskOs.FreePhysicalMemory * 1024
    hypervisor_present = $taskSystem.HypervisorPresent
    virtualization_firmware_enabled = $taskCpu.VirtualizationFirmwareEnabled
    slat_reported = $taskCpu.SecondLevelAddressTranslationExtensions
    vm_monitor_extensions_reported = $taskCpu.VMMonitorModeExtensions
    pagefile_allocated_mib = ($taskPage | Measure-Object AllocatedBaseSize -Sum).Sum
    pagefile_current_usage_mib = ($taskPage | Measure-Object CurrentUsage -Sum).Sum
    pagefile_peak_usage_mib = ($taskPage | Measure-Object PeakUsage -Sum).Sum
    disk_free_bytes = [long]$taskDrive.Free
    disk_total_bytes = [long]$taskDrive.Free + [long]$taskDrive.Used
    tools_present = [ordered]@{}
    gate = @{ eligible = $false; blockers = @('Native Windows is not the supported Linux/KVM FEMU host') }
    interpretation = 'Point-in-time host observation, not FEMU runtime measurement. Hypervisor can mask CPU feature reporting; pagefile allocation is not proof of active paging.'
}
foreach ($taskName in @('wsl','ssh','git','python','node','gh')) {
    $taskRecord.tools_present[$taskName] = [bool](Get-Command $taskName -ErrorAction SilentlyContinue)
}
$taskAbsolute = [System.IO.Path]::GetFullPath($OutputPath)
[System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($taskAbsolute)) | Out-Null
[System.IO.File]::WriteAllText($taskAbsolute,($taskRecord | ConvertTo-Json -Depth 8),[System.Text.UTF8Encoding]::new($false))
Write-Output "Host snapshot saved: $OutputPath"
