# Emulator ASG transport result

The normal signed guide V35 APK and original-quality bundle25 were retained.
Only this AVD's graphics transport changed from `pipe` to `asg`; GPU host,
4 cores, 4096MiB RAM, 1280x720 at120Hz and30G userdata were preserved.
Both Android boot transport properties report `asg`; the app owns an open
`/dev/goldfish_address_space` descriptor.

| All Songs idle35s | Average FPS | 1% low FPS |
| --- | ---: | ---: |
| Normal V35, pipe A2 | 26.90 | 18.63 |
| Same normal V35, ASG | 53.35 | 31.75 |

Both captures use actual presentation timestamps, trim prehistory, retain
rolling-snapshot overlap and have zero CLI requests inside their idle windows.
Chart, difficulty, All membership, query, sort/group/reverse, partner, replay
and all exposed settings match. The average increased98.3%, 1%low70.5%.
These are short emulator measurements, not physical-device or120FPS acceptance.

GL-thread CPU sampling placed87.12% of old samples in `goldfish_pipe_read_write`.
With ASG,69.32% are in `goldfish_address_space`; pipe falls below1%. This supports
the changed transport path. It does not assign every GL call or remove all
graphics overhead.

Native song reveal, Mod/Variety roundtrips and the existing navigation/play path
passed. Full screenshots retain the expected art/text. Original audio, images,
APK and bundle bytes were not converted.

The maximum navigation/loading presentation gap remains2733.65ms (old2776.22ms).
Synchronous scene construction remains open; no file cache, worker or renderer
port was accepted. A finite MainMenu-init versus CSB timing proposal is retained
outside the repository, unbuilt. Culling experiment APKs are not active.

The existing portable launcher retains the AVD configuration and requires no new
argument. A small original-config backup and operator rollback receipt are kept
with the workspace and build evidence. Rollback: gracefully stop this AVD,
restore its original config.ini, restart the same AVD without wiping userdata.

The user deferred Vulkan and ANGLE until the current menu/loading work is done.
