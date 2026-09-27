# Exports portfolio.pptx to portfolio.pdf and one PNG per slide (preview/) with PowerPoint.
# Usage (from anywhere):  powershell -NoProfile -File D:\hynix_hackathon\portfolio\export_pdf.ps1
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pptx = Join-Path $dir "portfolio.pptx"
$pdf = Join-Path $dir "portfolio.pdf"
$preview = Join-Path $dir "preview"
New-Item -ItemType Directory -Force $preview | Out-Null
Get-ChildItem $preview -Filter "slide-*.png" | Remove-Item -Force

$app = New-Object -ComObject PowerPoint.Application
try {
    $pres = $app.Presentations.Open($pptx, $true, $false, $false)   # ReadOnly, Untitled, WithWindow
    $pres.SaveAs($pdf, 32)                                          # ppSaveAsPDF
    for ($i = 1; $i -le $pres.Slides.Count; $i++) {
        $pres.Slides.Item($i).Export((Join-Path $preview ("slide-{0}.png" -f $i)), "PNG", 2000, 1125)
    }
    "slides: $($pres.Slides.Count)"
    $pres.Close()
} finally {
    $app.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($app) | Out-Null
}
Get-Item $pdf | Select-Object Name, Length, LastWriteTime
