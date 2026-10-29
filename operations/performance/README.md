# Bounded emulator performance capture

These operator wrappers reuse the existing workspace SurfaceFlinger collector
and analyzer, pinned by SHA-256. They do not patch or install an APK. Set
`AKAINE_WORKSPACE` to the existing Akaine workspace containing the historical
`work/emu-finish-20261025/capture_long.py` and
`work/perf-20261023/analyze_frames.py` files. The matching CLI hosts and portable
ADB remain at the explicit operator paths in the script. Raw output stays on D:.

Prepare actual native gameplay first, with the exact controls asserted by the
wrapper. Run only one emulator. Use a fresh label; existing evidence is rejected.

```powershell
$env:AKAINE_WORKSPACE = "<existing-Akaine-workspace>"
python operations/performance/measure_fps.py v34 high V34_FRESH_HIGH30
python operations/performance/measure_fps.py prod high PROD_FRESH_HIGH30
```

Use `cap60` only when the native setting is actually off. The wrapper measures
30 seconds with no CLI/audio/screenshot requests inside the collection window,
then rejects a changed gameplay session or missing rolling frame coverage. It
does not prove exact chart-time alignment or a cause for stalls.

`measure_menu.py v34` / `measure_menu.py prod` assumes Song Select and measures
native reverse/query/reset confirmation in Base and All Songs. Existing output
folders are rejected. Host latency includes ADB and state observation. Each
operation uses a new Client because the legacy prod host's deadline is scoped
to Client lifetime. This is a measurement adapter, not a change to that APK.

The workspace scripts used for the actual 2026-10-25 measurement are referenced
by hash in the report. These versioned copies differ only by requiring the
workspace root through the environment and removing an unused menu import.
