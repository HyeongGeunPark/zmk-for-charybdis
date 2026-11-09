# dbgrec v3: always-on flight recorder for the Charybdis dongle split

**Update 2026-11-09.** This spec and the dbgrec work live only on the `debug/dbgrec` branch, which replaces the single-branch strategy described below (my-keymap). my-keymap has also moved its ZMK pin from 9ebbeff to 4dd95d7, which already contains the stage-4 `_fix3110` candidate (ZMK 5b51501). Re-baseline the pinned SHAs before the next stage.

**Status.** Final design (v3.1) and implementation reference. It supersedes v2. v3.1 applies a second verification pass; the list is at the end of this document. It is built in stages (§2). Each stage is small, is useful on its own, ends with a hardware check (§16) and has an explicit stop and decision rule.

**Basis.** v2 was verified line by line against the pinned sources in seven areas: dongle GATT client, right-half TX, USB HID_1, crash/boot/flash, logging/build/CI, keymap/events, and PC side. It was also critiqued for MVP scope. v3 fixes, replaces or drops every refuted or partial claim. §1 lists the facts that forced changes. Staging follows the MVP critique: a safety net and host capture come first, then a small dongle recorder, then a minimal right recorder. The deeper machinery moved to later, optional stages.

**Notation.**
- **[V file:line]**: verified in the pinned sources, by the v2 verifiers or rechecked for v3.
- **[A-nn]**: assumption still to verify. §20 gives its status and method.
- **[E]**: estimate, to be replaced by a CI or hardware number.
- Paths: ZMK = zmk/app @9ebbeff; ZEP = Zephyr fork 10ba6d0, the head of the floating branch `v4.1.0+zmk-fixes` that CI fetched on 2026-10-01 [prod log:475-478]. ZMK pins Zephyr by branch with `clone-depth: 1` [V ZMK app/west.yml:8-11], so a later build may use a later commit; `west-list.txt` records the actual one. DRV = zmk-pmw3610-driver @44b4a76; CFG = config repo, branch my-keymap; PS = nRF52 Product Specification.

**Invariants.** No stage trades these away.
1. No cable to either half during capture. The halves stay wireless on battery.
2. ZMK Studio stays intact on the dongle: the CDC port (MI_00/COM33), keymap storage and the behavior list.
3. The privacy allowlist (§8.7).
4. The LL and system-workqueue safety rules (§15).
5. Pull-based retrieval. The PC pulls from the dongle, and device RAM rings cover any time the PC is absent.
6. A keyboard mark chord recorded on the dongle timeline, plus a PC hotkey.
7. An auto-started PC agent that survives sleep, hibernate, unplugging, dongle resets, Explorer restarts and its own crashes.
8. Automatic per-event reports.
9. Explicit loss accounting at every hop.
10. A fault becomes a recorded reset, never a permanent halt.

---

## 0. Summary

| Stage | Flash | Adds | Can tell apart |
|---|---|---|---|
| **1a** | nothing | Supervisor, rescue watcher and flash tool. Capture agent: Raw Input S6 in 100 ms bins, hotkey marks, one-click notes, power and session events. Automatic per-mark reports, `doctor`, `bundle`. Debug CI workflow: rescue images, host tests and the keymap check (debug builds start in 1b) | Host/OS vs device; diverted layer (wheel instead of x/y); production baseline |
| **1b** | dongle | Dongle recorder: S4/S5 input brackets in 100 ms bins. Health lane: sysworkq lateness, timer-ISR gap, queue high-water. Context: layers, USB, endpoint, links, profile. Per-second key counts and lost-key-event detection per half. Marks from two layer-gated combos. Recorded-reset crash capture. Stack watermarks. HID_1 vendor interface (3 × 128 B feature reports). Host rules | Dongle-internal stall/drop (C3), host/USB (C8), layer (C4), dongle reset/crash (C9/C10), link loss ≥4 s or right reset (C2-long / right C9), C7 context, C1 plausibility. The residual class "upstream silent" triggers stage 2 |
| **2** | right half (+ dongle rebuild) | Minimal right recorder: S0 ISR, S1/S2 notify timing, sysworkq lateness, MOTION-pin-stuck, posq/inq, att_pool. It sends one 20 B summary per active second plus composite anomaly records over its own encrypted service, after a per-connection handshake. Dongle gets a diag client | C1 vs C2 vs C5 vs C11; right resets and crashes |
| 2b | dongle | Shadow subscription S3 (exact S3−S4, lost-release proof), RSSI variant, CPI steps, ACL credits, verdict toast | Exact C3, C4 root cause, C6 timing |
| 3 | per item | Right pins/uploads, wrap pack, PMW3610 diag patch, WRN log counter, MPU-guard variant, HTML timelines | Decisive single-event proof |
| 4 | variants | Fix A/B: _fix3110, _q16, _wq4096, _llfix, _llstats, fast-rest | Which change lowers freezes per active hour |

**A marked freeze in stage 1b:**
1. The user holds POINTER and taps R+T.
2. The dongle writes a MARK into its event ring.
3. The agent sees STATUS.mark_count change at its next 1 Hz poll and shows a toast.
4. 60 s later, a subprocess writes `reports\mark-<n>.md/.html/.csv` with a classification and its evidence lines.

If the agent is not running, the dongle rings hold the data (events for days, bins for about 10 min of activity), and the report is written when the agent catches up.

No forks in any stage. Production firmware, `config/` and the production workflow are unchanged (optional `paths-ignore` excepted, §14).

---

## 1. Facts and traps established by verification

| # | Fact | Source | v3 consequence |
|---|---|---|---|
| F1 | ZMK's split-central subscriptions are effectively **VOLATILE**. `atomic_set(params->flags, BT_GATT_SUBSCRIBE_FLAG_NO_RESUB)` stores the integer 1, which is bit 0 = VOLATILE. They are removed at every disconnect without a CCC write and recreated after ZMK's rediscovery. The half keeps CCC=1 per bond, restored at every connect, so a CCC read never proves ZMK is subscribed. Copying the pattern as `atomic_set(flags, …VOLATILE)` would store 0 and make a subscription persistent | [V ZMK central.c:481; ZEP gatt.h:2116-2130; gatt.c:3426-3436, 3728-3754, 5929-5945] | Module always uses `atomic_set_bit`. ZMK liveness comes from the SENT flag (§10.1) |
| F2 | `bt_gatt_subscribe` skips the CCC write only if a *local* params entry with the same value_handle and value≥ exists. It prepends the new entry and sets SENT synchronously when it writes. `remove_subscriptions` clears SENT, removes VOLATILE entries and calls notify(NULL) | [V gatt.c:5496-5531, gatt_write_ccc ~5396, 3728-3754] | §10.1 |
| F3 | A right-half CCC for a bonded central is persisted and restored at reconnect. cfg_changed fires at encryption, before the dongle re-subscribes. A later same-value write fires neither cfg_changed nor a store. The client host drops notifications that match no params | [V gatt.c:2257-2271, 3320-3377, 5935-5951, 3665-3677; prod_right.config:225,227] | The right TLM pump arms only on a per-connection CMD HELLO (§9.3) |
| F4 | Windows sends every feature SET with the collection's FeatureReportByteLength, padded. Zephyr stalls any OUT control request with wLength > CONFIG_USB_REQUEST_BUFFER_SIZE (128) | [V usb_device.c:321-326; prod_dongle.config:746; HidD_SetFeature doc; hidapi windows/hid.c] | Every HID_1 report is exactly 128 B including the ID, so wLength = 128 and the USB Kconfig stays at production values (§8.3) |
| F5 | HID get/set_report run on `usbd_workq`: cooperative prio −1, 1024 B stack, shared with ZMK's HID_0 completion | [V usb_dc_nrfx.c:1210-1267,1923-1929; prod_dongle.config:692,744; ZMK usb_hid.c:33,197] | O(1) handlers, ≤114 B locked copy, static buffers, no logging |
| F6 | With exactly one CDC ACM instance, HID_1 becomes interface 3 with EP 0x84, and existing interfaces and endpoints do not move. If COUNT=2 but HID_1 is not registered, MI_03 enumerates broken and its report-descriptor GET stalls | [V hid/core.c:121-131,519-524,745-749; common-ram.ld:103-108; usb_descriptor.c:250-301,439-478] | Register unconditionally; BUILD_ASSERT; CI gate "exactly one cdc-acm" |
| F7 | HCI commands from a low-priority thread with BT_BUF_CMD_TX_COUNT=1 can deadlock the dongle sysworkq: K_FOREVER command alloc, tx_work on the sysworkq, 10 s timeout, then BT_ASSERT | [V hci_core.c:87,309-317,435-438,2445-2453,4696-4719; buf.c:298-301; prod_dongle.config:51,68] | dbgrec never issues HCI commands. RSSI only via `ll_rssi_get` in a 2b variant |
| F8 | GPREGRET2 survives soft reset (sys_reboot) and CPU lockup. It is cleared by pin reset, watchdog, brownout and POR. sys_reboot does not write GPREGRET in this tree (NRF_STORE_REBOOT_TYPE_GPREGRET is a dead symbol). The bootloader never touches GPREGRET2 | [PS reset table; V ZMK Kconfig:54-61; scb.c:38-43; Adafruit main.c] | The flash crash slot is authoritative and GPREGRET2 is a hint. Pressing reset clears the safe-level counter |
| F9 | RESETREAS accumulates until the app clears it. 0 after an app clear means POR/brownout. hwinfo maps VBUS wake to RESET_POR. The errata-136 workaround clears other flags when RESETPIN is set | [V hwinfo_nrf.c:137-141,194-201; system_nrf52.c] | Store the raw register, then clear it |
| F10 | If `k_sys_fatal_error_handler` returns, the faulting thread is aborted and the system continues. LL_ASSERT continues after `bt_ctlr_assert_handle` returns, and that handler runs in any controller context (LLL ISR prio 0, ULL, thread). `nrfx_nvmc_words_write` guards the address only with NRFX_ASSERT, which is compiled out | [V fatal.c:91,119-140; hal/debug.h:10-22; lll_central.c:250; lll.c:497-539] | Both handlers lock IRQs, validate the slot, use a re-entrancy latch and never return in any mode |
| F11 | Combos filter on the highest active layer **index**, and `zmk_keymap_highest_layer_active()` returns an index. Names and bindings are looked up by **id**. With LAYER_REORDERING=y, a Studio reorder or removal changes only the persisted index→id order | [V combo.c:150-169; keymap.c:169-173,196-210,238-272,339-422; prod_dongle.config:864] | Runtime index→id identity check (§7.8) |
| F12 | A behavior with no parameter metadata cannot be bound from Studio: -ENODEV, then INVALID_PARAMETERS | [V behavior.h:282-288; behavior.c:242-262; studio/keymap_subsystem.c:147-152] | Deliberate for dbg_mark; a CI grep forbids metadata |
| F13 | `behavior_dev` can be NULL for Studio-loaded bindings whose local ID has no device | [V keymap.c:908-922,950-958] | Compare device pointers through NULL-safe `zmk_behavior_get_binding()` [V behavior.c:37-41] |
| F14 | A snippet.yml appends only one EXTRA_CONF_FILE and one EXTRA_DTC_OVERLAY_FILE | [V snippet-schema.yml; snippets.py:51-77] | Separate `dbgrec-common` snippet |
| F15 | Container steps default to `sh -e` (dash): `${GITHUB_SHA::8}` fails and `\| tee` masks failures. `arm-zephyr-eabi-nm` is not on PATH. Matrix jobs cannot see each other | [V prod CI log] | bash defaults, pyelftools, post-matrix gate job (§14) |
| F16 | The dongle ELF always contains "keycode": ERR formats in hid_listener.c and event names | [V hid_listener.c:33,75; event_manager.h:46-49] | Stages 1–2 build without CONFIG_LOG. The stage-3 privacy scan matches exact DBG/INF formats |
| F17 | `connected` and `security_changed` callbacks run in the BT RX WQ (BT_RECV_WORKQ_BT=y). `disconnected` runs from deferred_work on the **system workqueue** | [V conn.c:1284-1312,1903-1930,2167-2230; hci_core.c:2146-2275; prod_dongle.config:234] | All conn callbacks are O(1) |
| F18 | A notify completion `func` fires when the ATT buffer is destroyed: at controller hand-off, or when flushed at disconnect. PDUs still in att->tx_queue get no callback | [V att.c:245-275,647-701; l2cap.c:261-274; conn.c:2167-2230] | Generation counter, at-least-once delivery up to hand-off (later loss = seq gap), host de-duplication |
| F19 | `zmk_position_state_changed.source` is the bonded-address slot index, not left/right. slot->conn is set at `bt_conn_le_create` | [V central.c:153-161,226-240,820] | Per-half classification by a compile-time position mask; slot→half learned at runtime |
| F20 | Background Raw Input mouse messages can be coalesced or capped (RAWMOUSE without MOUSE_MOVE_NOCOALESCE; ~125/s cap for background recipients since build 25272; this PC runs 10.0.26300) | [docs; measured device name on this PC] | Compare S4 `s4_dsum` with S6 Σ(\|dx\|+\|dy\|) only in bins where L1/L4/L5 are off (the only layers with input processors [CFG charybdis_dongle.overlay:51-66]), and S5 presence (s5_n>0) with S6 gaps. Never compare report counts |
| F21 | GetMessageTime is a wrapping 32-bit LONG while GetTickCount64 does not wrap, so v2's lag formula breaks after 24.9 days. WM_TIMER carries no lag | [measured on this PC] | §11.4 |
| F22 | This PC is a battery laptop (Lenovo 83JJ, hybrid i7-13650HX). It often stays awake for days, hibernates after 3 h on DC (cutting USB power), has Fast Startup on, and has its own keyboard and touchpad | [verifier, powercfg, event log] | Disk budget for 24 h awake; S4 tests; HighQoS |
| F23 | The v2 Task Scheduler XML parses to Priority 7 (BELOW_NORMAL) with no working directory, and RestartOnFailure does not cover kills | [in-memory parse on this PC] | Task Scheduler dropped (§11.1) |
| F24 | Raw Input stops while the session is locked or the secure desktop (UAC) is active, and when the endpoint is BLE | [docs; split-admin token] | H-RAW gated (§12.3 R4) |
| F25 | BT_ATT_TX_COUNT is 10 on the dongle and 3 on the halves. ZMK's discovery continuation allocates with K_NO_WAIT in BT RX and silently ends ("Discover complete") on failure | [V prod_dongle.config:55; prod_right.config:55; att.c:72-73,733-742,3948-3953; gatt.c:3829-3836; central.c:541-544] | At most one module ATT request outstanding on the whole dongle |
| F26 | A new GATT service on the right changes its DB hash. That causes one `bt/hash` settings write, synchronously inside settings_load() in main() (db_hash_commit → do_db_hash), at the first boot after flashing and again at the first boot after rollback. CF entries are rewritten only for peers that wrote Client Supported Features; none do here (ZMK and the Zephyr client never write it). sc_indicate stores nothing, because no bonded peer has an SC CCC entry and no link exists at boot | [V gatt.c:582-600,665-698,912-976,1339-1370,6372-6385; ZMK main.c:25-28; prod_right.config:188,192] | Listed in §6.6 |
| F27 | CONFIG_THREAD_NAME is off in production | [V prod configs] | Crash and stack records carry thread object addresses, which the PC resolves from the ELF |
| F28 | Device-name case differs by API: Raw Input `Col03`, SetupDi `col03`, PnP `COL03` | [measured] | Case-insensitive matching |
| F29 | Every board reports the same USB serial in its bootloader and in ZMK: `%08X%08X` of FICR DEVICEID[1], DEVICEID[0]. The halves also enumerate as 1D50:615E whenever they are cabled (ZMK builds usb.c whenever USB_DEVICE_STACK=y, the nRF52840 default). All three bootloaders are identical: USB 239A:00B3, INFO_UF2.TXT `Board-ID: nRF52840-nicenano`, FAT volume serial 0x00420042 | [V ZEP usb_descriptor.c:328-355, hwinfo_nrf.c:30-60; Adafruit usb_desc.c, boards/nice_nano/board.h, ghostfat.c; ZMK Kconfig:679-680, CMakeLists.txt:103, usb.c:81,91; prod_right.config:698-702; PnP history on this PC: 71FB7A39AFC7297C under both 1D50:615E and 239A:00B3] | The rescue watcher identifies boards by USB serial only (§11.3) |

---

## 2. Stages, exit criteria and decisions

### 2.1 Plan

| Stage | Precondition | Exit criterion | Next step by result |
|---|---|---|---|
| 1a | Agent installed; CI green | Rescue drill passed on production firmware **and** ≥3 days of baseline | If a marked freeze shows S6 continuous (pointer delivered), the report says "perception/app" and 1b still follows. Otherwise go to 1b |
| 1b | Rescue drill passed; dongle_dbg and rescue images from the same CI run | 3 classified marked freezes **or** 2 weeks | **upstream silent** → stage 2 (or the `_fix3110` right variant first, if right-hand typing preceded most onsets). **dongle-internal** → 2b (exact S3−S4) or stage-4 `_wq4096`/`_q16`. **host/USB** → direct-port A/B (Q14). **layer** → 2b keystate. **dongle reset** → symbolise the crash; stage-3 MPU variant if C10. **no anomaly** → app/perception |
| 2 | 1b verdicts say upstream; right rescue drill passed | 3 classified marked freezes or 2 weeks | Matching stage-3 item, or a stage-4 variant |
| 2b | Stage-2 client ran clean for about a week | Per question | — |
| 3, 4 | A named open question | Per item (§10) | — |

**Dongle recovery is one gesture.** Double-tap the dongle reset and the watcher restores production (§11.3; rescue is armed after a staged debug flash). The right half (stage 2) needs its rescue image staged, a cable and a double-tap of its reset. Never start a stage when 10 minutes of fallout is not affordable. The laptop's own keyboard and touchpad remain available as a fallback.

### 2.2 Observer-effect baseline and arms

- **Stage 1a** measures on production firmware: marks per active hour, S6 mid-motion gaps (≥150 ms) per active hour, counted only while the host gates hold (§12.2), and the S6 rate.
- Every later report header compares against that baseline.
- **Every stage** keeps some `mode off` days (§6.4). The user sets them with `py -m dbgrec ctl mode off` and returns with `ctl mode normal`.
- `flashlog.jsonl` labels every data row with the dongle and right builds (build_id and run) that were running, so rates are never pooled across firmware arms.

---

## 3. The user's day

| Moment | User does | System does |
|---|---|---|
| Once | `py -3.14 host\install_dbgrec.py` (dongle plugged in) | Copies the app, registers logon autostart, adopts the dongle's USB serial, starts the supervisor and agent, and runs `doctor` |
| Start of 1a | `py -m dbgrec rescue import <zip>` with the first CI bundle, then the rescue drill (§16 1a) | Archives the rescue images, ELF and symbols; stages nothing |
| Per stage | `py -m dbgrec flash <zip> dongle` (stage 2: `--target dongle_dbg2`, and `right` with a cable), then double-tap that board's reset | The watcher copies the staged UF2, archives ELF and symbols, and logs the flash. No settings_reset: pairings and Studio edits survive |
| Every day | Nothing | The agent pulls the dongle at 1 Hz and captures Raw Input. Device rings cover PC absence |
| Pointer freezes (from 1b) | Hold **POINTER** (left thumb) and tap **R+T** (left index). Keep POINTER held until both R and T are down (holding it until both are up is also fine). If SYMBOLS is stuck, use the right pinky on **`[`** (position 23) and **`'`** (position 35), the outer-column keys of the second and third rows. Do not use the POINTER key while SYMBOLS is stuck: there it sends RAlt, which toggles Hangul/English | Toast "마크 #12 기록됨 · Pointer 레이어 · 트랙볼 입력 0.84 s 전 중단" within about 1 s. The report follows about 60 s later |
| Optional | Tray → "마지막 마크 메모 ▸" (one click) | The note feeds the rules (C4, C5, C6) |
| Fallback mark (the only mark in 1a) | **Ctrl+Alt+Shift+M**: Ctrl = left pinky, Shift = right pinky, Alt = left thumb, M = right index. Configurable | HOSTMARK placed on the device timeline by the clock fit |
| Debug firmware misbehaves | Double-tap the dongle reset and touch nothing | The production-configured dongle image built in the same CI run as the staged debug image (same config SHA, Zephyr SHA and container digest, recorded in MANIFEST.json) is flashed back within about 20 s |

---

## 4. Architecture

### 4.1 Observation points S0–S6

The points are called "points", not "stages", so that "stage" always means a plan stage (1a, 1b, 2 …).

| Point | Where | Meaning | Observer | From stage |
|---|---|---|---|---|
| S0 | Right | PMW3610 MOTION ISR dispatch (one per burst-read cycle) | Second `gpio_add_callback` on P0.06 | 2 |
| S1 | Right | Input thread starts dispatching a sensor event | `dbgrec_in_a` input callback | 2 |
| S2 | Right | `bt_gatt_notify` returned | `split_input_handler_0_zz` input callback | 2 |
| S3 | Dongle | Notification arrived in BT RX | Shadow subscription | 2b |
| S4 | Dongle | Input thread, listener entry | `dbgrec_in_a` input callback | 1b |
| S5 | Dongle | Listener + processors + HID send done | `input_handler_0_zz` input callback | 1b |
| S6 | PC | Raw Input report from MI_02 Col03 | Agent `WM_INPUT` | 1a |

**Context lanes:**
- Dongle (1b): sysworkq lateness, timer-ISR gap, pevq/inq high-water, orphan-X, listener+HID duration, layers (ids), USB state, endpoint, profile open/connected (advertising implied), halves connected (scanning implied), per-second key counts per half, lost key events, battery.
- Right (2): ISR/S2 masks, notify duration, sysworkq lateness, pin-stuck, posq/inq, att_pool, keys per second.
- PC (1a): power, lock/desktop, loop lag.

### 4.2 Diagram

```
RIGHT HALF (stage 2)                      DONGLE (stage 1b; master clock)                    PC
PMW3610 IRQ P0.06 --2nd gpio cb--> S0     BT RX WQ: ZMK notify cb -> pevq(5)                 Raw Input WM_INPUT (S6)
sysworkq: burst read -> input_msgq(16)      [2b: shadow cb S3]                                hidden window, INPUTSINK
input thread: [dbgrec_in_a] S1            sysworkq -> input_msgq(16) -> input thread:          |
  split_input_handler_0 (notify)            [dbgrec_in_a] S4  input_handler_0  [.._zz] S5 --USB HID_0 MI_02-->
  [split_input_handler_0_zz] S2           tick 20 ms (always): lateness, cpu gap, q hwm     agent (pythonw, supervised)
tick 20 ms (active): pin, q hwm, probe    listeners: keys (counts, KEYX), USB, link, batt     device thread: HID_1 MI_03
RAM: 4 KB TX FIFO                         rings: E 16 KB (events), B 64 KB (bins)              STATUS 1 Hz, CHUNK pulls
flash: crash page                         flash: crash page (space 2)                          writer: day files (zstd later)
   | zzz_dbgrec_svc TLM notify (20 B, sysworkq, K_NO_WAIT, gated) after CMD HELLO              report subprocess (auto)
   +----------------------------> diag client (stage 2) relays into E/B ----HID_1 feature reports (128 B)--->
   <---- CMD write-w/o-rsp: HELLO, MODE, SELFTEST, REQ_CRASH ----
LEFT HALF: production in all stages (observed via its key events and LINK records).
MARK: combo -> dbg_mark (CENTRAL) -> MARK record -> STATUS mark_count -> agent toast.
```

### 4.3 Who stores what

| Board | Store | Leaves via | Covers |
|---|---|---|---|
| Dongle | E ring 16 KB (change-only events: days). B ring 64 KB (BINS: ~10 min of active time). Crash page | HID_1 feature reports | Agent absence: E for days, B for recent activity |
| Right (2) | 4 KB TX FIFO; crash page | `zzz_dbgrec_svc` notify | Disarmed/disconnected periods: ~3 min of active summaries |
| PC | `%LOCALAPPDATA%\dbgrec\` | local only | — |

---

## 5. Packaging and repository layout

### 5.1 Kinds of change

| Kind | Content | Loaded by |
|---|---|---|
| Module `dbgrec/` (own `dbgrec/zephyr/module.yml`, **not** at the repo root) | All recorder code | Debug workflow only: `-DZMK_EXTRA_MODULES=$GITHUB_WORKSPACE/dbgrec`. The production reusable workflow adds a module only when `zephyr/module.yml` is at the repo root [V build-user-config.yml:84-91] |
| Snippets | `dbgrec-common`, `dbgrec-dongle`, `dbgrec-right` | `-S` per snippet. `snippet_root: .` is honoured through ZMK_EXTRA_MODULES [V A-03]; fallback `-DSNIPPET_ROOT=$GITHUB_WORKSPACE/dbgrec` |
| Workflow-applied patches `dbgrec/patches/` | Stage 3b driver hooks; stage 4 cherry-picks | Debug workflow per matrix entry |
| `config/`, `build.yaml`, `.github/workflows/build.yml` | **Unchanged** (only optional exception: `paths-ignore`, §14) | — |

### 5.2 Layout

```
dbgrec/zephyr/module.yml          name: charybdis-dbgrec
                                  build: {cmake: ., kconfig: Kconfig, settings: {dts_root: ., snippet_root: .}}
dbgrec/CMakeLists.txt             if(CONFIG_DBGREC) zephyr_library()
                                    zephyr_library_include_directories(${APPLICATION_SOURCE_DIR}/include)   # ZMK headers are PRIVATE to app [V ZMK CMakeLists.txt:24]
                                    role sources (below)
                                    2b: ${ZEPHYR_BASE}/subsys/bluetooth/host (ACL credits). ll_rssi_get needs no include dir:
                                        client.c declares `uint8_t ll_rssi_get(uint16_t handle, uint8_t *const rssi);` itself.
                                        controller/include/ll.h has no #includes and would need <zephyr/kernel.h> and
                                        <zephyr/bluetooth/addr.h> first [V ll.h:8,213-232,260]
                                    3a: zephyr_ld_options(-Wl,--wrap=... -Wl,-y,__wrap_...)
dbgrec/Kconfig
dbgrec/dts/bindings/zmk,behavior-dbg-mark.yaml     include: zero_param.yaml
dbgrec/include/dbgrec/{rec.h,proto.h}              __packed wire structs + _Static_assert sizes/offsets
dbgrec/src/core.c           rings, bins, tick, probe work, dbgrec thread, mode, BOOT          (dongle 1b, right 2)
dbgrec/src/crash.c          fatal + LL-assert handlers, crash page, GPREGRET2, levels, selftests
dbgrec/src/stacks.c         watermarks (k_thread_foreach_unlocked)
dbgrec/src/hooks_input.c    input brackets; orphan-X (dongle)
dbgrec/src/keys.c           position listener: counts, KEYX, slot->half
dbgrec/src/conn.c           BT_CONN_CB_DEFINE
dbgrec/src/zmk_state.c      USB/endpoint/profile/battery listeners and polls (dongle)
dbgrec/src/markcfg.c        mark-configuration check (dongle)
dbgrec/src/usb_hid1.c       HID_1 (dongle)
dbgrec/src/behavior_dbg_mark.c (dongle)
dbgrec/src/client.c         diag client (dongle, stage 2) + shadow (2b)
dbgrec/src/svc_right.c      zzz_dbgrec_svc, handshake, TX pump (right, stage 2)
dbgrec/src/sensor_right.c   2nd gpio callback, pin watchdog (right, stage 2)
dbgrec/src/wrap/*.c         stage 3a
dbgrec/snippets/dbgrec-common/{snippet.yml,dbgrec-common.conf,dbgrec-common.overlay}
dbgrec/snippets/dbgrec-dongle/{snippet.yml,dbgrec-dongle.conf,dbgrec-dongle.overlay}
dbgrec/snippets/dbgrec-right/{snippet.yml,dbgrec-right.conf}
dbgrec/patches/...          stage 3b/4
dbgrec/ci/{gates_single.py,gates_compare.py,keymap_check.py,protected.txt}
dbgrec/build-dbg.yaml
.github/workflows/dbgrec.yml
host/dbgrec/...             Python package (supervisor, agent, decoder, rules, reports, rescue, tests)
host/install_dbgrec.py
host/README.ko.md           one-page playbook (§19.1)
```

**Snippet order** (dongle): `-S studio-rpc-usb-uart -S dbgrec-common -S dbgrec-dongle`. Right: `-S dbgrec-common -S dbgrec-right`.
- Snippets are applied in the order given [V ZEP scripts/snippets.py:147-148]. All their conf and overlay files come after the ZMK_CONFIG conf files and the keymap overlay [V ZMK boards/post_boards_shields.cmake:88; ZEP configuration_files.cmake:95-96, zephyr_get MERGE REVERSE], so the dbgrec `/combos` overlay merges after the keymap.
- The module is visible to snippet resolution because ZMK sets ZEPHYR_EXTRA_MODULES before find_package(Zephyr) [V ZMK CMakeLists.txt:6,9] and zephyr_module runs before snippets [V ZEP zephyr_default.cmake:95,100].

---

## 6. Firmware: common parts

### 6.1 Kconfig

`menuconfig DBGREC` (default n). Role symbols:
- `DBGREC_ROLE_DONGLE` = `ZMK_SPLIT_ROLE_CENTRAL`.
- `DBGREC_ROLE_RIGHT` = `!ZMK_SPLIT_ROLE_CENTRAL && $(dt_nodelabel_enabled,trackball)`.
- The left half has no code in any stage.

| Symbol | Default | Stage |
|---|---|---|
| `DBGREC_TICK_MS` | 20 | 1b |
| `DBGREC_ERING_KB` / `DBGREC_BRING_KB` | 16 / 64 (dongle) | 1b |
| `DBGREC_BINQ` | 32 closed bins | 1b |
| `DBGREC_THREAD_PRIO` / `_STACK` | 14 / 1280 dongle, 1024 right | 1b/2 |
| `DBGREC_EARLY_CRASH_S` | 30 | 1b |
| `DBGREC_HID1` | y on the dongle; `BUILD_ASSERT(IS_ENABLED(CONFIG_DBGREC_HID1) == (CONFIG_USB_HID_DEVICE_COUNT == 2))` | 1b |
| `DBGREC_CLIENT` | n in 1b; y from stage 2 (dongle) | 2 |
| `DBGREC_TXFIFO_KB` | 4 (right) | 2 |
| `DBGREC_ATT_POOL` | y (right); selects `NET_BUF_POOL_USAGE` | 2 |
| `DBGREC_SHADOW`, `DBGREC_CPI_STEP`, `DBGREC_ACL_CREDITS`, `DBGREC_RSSI` | n | 2b |
| `DBGREC_WRAP` / `DBGREC_LOGCOUNT` / `DBGREC_SENSOR_HOOKS` | n | 3 |
| `DBGREC_BUILD_ID` | hex, from CI | all |
| `DBGREC_BUILD_RUN` | int, `GITHUB_RUN_NUMBER*100+GITHUB_RUN_ATTEMPT`, from CI. Carried in BOOT and STATUS next to build_id | all |
| `DBGREC_VARIANT` | int | all |

`dbgrec-common.conf`:
```
CONFIG_DBGREC=y
CONFIG_BT_CTLR_ASSERT_HANDLER=y   # LL asserts call bt_ctlr_assert_handle()
CONFIG_INIT_STACKS=y              # watermarks; stacks are filled once at thread creation
CONFIG_THREAD_MONITOR=y           # k_thread_foreach_unlocked() for watermarks
# CONFIG_LOG stays unset in stages 1-2 (CI gate). Stage 3: see 10.10.
```
- `dbgrec-dongle.conf`: `CONFIG_USB_HID_DEVICE_COUNT=2` (production is 1 [V prod_dongle.config:734]), `CONFIG_DBGREC_HID1=y`. `CONFIG_USB_REQUEST_BUFFER_SIZE` stays 128 (§8.3).
- `dbgrec-right.conf` (stage 2): `CONFIG_DBGREC_ATT_POOL=y`.

**Deliberately unchanged.** CI compares these against the rescue build of the same role from the same CI run (§14):
- stack sizes: sysworkq 2048, input 1024, BT RX 2200, split notify 756, usbd_workq 1024;
- priorities;
- queues: pevq 5, input 16, posq 10;
- connection parameters (interval 6, latency 30, timeout 400), PHY, TX power;
- `BT_BUF_*`, `BT_ATT_TX_COUNT` (dongle 10, halves 3), `BT_BUF_CMD_TX_COUNT=1`;
- `USB_REQUEST_BUFFER_SIZE=128`, `USB_MAX_NUM_TRANSFERS`, all `USB_HID_*` except DEVICE_COUNT;
- `CONFIG_ASSERT` unset; FPU settings; PMW3610 Kconfig; ZMK init priorities.

A variant that changes one of these on purpose (`_wq4096`, `_q16`, the RSSI and MPU variants) lists the symbol in its `allow:` field (§14); nothing else may differ.

**Intentional observer deltas.** Every report header prints these:
- `INIT_STACKS`, `THREAD_MONITOR`, `BT_CTLR_ASSERT_HANDLER`;
- `USB_HID_DEVICE_COUNT=2` (dongle);
- `NET_BUF_POOL_USAGE` (right, stage 2);
- code partition 12 KB smaller;
- variant `BT_CTLR_CONN_RSSI` (2b only).

**Forbidden** (CI): `LOG` (stages 1–2), `LOG_MODE_IMMEDIATE`, any LOG backend, `SHELL`, `ASSERT`, `HW_STACK_PROTECTION` (except the stage-3 variant), `SYMTAB`, `ZMK_USB_LOGGING`, `INPUT_EVENT_DUMP`, `ENABLE_HID_INT_OUT_EP`, `USB_HID_BOOT_PROTOCOL`, `ZMK_USB_BOOT`, `USB_DEVICE_SOF`, `USB_DEVICE_INITIALIZE_AT_BOOT`, `BT_CTLR_CONN_RSSI` (except the RSSI variant). The global HID options would add an OUT endpoint to HID_0 or make HID_1 a boot interface [V hid/core.c:47-64,104-119].

### 6.2 Execution contexts and bounds

| Context | Board | dbgrec work | Bound |
|---|---|---|---|
| `k_timer` tick (system clock ISR) | dongle: always. right: while active | Expiry lateness = `(uint32_t)k_cycle_get_32() − (uint32_t)k_uptime_ticks()`. Inside an expiry function, uptime is the scheduled tick and the cycle counter is real RTC time; both are 32768 Hz [V kernel/timeout.c:66-85,240-251; nrf_rtc_timer.c:698-701]. Never use k_uptime_get() alone for lateness or for `t_submit` in ISR context. `k_msgq_num_used_get` of the queues (plain read [V kernel.h:4824-4829]). Right: `gpio_pin_get_dt` (one register read [V gpio_nrfx.c:244-251]). Submit the probe work if none is pending, else update the pending age. Every 5th tick: swap the bin accumulator under a spinlock and push it to the bin queue | ≤5 µs |
| GPIO ISR | right | `isr_cnt++`, last ISR time; start the tick if stopped | ≤1 µs; ≈5–10 µs once when it starts the tick |
| Input thread (prio 0) | both | Bracket updates | ≤3 µs per event, never blocks |
| BT RX WQ | dongle: `connected`/`security_changed` appends; stage 2: client GATT callbacks, TLM relay. right: CMD write handler (mailbox copy) | O(1) |
| System workqueue | dongle: probe work, position listener, ZMK listeners, `dbg_mark` pressed, `disconnected` callback. right: probe work, TX pump (K_NO_WAIT notify, ≤1 in flight), `dbgrec_tx_done`, position listener, `disconnected`. Both: the one-shot GPREGRET2 count clear at 60 s (§6.3) | O(1), never waits |
| usbd_workq (cooperative −1) | dongle: HID_1 get/set_report | ≤114 B locked copy, ≤6 µs |
| dbgrec thread (prio 14, preemptible) | Bins → BINS records; context polls; mark-config check; stack scans; selftests. Stage 2: client request issue and CMD writes (dongle); mailbox, crash replay, STACK_R (right) | May block only itself |
| Fatal / LL assert | both | §6.3 | Once, then reset |

**Ring append:** a spinlock (IRQs masked) around a ≤114 B copy, about 2 µs. dbgrec uses no logging and no UART/CDC output in stages 1–2; Studio's CDC ACM (MI_00) is unchanged from production.

### 6.3 Fault capture, boot and safety levels

**Partition** (`dbgrec-common.overlay`):
```dts
&code_partition { reg = <0x00026000 0x000C3000>; };   /* was 0xC6000; now ends at 0xE9000 */
&flash0 { partitions {
    dbgrec_partition: partition@e9000 { reg = <0x000E9000 0x00003000>; };
}; };
```
- 0xE9000 is the crash page: 64 slots × 64 B.
- 0xEA000–0xEBFFF is not used by any stage in v3 (v2 used it for ping-pong pages and a boot log). It is kept only so that a later need does not move the code partition, and with it the rescue/debug flash layout, a second time. Nothing writes there.
- `storage_partition` (0xEC000+0x8000: bonds, Studio keymap) is untouched (CI gate).
- `USE_DT_CODE_PARTITION=y` [V prod config] makes the linker enforce the smaller code partition. The images are ~200–300 KB of 780 KB.
- UF2 drag-and-drop with the upstream bootloader logic rewrites only image pages [A-13]. Data left by an earlier debug build is used only if magic and CRC are valid, and it is attributed to its own build_id. Serial or BLE DFU through adafruit-nrfutil is out of scope.

**GPREGRET2** (direct `NRF_POWER->GPREGRET2`, unused by ZMK and the bootloader [F8]):
- bits 3–0: consecutive early crashes (uptime <30 s), saturating at 15;
- bits 6–4: kind of the last crash (1 fatal, 2 LL assert, 3 selftest, 4 stack-check fault);
- bit 7: slot write started.

It survives sys_reboot and lockup. Pin reset, watchdog, brownout and POR clear it.

**Fault handlers.** `k_sys_fatal_error_handler(unsigned int reason, const struct arch_esf *esf)` and `bt_ctlr_assert_handle(char *file, uint32_t line)` [V hal/debug.h] share one path. The mode flag and the safety level never skip the reset.
1. `irq_lock()`. The assert handler does this first. The fatal path is already locked [V fatal.c:91,119].
2. Re-entrancy latch: if it is already set, go to step 6.
3. Write GPREGRET2 **first**: kind; count+1 if uptime <30 s, otherwise count = 0; bit 7 only when step 4 will write a slot.
4. Write a slot only if **all** of these hold:
   - level ≤ SAFE;
   - the boot code set the `slot_ready` magic;
   - the slot address lies in [FIXED_PARTITION_OFFSET(dbgrec_partition), +0x1000) and is 64-B aligned;
   - all 16 target words read 0xFFFFFFFF.

   Otherwise skip the write. A fault before `dbgrec_early` has run therefore cannot write anywhere (the MBR is safe).
5. Build the 64 B record (§8.5).
   - `esf` may be NULL: then PC/LR are 0 and the `no_esf` flag is set.
   - `reason == K_ERR_STACK_CHK_FAIL` or CFSR.MSTKERR sets `pc_untrusted`.
   - LL assert: pc = `__builtin_return_address(0)` (the assert site), plus the file pointer and line.

   Then `nrfx_nvmc_words_write(addr, rec, 15)`, then the CRC word last. That is ≈16 × 41 µs ≈ 0.7 ms. nrfx waits for READY before every word and restores REN [V nrfx_nvmc.c].
6. `sys_reboot(SYS_REBOOT_WARM)` → NVIC_SystemReset. Declared FUNC_NORETURN, followed by CODE_UNREACHABLE. The handler never halts and never returns.

**Boot.** `SYS_INIT(dbgrec_early, POST_KERNEL, 99)` runs before ZMK's `bt_enable` (APPLICATION 50) and before `settings_load` in main(), so flash operations take the direct, non-ticker path [V A-12].
1. Read raw `NRF_POWER->RESETREAS`, then `hwinfo_clear_reset_cause()` (writes all ones) [F9].
2. Read `g2 = GPREGRET2`; `count = g2 & 0xF`. Level: NORMAL (count ≤1), SAFE (2–4), INERT (≥5).
3. Unless INERT: scan the crash page for valid slots (magic + CRC) and the first erased slot.
   - If none is erased and the level is NORMAL, erase the page. This is an ≈85–90 ms CPU stall that delays bt_enable; there is no radio yet. Increment `crash_page_erases`; records the PC had not yet pulled are lost and counted.
   - Set `slot_ready`.
4. `boot_nonce = sys_rand32_get()` [A-53]. Append BOOT.
5. After 60 s of uptime, a one-shot `k_work_delayable` clears bits 3–0 and bit 7. It is scheduled at every level (NORMAL, SAFE, INERT) and needs no recorder state. The level stays as decided at boot until the next boot. STATUS byte 91 carries the live GPREGRET2 value (`gpregret2_now`).

| Level | Trigger | Recorder | Fault path |
|---|---|---|---|
| NORMAL | count ≤1 | Everything for the stage | GPREGRET2 + slot + reset |
| SAFE | 2–4 consecutive early crashes | HID_1 (STATUS and the crash-page space) only. No hooks, tick, listeners, client or boot-time erase | GPREGRET2 + slot (only into an already-erased slot) + reset |
| INERT | ≥5 | HID_1 STATUS only, so MI_03 is not broken [F6]. Nothing else initialised | GPREGRET2 + reset (no flash) |

**At SAFE and INERT.** Hooks are static registrations (INPUT_CALLBACK_DEFINE, ZMK_LISTENER, BT_CONN_CB_DEFINE), and the combos are compiled into combo.c from DT [V combo.c:100-101]. Each such callback (input callbacks, ZMK listeners, conn callbacks, dbg_mark) therefore checks the level first and returns. The mark combos still capture R/T and [/' at every level. dbg_mark then only increments STATUS `mark_count`, so the toast still works, and writes no MARK.

**Right half** (no HID_1). SAFE: only `zzz_dbgrec_svc`, the CMD handler, the handshake and the pump run, sending HELLO_R, BOOT_R and CRASH_R only (no tick, hooks, listeners or SUM_R). INERT: the static service stays registered; after HELLO the pump sends HELLO_R and BOOT_R only; no flash access, so no CRASH_R. BOOT_R.level reaches the PC through the dongle's relay (ring E), so the tray can show a right-half SAFE/INERT.

At every level the board resets instead of halting. Production halts on any fault [V fatal.c]; that is the intended difference. A single tap of reset clears GPREGRET2 and returns to NORMAL. A double tap enters the bootloader, and the rescue watcher restores production (§11.3).

### 6.4 Mode flag and selftests

**Mode** is `normal` or `off`: one atomic, set by CTRL MODE (§8.3).
- `off` turns measurement off: input brackets, tick, probe, key counting, bins, stack scans, the stage-2 client and the right summaries return at once.
- These stay on in `off`: BOOT, LINK, USB, BATT, MARK, MARKCFG and CFG records, crash capture, HID_1.
- It is used for observer A/B days.

**Selftests** (CTRL SELFTEST with magic 0xDB6C0DE5; CLI needs `--i-know`):

| Kind | Action |
|---|---|
| `oops` | `k_oops()` in the dbgrec thread |
| `llassert` | `bt_ctlr_assert_handle()` from a thread |
| `llassert_isr` | Same, from a one-shot `k_timer` expiry (ISR context) |
| `fault_isr` | Invalid read in a `k_timer` expiry |
| `early` | The next crash counts as early (two of them drill SAFE at the next boot) |
| `sysq150` | `k_busy_wait(150 ms)` in a sysworkq item (drills the health lane) |
| `reboot` | Plain reboot |

There is no stack-overflow selftest without an MPU guard, because it would corrupt memory.

### 6.5 Stack watermarks

- `k_thread_foreach_unlocked()` [V thread_monitor.c:64-85; it drops the monitor lock around each callback] plus `k_thread_stack_space_get()` (needs INIT_STACKS + THREAD_STACK_INFO [V thread.c:857-868; prod:704]).
- Run from the dbgrec thread only: every 10 min while active, and at each mark.
- Records carry the `k_thread` object address [F27]. The PC resolves it with ELF symbols: `k_sys_work_q`, `bt_workq`, the input thread, ZMK's split notify queue, `usbd_workq`.
- CI grep: no locked `k_thread_foreach(` in module sources.

### 6.6 One-time flash writes caused by debug firmware

| Board | When | What | Path |
|---|---|---|---|
| Dongle | First debug boot | ZMK behavior local-ID entry for `dbg_mark` | `settings_load` in main(), after bt_enable, ticker-synced [V behavior.c:346-370] |
| Dongle/right | Crash page full at boot | One 4 KB erase, pre-BT | §6.3 |
| Right | First debug boot, and first production boot after rollback | `bt/hash` (DB-hash change; CF only if a peer had written Client Supported Features, not expected) | Synchronously inside settings_load() in main() [F26] |
| Right | First TLM subscription | CCC entry for the TLM characteristic | Delayed CCC store on the sysworkq |

After rollback, the dongle's stale local-ID entry is skipped (-EINVAL) and is harmless [V behavior.c:332-340]. The right half's stale TLM CCC entry is skipped because its handle no longer exists [V gatt.c:5790-5800]. Reports expect an R-CPU/R-SYSQ gap at exactly these boots.

---

## 7. Dongle recorder (stage 1b)

### 7.1 Hook points

| Purpose | Symbol / API |
|---|---|
| S4 pre | `INPUT_CALLBACK_DEFINE_NAMED(DEVICE_DT_GET(DT_NODELABEL(trackball_split)), dbgrec_in_pre, NULL, dbgrec_in_a)`. `_input_callback__dbgrec_in_a` < `_input_callback__input_handler_0` [V input.h:139-155; input_listener.c:404] |
| S5 post | `INPUT_CALLBACK_DEFINE_NAMED(…, dbgrec_in_post, NULL, input_handler_0_zz)` |
| Queues | `extern struct k_msgq peripheral_event_msgq;` [V central.c:146], `extern struct k_msgq input_msgq;` [V input.c:16] |
| Slot lookup | `extern int peripheral_slot_index_for_conn(struct bt_conn *conn);` (non-static, no header) [V central.c:153-161] |
| Keys | `ZMK_LISTENER(dbgrec_keys, …)` + `ZMK_SUBSCRIPTION(dbgrec_keys, zmk_position_state_changed)`. Always returns BUBBLE |
| Other events | `zmk_usb_conn_state_changed`, `zmk_endpoint_changed`, `zmk_ble_active_profile_changed`, `zmk_peripheral_battery_state_changed` [V headers; built on the dongle] |
| Polls (each bin close) | `zmk_keymap_layer_state()` (ids), `zmk_usb_get_status()`, `zmk_endpoint_get_selected()`, `zmk_ble_active_profile_is_open()` / `_is_connected()` [V signatures] |
| Link | `BT_CONN_CB_DEFINE(dbgrec_conn) = {.connected, .disconnected, .le_param_updated, .security_changed}`. `bt_conn_get_info()` role: CENTRAL = half, PERIPHERAL = BLE host. `bt_conn_index()` is the connection tag |
| Mark | `BEHAVIOR_DT_INST_DEFINE(0, …, &dbg_mark_api)` with `{.locality = BEHAVIOR_LOCALITY_CENTRAL, .binding_pressed, .binding_released}` and nothing else |
| HID_1 | `SYS_INIT(dbgrec_hid1_init, APPLICATION, 90)` (before ZMK USB HID 95 and USB 96 [V]): `device_get_binding("HID_1")`, `usb_hid_register_device()`, `usb_hid_init()`. **Unconditional** at every level |
| Faults, boot, stacks | §6.3, §6.5 |

### 7.2 Tick and sysworkq probe

- A 20 ms `k_timer`, always on (the dongle is USB powered).
- Expiry lateness (`k_cycle_get_32() − k_uptime_ticks()` inside the expiry, §6.2) → `cpu_gap` (the timer ISR was blocked by higher-priority ISRs or IRQ locks).
- `inq_hwm` and `pevq_hwm` per bin. Sampling misses fills shorter than 20 ms; the lateness lane covers those.
- **Probe:** if none is pending, record `t_submit = k_cycle_get_32()` and `k_work_submit(&probe_work)`. If one is pending, its age `now − t_submit` feeds `sysq_late_max`, so a long block shows while it lasts. `probe_work` on the sysworkq computes `late = now − t_submit`.
- Every 5th tick the 100 ms bin closes.

### 7.3 S4/S5 brackets and orphan-X

**Pre (input thread):**
- In mode off, return at once.
- For REL events: `s4_n++`; `s4_dsum += |value|` (saturating); gap = now − last_s4 → `s4_gap_max`; store `t_pre`.
- **Orphan-X.** The driver sends Y with sync when both axes are non-zero, and X with sync when Y is 0 [V DRV pmw3610.c:491-503]. So a REL_X with sync=0 must be followed by REL_Y. Anything else increments `orphan_n`: a Y lost anywhere between the right half's driver and S4. Possible places: the right half's input_msgq (K_NO_WAIT; it fills while the right input thread is blocked in bt_gatt_notify) [V DRV pmw3610.c:496-503; ZEP input.c:47-63], a failed right notify, the dongle pevq [V central.c:338] or the dongle input_msgq [V input_split.c:69]. It counts as a dongle-side loss only when pevq_hwm = 5 or inq_hwm = 16 in the same or previous bin; otherwise it is an upstream loss. (KEYX, in contrast, is dongle-side only, because position notifications carry the full bitmap [V central.c:367-389].)

**Post:** on sync events, `s5_n++` and `lst_max = max(now − t_pre)`. A value ≥30 ms means an hid_sem timeout.

Cost: ≤3 µs per event. Timestamps are `k_cycle_get_32()` (30.5 µs ticks).

### 7.4 Key listener (sysworkq; positions never leave RAM)

**Half mask.** A compile-time mask from the matrix transform:
- left: 0–5, 12–17, 24–29, 36–41, 48–50, 53–54;
- right: 6–11, 18–23, 30–35, 42–47, 51–52, 55

[V CFG charybdis_layout.dtsi:83-90; charybdis_right.overlay:10-12 (col-offset 6; the left overlay has none)]. The CI keymap check reads both files and verifies it (§14).

**Counts:**
- presses per second per half (`keys_l`, `keys_r`);
- last key time per half, for MARK ages and the rules.

**slot→half learning.** The first key from source S gives `slot_half[S]`, emitted once per boot as an SRCMAP record. The agent persists the map and pushes it back after each dongle boot (CTRL SLOTMAP).

**Lost key events (KEYX).** Combo positions 16, 17, 23 and 35 are excluded. Per half, keep 64-bit `pressed` and `seen` sets:
- A press of a position already pressed means a **release was lost** earlier. That is what makes a key or layer stuck.
- A release of a position not pressed but `seen` in this epoch means a **press was lost** (typically a short tap). ZMK still raises the release, because its slot bitmap had the bit [V central.c:367-389]. Unlike v2's ≥300 ms desync rule, this catches short taps.
- A release of a never-seen position is benign: the key was held across a reconnect or a dongle boot.
- A half's `connected` callback (CENTRAL role only; BT RX WQ, preemptible prio 8, which the cooperative sysworkq can preempt) only does `atomic_inc(&key_epoch)`. The listener (sysworkq) clears `seen` when it observes a new epoch.
- Any CTRL MODE change clears both `pressed` and `seen`, because they are not maintained while mode is off.
- Each KEYX is an E record with the layer state, at most 1/s; the excess is counted in BINS.

**Listener position.** `.event_subscription` is collected unsorted in link order [V zmk-events.ld:13-15], and `app` is the first Zephyr library [V ZEP cmake/modules/kernel.cmake:218; CMakeLists.txt:1026-1030]. dbgrec_keys therefore runs after every ZMK listener: activity, combo, keymap [V ZMK CMakeLists.txt:28,70,77].
- It sees an event that combo.c captured exactly once, when combo.c releases or re-raises it [V combo.c:263-276,459-470].
- It never sees the key events of a fired mark combo (excluded positions).
- It never sees an event whose behavior returned <0 at the keymap [V keymap.c:735-751; event_manager.c:30-44], so KEYX can count one half of such a pair (e.g. a failing `&bt`).
- Placed before combo.c, dbgrec would see re-raised copies twice and report false KEYX. CI therefore fails the build unless the dbgrec `zmk_position_state_changed` entry follows `combo.c.obj` and `keymap.c.obj` in `zmk.map` (§14).

### 7.5 Link, USB, battery, profile

- **`connected`** (BT RX): a LINK conn record with {conn_idx, role, slot = `peripheral_slot_index_for_conn(conn)` (slot->conn is already set [F19]), half = `slot_half[slot]`}. Cached by conn_idx. Increments key_epoch (CENTRAL role only).
- **`security_changed`** (BT RX): LINK sec; stores `t_sec` for the stage-2 client gate.
- **`le_param_updated`**: LINK param.
- **`disconnected`** (sysworkq [F17]): LINK disc with the reason: 0x08 timeout, 0x13 remote user, 0x16 local host, 0x3E failed to establish.
- **USB record** on USB state, endpoint or profile change.
- **BATT** {slot, half, soc} when a half's SOC changes.

### 7.6 Rings and bins

- **E ring** (16 KB): change-only events. Holds days.
- **B ring** (64 KB): one BINS record (§8.4) per active second, ≈10 min of active time.
- **Space 2**: the crash page, a read-only flash view.
- Byte rings of variable-length records. u32 sequence per ring. An append drops the oldest records. A reader cursor that falls behind counts the records lost unread (STATUS `lost_total`, CHUNK `lost_before`).
- Closed bins pass through a 32-entry queue from the tick to the dbgrec thread. Overflow increments `bins_lost` (STATUS and a BINS flag).
- **Active second:** this or the previous 2 s had any S4 event, key event, S5 report, sysq_late ≥20 ms, cpu_gap ≥20 ms or context change. Idle seconds write nothing; continuous ring sequence numbers tell idle apart from lost.

### 7.7 Mark behavior and combos

```dts
/ {
    behaviors {
        dbg_mark: dbg_mark {
            compatible = "zmk,behavior-dbg-mark";
            #binding-cells = <0>;
            display-name = "DEBUG mark (do not bind)";
        };
    };
    combos {                                   /* the only zmk,combos node; keymap combos must also live in /combos */
        compatible = "zmk,combos";
        dbg_mark_ptr {                         /* combo index 0 */
            timeout-ms = <80>;
            key-positions = <16 17>;           /* R, T (left index) */
            layers = <2 4 5 6>;                /* layer INDEXES (7.8) */
            bindings = <&dbg_mark>;
        };
        dbg_mark_sym {                         /* combo index 1 */
            timeout-ms = <80>;
            key-positions = <23 35>;           /* right outer column, rows 1 and 2 counted from 0 ([ and ') */
            layers = <1>;
            bindings = <&dbg_mark>;
        };
    };
};
```

**Behavior definition:**
- The binding YAML has `include: zero_param.yaml`, which declares `#binding-cells` and `display-name` [V zero_param.yaml:4; behavior-metadata.yaml:5].
- **`dbg_mark_api` has no parameter metadata** (enforced by a CI grep). Studio therefore rejects binding it [F12], so it cannot be bound by mistake or become a dead key after rollback. Studio lists it as a zero-parameter behavior named "DEBUG mark (do not bind)" [V studio/behavior_subsystem.c:19-42,189-209; drivers/behavior.h:147-158]. Choosing it is rejected with -ENODEV [F12]. Harmless [A-37].
- `binding_pressed` (sysworkq, O(1)):
  - `mark_seq++`, MARK record, STATUS `mark_count` (at SAFE/INERT only `mark_count`, §6.3);
  - wake the dbgrec thread for a stack scan;
  - `src = event.position − ZMK_VIRTUAL_KEY_POSITION_COMBO(0)` [V combo.c:284]. combo.c orders combos by key-position count, then DT child order [V combo.c:79-101], so src is 0/1 only while `dbg_mark_ptr` and `dbg_mark_sym` are the first two children of `/combos` and no combo has a single key position (CI gate, §14).
- `binding_released` returns `ZMK_BEHAVIOR_OPAQUE`.

**Combo mechanics.** Combos are compiled on the central only [V ZMK CMakeLists.txt:48-70]. They filter on the highest active layer *index* [F11]. Effect on each layer (stock order):

| Layer | Effect |
|---|---|
| Base (0) | No combo active; no delay on R/T/[/' |
| SYMBOLS (1) | `dbg_mark_sym` active; 23/35 are `&none`, so a mistimed chord leaks nothing |
| POINTER (2) | `dbg_mark_ptr`; 16/17 are `&none` |
| DANGER (3) | Excluded on purpose (17 = `&bootloader`) |
| SCROLL / SNIPE (4/5) | `dbg_mark_ptr`. With POINTER held, 16/17 fall through to POINTER's `&none`. **With SCROLL/SNIPE stuck and POINTER not held**, they fall through to base R/T: R and T are held back up to 80 ms, and a fast "rt"/"tr" fires a mark and swallows both letters. This happens only while that layer is stuck, which is itself a C4 freeze |
| EXTRA (6) | `dbg_mark_ptr`; `&none` |

**Early-POINTER-release leak.** If POINTER is released after R goes down but before T goes down, combo.c handles the POINTER key-up before the keymap does. It releases the captured R press first, so R still resolves to POINTER's `&none` [V combo.c:263-270,396-404,459-473; ZMK CMakeLists.txt:70,77]. The T pressed afterwards is evaluated on Base, where no combo is active, and types "t". User rule: keep POINTER held until both R and T are down (holding it until both are up is also fine).

### 7.8 Mark-configuration check

Runs in the dbgrec thread at boot+5 s and every 60 s, because Studio edits apply live.

1. **index→id identity.** `zmk_keymap_layer_index_to_id(i) == i` for i ∈ {0, 1, 2, 4, 5, 6} [V keymap.h:43]. A Studio reorder or removal is persisted as `keymap/layer_order` and silently retargets the index-based combos [F11].
2. **Bindings by id, as device pointers.** Use `zmk_behavior_get_binding(b->behavior_dev)` (NULL-safe [F13]). A NULL binding or NULL `behavior_dev` counts as a mismatch and is never dereferenced.
   - ids 2 and 6 at positions 16/17 → `DEVICE_DT_GET(DT_NODELABEL(none))`;
   - ids 4 and 5 at 16/17 → `DEVICE_DT_GET(DT_NODELABEL(trans))` (device name "transparent");
   - id 1 at 23/35 → `none`.
3. **Output:** `mark_cfg_ok` and `fail_mask` in STATUS; a MARKCFG E record on change; tray yellow "마크 콤보 설정 불일치: Studio 레이어 순서/바인딩 확인".

Layer names are not checked, because renames do not affect combos.

### 7.9 HID_1

- **Enumeration.** With exactly one CDC ACM instance, HID_1 becomes interface 3 (MI_03) with EP 0x84, and MI_00/COM33 and MI_02 COL01–03 keep their numbers [F6; A-01 for the Windows side]. A second CDC instance would move it, so CI asserts exactly one `zephyr,cdc-acm-uart` node.
- **get_report** (usbd_workq [F5]):
  - type = `setup->wValue >> 8` must be 3 (feature); id = `wValue & 0xFF`;
  - lock, fill a static `__aligned(4)` 128 B buffer, unlock;
  - `*data = buf`, `*len = 128` (`*len` enters as 0 [V usb_device.c:317,337-347]); byte 0 = id (ZMK's own handler leaves it 0 [V hid.h:335-338]);
  - no other context touches the buffer until the next request.
- **set_report:**
  - accept `*len` ≤128 (Windows pads to 128); id = `data[0]`;
  - CTRL ops run O(1) inline (SEEK, MODE, SLOTMAP) or post to the dbgrec thread (SELFTEST, RIGHT_CMD);
  - results go to STATUS `last_ctrl_seq`/`last_ctrl_result`.
- **Restrictions in both callbacks:** no logging, no stack buffers >32 B, no ring scans. The mandatory interrupt IN endpoint is never written, so it cannot trigger a remote wakeup [V core.c:692-705].

---

## 8. Records and the HID_1 protocol

All wire structs are `__packed` with fixed-width fields and `_Static_assert` sizes and offsets in `rec.h`. `host/dbgrec/schema.py` mirrors the constants, and CI compares the two (§14). Little-endian throughout.

### 8.1 Dongle ring record

Header 8 B, then payload. Total ≤114 B, so any record fits one CHUNK (`_Static_assert(REC_MAX ≤ CHUNK_DATA_MAX)`).

| off | size | field |
|---|---|---|
| 0 | 1 | `len` (8..114, including the header) |
| 1 | 1 | `type`: bits 7–6 source (0 dongle, 1 right relay, 2 left relay), bits 5–0 id |
| 2 | 2 | `seq16` (low 16 bits of the ring's u32 sequence) |
| 4 | 4 | `t_ms` (dongle uptime, low 32 bits; for relays, the arrival time) |

**Encoding `enc_ms8`** (one byte): v <128 → 2v ms (0–254); v ≥128 → 256 + (v−128)×16 ms (up to 2288). Shared by firmware and Python.

### 8.2 Dongle record types

| id | Ring | Name | Payload |
|---|---|---|---|
| 0x01 | E | BOOT | boot_nonce u32, resetreas_raw u32, gpregret2 u8, level u8, crash_valid u8, crash_free u8, crash_page_erases u8, schema u8, variant u8, build_id u32, build_run u32 = 23 |
| 0x06 | E | LINK | conn_idx u8, role u8, slot i8, half u8 (0 ?, 1 L, 2 R, 3 host), ev u8 (conn, disc, param, sec, fail), reason u8, interval u16, latency u16, timeout u16, sec u8 = 13 |
| 0x07 | E | MARK | mark_seq u16, src u8 (0 ptr combo, 1 sym combo, 7 selftest), layers u8 (ids 0–7), usb u8, halves_conn u8, s4_age_ms u16, r_key_age_ms u16, l_key_age_ms u16, sysq_late_2s enc u8, pevq_now u8, inq_now u8, agent_live u8 = 16 |
| 0x0A | E | USB | usb_status u8, endpoint u8, profile_idx u8, profile_open u8, profile_conn u8 |
| 0x0B | E | BATT | slot u8, half u8, soc u8 |
| 0x0D | E | STACK | n u8, then n × {thread u32, size u16, unused u16} (n ≤13) |
| 0x0E | E | CFG | ctrl_seq u16, op u8, arg u32, result i8 |
| 0x10 | E | KEYX | half u8, kind u8 (1 lost release, 2 lost press), layers u8, total u16 |
| 0x12 | E | MARKCFG | ok u8, fail_mask u8 |
| 0x13 | E | SRCMAP | slot u8, half u8 |
| 0x14 | B | BINS | §8.4 |
| 0x17 | E | AGENT | ev u8 (attach, detach), gap_s u32 |
| 0x18 | E | SELFTEST | kind u8 |
| 0x20 / 0x21 | E / B | RELAY_E / RELAY_S (stage 2) | conn_idx u8, half u8, raw half record ≤20 B |
| 0x22 | E | DIAG (stage 2) | conn_idx u8, half u8, step u8 (no_diag, discovered, subscribed, armed, live, no_hello, fail), err i16 |
| 0x30 | E | ZMKSUB (2b) | conn_idx u8, char u8, result u8 (order_ok, zmk_sub_missing, ccc_zero, fail) |
| 0x31 | B | SHADOW (2b) | per-second S3 counts, Σ\|d\|, pevq_pred_loss, bitmap state |

There is no LOST record type. Loss is explicit through CHUNK `lost_before`, STATUS `lost_total`, `bins_lost` and `crash_page_erases`.

### 8.3 HID_1: descriptor and reports

**Why 128 B.** Windows pads every feature SET to the collection's FeatureReportByteLength [F4]. All three reports are therefore 127 data bytes + ID = 128. Then FeatureReportByteLength = 128, wLength = 128, and 128 ≤ CONFIG_USB_REQUEST_BUFFER_SIZE (the check is `>` [V usb_device.c:321]). The USB stack configuration stays at production values.

```
0x06,0xDB,0xFF, 0x09,0x01, 0xA1,0x01,     // Usage Page 0xFFDB (vendor), Usage 1, Collection (Application)
  0x15,0x00, 0x26,0xFF,0x00, 0x75,0x08, 0x95,0x7F,   // 0..255, 8 bits, count 127
  0x85,0x01, 0x09,0x02, 0xB1,0x02,        // ID1 STATUS  (GET)
  0x85,0x02, 0x09,0x03, 0xB1,0x02,        // ID2 CTRL    (SET)
  0x85,0x03, 0x09,0x04, 0xB1,0x02,        // ID3 CHUNK   (GET)
0xC0
```
SET on ID1/ID3 and GET on ID2 return an error (stall).

**STATUS (ID1, 128 B):**

| off | field |
|---|---|
| 0 | id = 1 |
| 1 | magic "DBR3" (4) |
| 5 | schema u8 (3) |
| 6 | role u8 (1 = dongle) |
| 7 | level u8 (0 NORMAL, 1 SAFE, 2 INERT) |
| 8 | build_id u32 |
| 12 | variant u8 |
| 13 | mode u8 (0 off, 1 normal) |
| 14 | flags u16: usb_cfg, usb_susp, endpoint_usb, profile_open, profile_conn, mark_cfg_ok, agent_live, crash_new, client_on, r_diag_live, bins_lost_nz |
| 16 | boot_nonce u32 |
| 20 | resetreas_raw u32 (as read at this boot) |
| 24 | gpregret2_at_boot u8, crash_valid u8, crash_free u8, crash_page_erases u8 |
| 28 | uptime64_ms u64 (captured inside get_report) |
| 36 | cyc32 u32 |
| 40 | 3 × {head_seq u32, oldest_seq u32, read_seq u32} (spaces 0 E, 1 B, 2 crash) = 36 B |
| 76 | lost_total u32 |
| 80 | mark_count u16 |
| 82 | last_ctrl_seq u16 |
| 84 | last_ctrl_result i8 |
| 85 | layers u8 (ids) |
| 86 | halves_conn u8 |
| 87 | slot_half u8 (2 bits × 4 slots) |
| 88 | markcfg_fail u8, bins_lost u16 (sat), gpregret2_now u8 (live register value, §6.3) |
| 92 | r_boot_nonce u32 (stage 2) |
| 96 | r_relay_n u16, r_seq_gaps u16 (stage 2) |
| 100 | build_run u32 (§6.1) |
| 104 | reserved (24 B, zero) |

**CTRL (ID2, SET):** `[0]=2, [1] op, [2..3] ctrl_seq u16, [4..] args`, padded to 128 by Windows.

| op | Name | Args | Effect |
|---|---|---|---|
| 0x01 | SEEK | space u8, how u8 (0 oldest, 1 seq), seq u32 | O(1). `seq` is honoured only if it equals the space's current read cursor (no-op) or the start of the last returned chunk (retransmit). Anything else positions at oldest and sets `cursor_mismatch`. No ring scan ever runs in USB context |
| 0x02 | MODE | mode u8 | Sets the mode flag; CFG record |
| 0x03 | SELFTEST | kind u8, magic u32 | Posted to the dbgrec thread |
| 0x04 | SLOTMAP | slot_half[4] | RAM only |
| 0x05 | AGENT | agent_version u16 | Agent attach marker |
| 0x10 | RIGHT_CMD (stage 2) | op u8, args ≤17 | Forwarded to the right as CMD |

**CHUNK (ID3, GET, 128 B):**

| off | field |
|---|---|
| 0 | id = 3 |
| 1 | space u8 |
| 2 | n_rec u8 |
| 3 | flags u8: more, overrun, cursor_mismatch |
| 4 | first_seq u32 |
| 8 | lost_before u32 (records overwritten unread since the previous GET) |
| 12 | data_len u16 |
| 14 | records (≤114 B, whole records only) |

A GET returns the records from the space's read cursor and advances it. The echoed `first_seq` lets the agent detect a second reader. Space 2 returns one 64 B crash slot per GET (seq = slot index, erased slots skipped).

### 8.4 BINS record (B ring, one per active second)

Payload 100 B (record 108 B):

| off | field |
|---|---|
| 0 | first_bin u32 (uptime_ms/100 of bin 0) |
| 4 | keys_l u8, keys_r u8 (presses in this second) |
| 6 | cpu_gap_max enc u8 |
| 7 | orphan_n u8 |
| 8 | keyx_n u8 |
| 9 | flags u8: mode, endpoint_usb, profile_open, profile_conn, usb_cfg, agent_live, bins_lost, rsv |
| 10 | 10 × bin (9 B) |

**Bin (100 ms):**

| off | field |
|---|---|
| 0 | s4_n u8 (REL events at S4) |
| 1 | s4_dsum u16 (Σ\|dx\|+\|dy\|, saturating) |
| 3 | s4_gap_max enc u8 (largest gap ending at an event in this bin) |
| 4 | s5_n u8 (sync events = HID report attempts) |
| 5 | lst_max enc u8 (S5−S4 for sync events) |
| 6 | sysq_late_max enc u8 |
| 7 | q u8: inq_hwm:5 (0–16; 16 = input_msgq full, the K_NO_WAIT drop condition [prod_dongle.config:491; input_split.c:69]) \| pevq_hwm:3 (0–5). Orphans are counted per second in `orphan_n` (payload offset 7) |
| 8 | ctx u8: L1, L2, L4, L5, L6 (ids) \| halves_conn:2 \| usb_suspended:1 |

### 8.5 Crash slot (64 B, flash; same format on the right)

| off | field |
|---|---|
| 0 | magic u32 'DBC3' |
| 4 | build_id u32 |
| 8 | uptime_ms u32 |
| 12 | boot_nonce u32 |
| 16 | kind u8, reason u8, flags u8 (no_esf, pc_untrusted, in_isr, early, level:2), seq u8 |
| 20 | pc u32 (LL assert: call site) |
| 24 | lr u32 |
| 28 | xpsr u32 (LL assert: line) |
| 32 | sp u32 |
| 36 | cfsr u32 |
| 40 | hfsr u32 |
| 44 | fault_addr u32 (MMFAR or BFAR when valid) |
| 48 | thread u32 (`k_current_get()`) |
| 52 | stack_start u32 |
| 56 | aux u32 (LL assert: `file` pointer into flash; otherwise stack_size) |
| 60 | crc32 u32 (written last) |

**PC-side symbolisation** uses `symbols.json` from CI (pyelftools):
- Thumb FUNC addresses with bit 0 cleared; lr looked up with bit 0 cleared;
- `file` strings read from the ELF;
- thread objects resolved by symbol.

No on-device SYMTAB.

### 8.6 Time, sequences and loss accounting

**Clocks:**
- **Dongle uptime is the master timeline.** STATUS carries `uptime64` and `cyc32` captured inside get_report. The agent brackets each GET with QPC and fits a per-boot line using samples with RTT ≤1 ms (±0.3 ms [E]).
- **Right → dongle:** each relay is stamped with the dongle's arrival time and keeps the right's `t_ms`. The PC takes the lower envelope of (arrival − t_half) per 10 min with a linear drift fit (≤100 ppm), since records delayed by the gate sit above the envelope [A-27].
- **Wrap:** 64-bit anchors (STATUS uptime64, right HB_R/BOOT_R uptime_hi) remove the 49.7-day u32 wrap.

**Loss per hop:**

| Hop | Loss is visible as |
|---|---|
| Dongle rings | `lost_before` / `lost_total`; `bins_lost` |
| Crash page | `crash_page_erases` |
| Right FIFO | `tx_lost` in HB_R plus seq gaps (seq gaps also cover records lost in the controller at disconnect). Rare duplicates are removed by (boot_nonce of the latest HELLO_R, seq) |
| PC frames | Block CRC; a truncated last block is cut off at start and counted |
| Raw Input | Coalescing is not loss (§12) |
| Agent absence | AGENT records (gap_s) and the PC's own power records |

### 8.7 Privacy allowlist

**Recorded:**
- counters, durations, queue depths, \|d\| sums;
- link, USB, power, lock-state and radio context; reset causes; battery;
- layer ids (100 ms bits during active seconds);
- marks and notes;
- per-second key counts per half;
- lost-key-event counts (no positions);
- thread and code addresses in crash and stack records.

**Never recorded:** keycodes, positions, per-keystroke timestamps, HID report contents beyond pointer deltas, window titles, log text, BLE addresses.

Key sets live only transiently in dongle RAM. Exports (`bundle`) redact the boot nonce and the USB serial. Q11 asks the user to confirm the layer bits and the stage-2b CPI_STEP.

---

## 9. Stage 2: right recorder and dongle diag client

### 9.1 Right hooks

| Purpose | Symbol / API |
|---|---|
| S0 | `gpio_init_callback(&cb, dbgrec_motion_isr, BIT(irq.pin)); gpio_add_callback(irq.port, &cb);` with `irq = GPIO_DT_SPEC_GET(DT_NODELABEL(trackball), irq_gpios)` (P0.06 [V CFG overlay:60]). It is registered in `dbgrec_early` (POST_KERNEL 99), after the driver's `pmw3610_init` (POST_KERNEL 90) has added its callback. Because callbacks are prepended, it then runs **before** the driver's callback that disables the LEVEL interrupt. The order affects only the S0 timestamp; every matching callback is called either way [V gpio_utils.h:59-79,90-104; DRV pmw3610.c:509-515,543-545,685-686; prod_right.config:460]. GPIOTE runs at IRQ priority 5. It counts **dispatches = burst-read cycles**, not sensor samples (several samples merge into one dispatch). It never configures the pin |
| S1 | `INPUT_CALLBACK_DEFINE_NAMED(trackball, dbgrec_in_pre, NULL, dbgrec_in_a)`: after `activity_input_listener`, before `split_input_handler_0` [V] |
| S2 | `…_post, split_input_handler_0_zz`: notify duration = post − pre of the same event; `in_notify` flag and since-time; Σ\|d\|; jump = first REL after ≥100 ms idle |
| Tick | 20 ms while active: lateness, `input_msgq`/`position_state_msgq` high-water, MOTION pin (active with no new ISR → pin_stuck), sysworkq probe. Lateness as in §6.2. It starts on an ISR, key or command: write the activity time first, then `atomic_cas(&running, 0, 1)`, then `k_timer_start` (ISR-safe [V kernel/timer.c:139-179]). It stops only when all of these hold: 5 s with no ISR or key, MOTION inactive, `in_notify` clear, input_msgq and posq empty, no probe pending and no ANOM_R episode open. A disarmed-IRQ freeze or a stalled notify therefore keeps it running |
| Queues | `extern struct k_msgq input_msgq;` and `extern struct k_msgq position_state_msgq;` (peripheral-only symbol [V service.c:214]; role-gated extern) |
| att_pool | `DBGREC_ATT_POOL`: at init, `STRUCT_SECTION_FOREACH(net_buf_pool, p)` with `strcmp(p->name, "att_pool") == 0`, then `atomic_get(&p->avail_count)` [V net_buf.h:1094-1122,1225-1239; att.c:277]. Idle value 3. It can read one high for a few µs during a preempted allocation (harmless) |
| Keys | Listener on `zmk_position_state_changed`: counts only |
| Link | `BT_CONN_CB_DEFINE` → LINK_R, queued for the next handshake |
| Stacks, faults, boot | §6.3–6.5; the right half has its own crash page |

### 9.2 Right records

**Header:** type u8, seq u16, t_ms u32 (right uptime, low 32 bits), then ≤13 B of payload. One record is one notification of ≤20 B, which fits one 27 B ACL fragment (the MTU is never exchanged [V]).

| id | Name | Payload (≤13 B) | When |
|---|---|---|---|
| 0x41 | HELLO_R | role u8, build_id u32, boot_nonce u32, resetreas_raw u32 | First record after every handshake |
| 0x42 | BOOT_R | gpregret2 u8, level u8, crash_valid u8, crash_free u8, schema u8, variant u8, early_cnt u8, uptime_hi u32, build_run16 u16 (low 16 bits of `DBGREC_BUILD_RUN`) | After HELLO_R |
| 0x43 | CRASH_R | slot u8, frag u8 (0–5), data[11] | Newest ≤2 valid slots after each handshake; REQ_CRASH on demand |
| 0x44 | LINK_R | ev u8, reason u8, interval u16, latency u16, timeout u16, sec u8, rsv[3] | Link events (queued while disarmed) |
| 0x45 | SUM_R | isr_mask:10\|s2_mask:10\|rsv:4 (3 B: 100 ms bins with ≥1 ISR / ≥1 S2), isr_n u8, s2_n u8, ntf_max enc, sysq_max enc, cpu_max enc, inq_hwm:4\|posq_hwm:4 (inq_hwm saturates at 15), pin_stuck_max enc, keys_n u8, jump_max_div4 u8, att_min:2\|in_notify:1\|gate_blocked:1\|inq_full:1\|rsv:3 (inq_full = input_msgq reached 16, the driver's K_NO_WAIT drop condition [V DRV pmw3610.c:498-503; prod_right.config:461]) | Each active second |
| 0x48 | ANOM_R | det u8 (bits: ntf≥50, sysq≥50, pin≥50, isr_without_s2≥150, cpu≥30, posq_full, inq≥14, inq_full), dur_ms u16, ntf_max enc, sysq_max enc, pin_max enc, cpu_max enc, isr_n u8, s2_n u8, inq:4\|posq:4 (inq saturates at 15), att_min u8, keys_2s u8 (right presses in the 2 s before onset), jump_div4 u8. Header t_ms = onset | Once per episode, at its end (all conditions clear for 200 ms). ≤5/s, ≤60/min |
| 0x47 | HB_R | uptime_hi u32, batt_soc u8, tx_lost u16, fifo_used u8, anom_suppressed u8, level u8, mode u8, rsv u16 | Every 60 s while idle |
| 0x51 | STACK_R | thread u32, size u16, unused u16, idx u8, n u8, rsv[3] | After the handshake and every 30 min |
| 0x4F | CMD_ACK | cmd_seq u16, op u8, result i8 | Per command |

The firmware detects nothing beyond the single composite ANOM_R trigger; every other threshold lives in Python.

### 9.3 Diag service, handshake and TX pump (right)

```c
BT_GATT_SERVICE_DEFINE(zzz_dbgrec_svc,
  BT_GATT_PRIMARY_SERVICE(DBGREC_UUID_SVC),                                       /* attrs[0] */
  BT_GATT_CHARACTERISTIC(DBGREC_UUID_TLM, BT_GATT_CHRC_NOTIFY,
                         BT_GATT_PERM_READ_ENCRYPT, NULL, NULL, NULL),             /* [1] decl, [2] value */
  BT_GATT_CCC(NULL, BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT),      /* [3] */
  BT_GATT_CHARACTERISTIC(DBGREC_UUID_CMD, BT_GATT_CHRC_WRITE_WITHOUT_RESP,
                         BT_GATT_PERM_WRITE_ENCRYPT, NULL, dbgrec_cmd_write, NULL)); /* [4], [5] */
```

**Service name and DB hash:**
- The name sorts after `split_svc` and `bas`, so ZMK's handles and bonded CCC entries are unchanged [V A-07]. A CI symbol check confirms it.
- The DB-hash change causes the one-time write of §6.6. `sc_indicate` is harmless. At boot there is no link. The dongle never wrote the SC CCC, so there is no sc_cfg entry and no bt/sc write. With no CF entry the dongle stays change-aware, so no ATT request is refused [V gatt.c:474-487,1339-1370,6026-6034; att.c:2123-2129].

**Handshake** (fixes F3):
1. Every connection starts disarmed.
2. The dongle subscribes TLM (VOLATILE, renewed per connection), then writes CMD HELLO.
3. The right's CMD handler (BT RX). The stack already drops unencrypted writes because CMD is WRITE_ENCRYPT [V att.c:2077-2117,2119-2171]. On op == HELLO it stores `arm_req = conn_epoch` and calls `k_work_reschedule(&pump, K_NO_WAIT)`. It takes no reference. `conn_epoch` is incremented in the `connected` callback, which also runs in BT RX.
4. The pump arms only if `arm_req == conn_epoch` and `bt_conn_get_info()` reports CONNECTED.
   - Not yet armed: `armed = true`, `inflight = false`, `gen++`, `conn = bt_conn_ref(conn)`. This is the only reference the module ever holds. Then it queues the control records ahead of the FIFO: HELLO_R, BOOT_R, CRASH_R, pending LINK_R, STACK_R.
   - Already armed on this connection (a repeated HELLO): no new reference and no `gen` change. It only re-queues HELLO_R and BOOT_R.
5. Only `disconnected` releases the reference: `if (conn) { bt_conn_unref(conn); conn = NULL; }`, then `armed = false`, `inflight = false`, `gen++`, `arm_req` cleared. It runs inside deferred_work before the stack's final unref, so the single connection slot (BT_MAX_CONN=1) is recycled and ZMK re-advertises [V conn.c:343-352,1516-1550,2167-2235; ZMK peripheral.c:95-104]. A leaked or doubled reference would keep the right disconnected until reset.
6. Records produced while disarmed wait in the FIFO. The cursor never advances while disarmed.

So HELLO_R, BOOT_R and post-crash records reach the dongle after every right reboot or reconnect, and the dongle re-sends its cached right config after each HELLO_R.

**TX pump** (`k_work_delayable` on the sysworkq). It sends one record only when all of these hold:
1. armed and security ≥ L2;
2. no diag PDU in flight;
3. `input_msgq` empty and the input thread not inside `bt_gatt_notify` (`in_notify` clear);
4. `position_state_msgq` empty (a key notify the split-notify thread has already popped is covered only by condition 5);
5. att_pool avail ≥2 (with `DBGREC_ATT_POOL`);
6. ≥50 ms since the previous diag send.

Otherwise it reschedules in 20 ms and counts `gate_blocked`. With nothing queued the pump does not reschedule; an enqueue kicks it.

**Send:**
- Copy the head record into a static 20 B buffer. Remember the queue and seq of the record sent.
- `bt_gatt_notify_cb(conn, &p)` with:
  - `p.attr = &zzz_dbgrec_svc.attrs[2]` (the value attribute; its READ_ENCRYPT permission makes `gatt_notify` refuse an unencrypted link [V gatt.c:2513-2517]);
  - `p.func = dbgrec_tx_done`, `p.user_data = (void *)gen`.
- The allocation is K_NO_WAIT on the sysworkq, and no later step blocks [V att.c:734-747; A-06].
- A non-zero return retries after 50 ms (`tx_err++`). `-ENOTCONN` sets `armed = false` only. It never unrefs; the `disconnected` callback releases the reference.

**`dbgrec_tx_done`** fires when the ATT buffer is destroyed: at hand-off, or when flushed at disconnect [F18].
- It runs at the deepest point of the sysworkq hand-off chain [V att.c:245-275]. Keep it to one `bt_conn_get_info()`, a compare and a removal, with no other calls.
- If `ud != gen` or `bt_conn_get_info()` says the connection is not connected: discard. The record stays queued and is re-sent after the next handshake; the PC removes the duplicate.
- Otherwise remove exactly the sent record (matched by seq) if it is still queued, clear `inflight`, and record `handoff_ms = now − t_call`. That value is hand-off latency, **credit wait plus sysworkq queueing** (tx_processor runs on the same queue [V hci_core.c:4696-4719]); read it together with sysq lateness.
- PDUs still in the ATT TX queue at disconnect get no callback; the `disconnected` reset covers them.

**Queueing and order:**
- Delivery is at least once up to controller hand-off. A record already handed to the controller when the link drops is lost and shows only as a seq gap (not in `tx_lost`). Duplicates arise only when a hand-off callback is discarded on a live link. The PC assigns each relayed record the boot_nonce of the latest preceding HELLO_R, merging rings E and B by dongle arrival time, and removes duplicates by (boot_nonce, seq) within the records since that HELLO_R.
- FIFO: 4 KB of 20 B records (204 entries). When full, drop the oldest SUM_R/HB_R first, then ANOM_R, never the in-flight record. Count drops in `tx_lost`.
- Control records have their own fixed queue (HELLO_R, BOOT_R, ≤12 CRASH_R, ≤8 LINK_R, ≤8 STACK_R); its overflow is also counted.
- Priority: control records > ANOM_R > SUM_R/HB_R.

### 9.4 Dongle diag client (stage 2, `DBGREC_CLIENT`)

**Rules** [F25, A-10]:
- **At most one module ATT request outstanding on the whole dongle.** Both halves are serialised. Each half has its own params structs, and ZMK's slot discover params are never touched.
- **Gate:** start ≥10 s after `security_changed` (L2+) and after ≥1 s without dongle-side activity (no S4 events, no position events). The gate is re-checked before **every** request; activity aborts the chain and it is retried later.
- **Discovery** stays inside the dbgrec service's range, so a production right half or the left half costs one Find By Type Value request per connection.

**Sequence:**
1. From the dbgrec thread (the only step there): `bt_gatt_discover(BT_GATT_DISCOVER_PRIMARY, uuid = DBGREC_UUID_SVC)`. 128-bit discovery works [V gatt.c:4698-4703,3917-3923]. Not found → DIAG `no_diag`; done for this connection.
2. In the callback (BT RX): characteristic discovery within the service range, `uuid = NULL`, matching TLM and CMD in the callback.
3. In the discovery-complete callback (BT RX), so it is serialised with disconnect processing: `bt_gatt_subscribe` for TLM with fully re-initialised params:
   - `memset`; `.value = BT_GATT_CCC_NOTIFY`; `.value_handle`; `.ccc_handle = value_handle + 1` (own layout);
   - `atomic_set_bit(params.flags, BT_GATT_SUBSCRIBE_FLAG_VOLATILE)`, never `atomic_set` [F1];
   - a params struct is reused only after its NULL removal callback has been seen [V gatt.c:3743-3748]. The client never calls `bt_gatt_unsubscribe`.
4. Subscribe write-response callback → the dbgrec thread sends CMD HELLO via `bt_gatt_write_without_response_cb()` with a completion callback. At most 1 CMD in flight; no new CMD while the previous one has not completed within 2 s. The completion means hand-off, not delivery: the right drops an unencrypted write command silently [V att.c:2119-2171]. If no HELLO_R is relayed within 5 s of the completion, resend HELLO, at most 3 times per connection; the right treats a repeat as a HELLO_R re-request (§9.3 step 4). After 3 misses, record DIAG `no_hello`.
5. HELLO_R relayed → DIAG `live`. The dongle re-sends the cached right config (mode).

**TLM callback (BT RX):**
- NULL data → mark the params free and return STOP (the return is ignored [V gatt.c:3561]).
- Length 7..20 → relay into E (HELLO/BOOT/CRASH/LINK/ANOM/STACK/ACK) or B (SUM/HB), stamped with the arrival time. Return CONTINUE.

**Cost:** ≈4–5 round trips per connection, each ≤≈232 ms at latency 30 [V].

### 9.5 Commands (dongle → right)

CMD = `{op u8, cmd_seq u16, args ≤17}`, written without response.

| op | Command | Args |
|---|---|---|
| 0x06 | HELLO | dongle_ms u32, dongle_build u32 |
| 0x02 | MODE | mode u8 |
| 0x05 | SELFTEST | kind u8, magic u32 |
| 0x07 | REQ_CRASH | slot u8 |

The right copies a command into a 4-slot mailbox in BT RX, executes it in its dbgrec thread (HELLO is handled by the pump) and answers with CMD_ACK.

### 9.6 Right-side budget [E]

- About 1 PDU/s while active (SUM_R), plus ANOM_R as episodes occur, plus HB_R once a minute when idle.
- 0 while the gate is closed. At most 1 of 3 att buffers is used.
- About 0.4% of ~250 trackball PDUs/s.
- Tick wake-ups only while active; RAM ≈6 KB.

---

## 10. Optional depth (each item gated by a named question)

### 10.1 Shadow subscription (2b, `DBGREC_SHADOW`, its own flash)

**Purpose.** S3 on ZMK's input and position characteristics: the exact S3−S4 deficit (C3), predicted pevq loss, per-half bitmaps. It is built on the stage-2 client and uses the same gate and single-request rule.

**Procedure:**
1. Characteristic discovery inside ZMK's split-service range only, `uuid = NULL`, filtering `ZMK_SPLIT_BT_INPUT_EVENT_UUID` and `ZMK_SPLIT_BT_CHAR_POSITION_STATE_UUID` in one pass.
2. `bt_gatt_read(value_handle + 1)`: the CCC directly follows each value [V service.c:172-186]. It is a precondition only ("server cfg ≠ 0", which avoids a 0→1 store on the half). It is **not** evidence that ZMK is subscribed [F1].
3. Inside the read callback (BT RX): `bt_gatt_subscribe` with VOLATILE params (`atomic_set_bit`; `.value` set again before every subscribe, because removal zeroes it [V gatt.c:3747]).
4. Right after it returns 0, test `atomic_test_bit(params.flags, BT_GATT_SUBSCRIBE_FLAG_SENT)`:
   - **SENT set:** ZMK's local subscription was absent, so the write was issued. It is value-neutral on the half: no store, no cfg_changed [V gatt.c:2257-2271]. Record ZMKSUB `zmk_sub_missing`: ZMK's discovery or subscribe failed on this connection, for example through the silent K_NO_WAIT discover failure [F25].
   - **SENT clear:** the write was skipped, so ZMK's params existed and the shadow sits ahead of ZMK [V gatt.c:5496-5531]. Record `order_ok`.
5. **Never return `BT_GATT_ITER_STOP` for data.** If ZMK's params were absent, STOP would unsubscribe the shadow and write CCC=0 on the half [V gatt.c:3655-3657,5605-5613]. Return STOP only for NULL. Soft-off is an early return. Never call `bt_gatt_unsubscribe`.

**Callback checks:**
- Position notifications must be 16 B (ZMK reads 16 B unchecked [V central.c:367-370]).
- Input notifications must equal ZMK's input payload size.
- Otherwise return CONTINUE without using the data.

**Measures:**
- `pevq_pred_loss = max(0, used + k − 5)`, with k = popcount(new XOR prev) for position notifications and k = 1 for input. Counted only on connections with `order_ok` [A-30].
- The S3−S4 deficit defers to `zmk_sub_missing`: "S3 flowing, S4 zero, SENT set" is a ZMK subscription failure, not C3.

**Known side effect.** If ZMK takes its STOP path (input length mismatch), the shadow's presence suppresses ZMK's CCC=0 write [V gatt.c:5605-5613]. The half's state then differs from production, but only in that malformed-notification case.

### 10.2 Keystate exactness (2b)

- **State per half.** A shadow bitmap is UNKNOWN from subscribe until its first notification, after a NULL callback, and while unsubscribed. It may optionally be seeded with `bt_gatt_read` of the position value (the characteristic has READ [V service.c:183-185]); the seed is discarded if a notification arrived meanwhile.
- **D-KEYDESYNC:** the bitmap differs from the listener's pressed set for ≥300 ms, excluding combo positions, with pevq empty and the sysworkq not late.
- **D-STUCKLAYER:** a momentary layer is active while both bitmaps are KNOWN and show zero keys for ≥500 ms.
- Both run only while the relevant halves are KNOWN. A held key is invisible until its next change [V central.c:191-213], hence the UNKNOWN state.
- **Residual false negative:** a final snapshot lost on the peripheral. Posq overflow pops the oldest snapshot, and notify failures are only LOG_DBG'd [V service.c:221-238].
- The 1b KEYX counters remain the duration-independent signal.

### 10.3 RSSI (2b variant `dongle_dbg_rssi`)

- **Never through HCI** [F7].
- Read with `ll_rssi_get(handle, &rssi)` [V controller ull_conn.c:688-700: a lock-free read of `rssi_latest`, a magnitude, so dBm = −value] from the dbgrec thread, ≤1 Hz while the right half is active. The handle comes from `bt_hci_get_conn_handle()`.
- It needs `CONFIG_BT_CTLR_CONN_RSSI=y`, a compile-time change to the LLL radio paths (sampling every connection event [V lll_conn.c:571-591]). So it is a separate variant and an explicit observer delta [A-38r, A-48].
- The function is global in the controller library when CONFIG_BT_CTLR_CONN_RSSI=y [V ull_conn.c:687-700], and ll_connected_get() rejects a stale handle [V ull_conn.c:186-200]. client.c declares the prototype itself (§5.2).

### 10.4 CPI_STEP (2b)

On a dongle position press, walk the layers:
1. Start at `zmk_keymap_highest_layer_active()` (an index) and go down to the default layer's index.
2. For each index: `id = zmk_keymap_layer_index_to_id(idx)`; skip it if `!zmk_keymap_layer_active(id)`.
3. `b = zmk_keymap_get_layer_binding_at_idx(id, pos)`; `dev = zmk_behavior_get_binding(b->behavior_dev)`; NULL → skip.
4. If `dev == DEVICE_DT_GET(DT_NODELABEL(trans))`, continue. Stop at the first non-transparent binding.
5. If `dev == DEVICE_DT_GET(DT_NODELABEL(dpi))`, emit CPI_STEP(sign of param1).

The position is discarded. Until 2b, the user's note "&dpi 누름" covers this.

### 10.5 ACL credits (2b, `DBGREC_ACL_CREDITS`)

- `k_sem_count_get(&bt_dev.le.acl_pkts)` through the internal `hci_core.h`, after including `<zephyr/kernel.h>`, `<zephyr/bluetooth/bluetooth.h>`, `<zephyr/bluetooth/conn.h>` and `<zephyr/bluetooth/hci.h>` [V hci_core.h:10,272-284,433].
- A compile error cannot be "dropped" silently, so CI builds the entry with =y and, on failure, retries with =n and records the flag [A-05].

### 10.6 Verdict toast (2b)

Enabled only after the rules have been checked against at least 3 real marks.

### 10.7 Right pins and uploads (3)

Only if SUM_R plus ANOM_R cannot decide a real event. v2's pin protocol with the v3 transport:
- RAM pins; frames through the same armed pump;
- idle-only (≥300 ms with no ISR and no right key);
- at-least-once delivery with PC de-duplication;
- ≤6 pins/h.

### 10.8 Wrap pack (3a, `DBGREC_WRAP`)

GNU ld `--wrap` through `zephyr_ld_options`, which reaches every link stage [V extensions.cmake:163-165,2366-2387].

**Wrapped functions:**
- `__wrap_z_impl_k_msgq_put` (`k_msgq_put` is an inline syscall wrapper [V gen_syscalls]):
  - filters `&position_state_msgq` (right) and `&peripheral_event_msgq`/`&input_msgq` (dongle);
  - is ISR-safe and O(1);
  - treats `-ENOMSG` (K_NO_WAIT full) and `-EAGAIN` (timed) both as drops [V msg_q.c:165-176];
  - externs are role-gated.
- `__wrap_bt_gatt_notify_cb`: filters by attribute pointer and passes the dbgrec pump, `central_bas_proxy.c:89`, `hog.c:325` and BAS through.
- `__wrap_settings_save_one` and `__wrap_nvs_write` (C11); adv/scan start/stop (C7).

**Checks:**
- CI adds `-Wl,-y,__wrap_<sym>` and asserts in build.log that `service.c.obj`/`central.c.obj` reference the wrapped symbols. A `__wrap_` symbol being present proves nothing, and `target_ld_options` silently drops failing flags.
- A boot self-test on a private msgq sets `wrap_ok`.

### 10.9 PMW3610 diag patch (3b)

v2's design, unchanged. Weak hooks report burst MOTION/SQUAL/shutter, SPI errors, `input_report` return codes, the CPI-write window and a canary. The patch is workflow-applied to DRV@44b4a76.

### 10.10 WRN log counter (3, `DBGREC_LOGCOUNT`)

**Configuration:**
- `CONFIG_LOG`, `LOG_MODE_DEFERRED`;
- `ZMK_LOGGING_MINIMAL=y` + `ZMK_LOG_LEVEL_WRN=y`, which removes ZMK's `default 4` [V ZMK Kconfig:549-558] and gives `ZMK_LOG_LEVEL=2` [V CI dbg log];
- `LOG_MAX_LEVEL=2` compiles out DBG/INF formats, but WRN/ERR formats and non-log strings remain.

**Backend:**
- `LOG_BACKEND_DEFINE(…, autostart=true)` with `process`, `dropped` and a mandatory no-op `panic` [V log_backend.h:111-212].
- A format-string walker finds `%s`/`%c`/`%p` and computes argument offsets, with 8-byte alignment for ll/j/z/f/double (CBPRINTF_FP_SUPPORT=y). Anything ambiguous yields no arguments. It handles `package_len == 0` and hexdump messages.
- Arguments only for allowlisted Zephyr sources matched by exact registered name via `log_source_name_get` at init: `fs_nvs`, `flash_nrf`, `usb_device`, `usb_hid`, `usb_cdc_acm`, `usb_nrfx`, `bt_att`, `bt_conn`, `bt_gatt`, `bt_hci_core`, `input`. Never for ZMK sources.
- `src_id`/`fmt_ptr` are build-specific, so the PC resolves them with the exact ELF.
- The pump's own logs are filtered during pump calls: att.c:749 alloc ERR, gatt.c:2525 not subscribed, gatt.c:2544 no buffer.

**Gates:**
- Additionally forbidden: `LOG_FMT_SECTION`, `LOG_DICTIONARY_SUPPORT`, `LOG_OVERRIDE_LEVEL>0`.
- Privacy gate: a pyelftools scan of `.rodata` for the **exact** DBG/INF format strings extracted from `LOG_DBG`/`LOG_INF` calls in the pinned ZMK and DRV sources (e.g. "position %d keycode 0x%02X", "x/y: %d/%d", "Got peripheral event for %d!"). Never the bare word "keycode" [F16].
- CONFIG_LOG adds message construction on deep paths, for example gatt.c `notify_cb` in the right half's 1024 B input thread. A stack-minima gate of ≥256 B applies before shipping.

### 10.11 MPU stack-guard variant (3)

- `HW_STACK_PROTECTION=y` → `MPU_STACK_GUARD` (no SPLIM on Cortex-M4 [V]).
- With `FPU_SHARING=y`, a thread that has used the FPU switches to a 128 B guard: usable stack −64 B.
- Every stack object gains a 64 B reserve and up to 127 B of alignment padding, so "Kconfig sizes unchanged" does not mean "layout unchanged".
- The ISR (MSP) stack has no guard.
- For `K_ERR_STACK_CHK_FAIL`/MSTKERR, the ESF PC/LR are untrusted [V fault.c:255-290]; rely on the thread object and MMFAR.
- It runs as a variant only and is compared against the non-guard build.

### 10.12 Report polish (3)

HTML/SVG timelines, per-motion-hour rates with Poisson CIs, a weekly digest.

### 10.13 Stage 4: fix variants and fast-rest

**Variants:**
- `_fix3110`: ZMK 5b51501 via `git -c user.name=dbgrec-ci -c user.email=ci@invalid cherry-pick -x` (the container has no git identity). Fetch 5b51501 into zmk/ first (`git -C zmk fetch origin 5b51501`) if it is not reachable from 9ebbeff. May come right after 1b if right-hand typing precedes most "upstream silent" onsets.
- `_q16` (dongle): pevq `CONFIG_ZMK_SPLIT_BLE_CENTRAL_POSITION_QUEUE_SIZE` 5 → 16 [V central.c:146-147]. `_wq4096`: `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE` 2048 → 4096. Each lists its symbol in `allow:` (§14).
- `_llfix`: 355648a, cd0c5fc, d04563f. Zephyr is a shallow clone at a branch head [V ZMK app/west.yml:10-11], so for each commit first run `git -C zephyr fetch --depth=2 https://github.com/zephyrproject-rtos/zephyr <sha>`, then the identity cherry-pick. The job fails if `west-list.txt` shows a Zephyr SHA other than the one the picks were tested on.
- `_llstats`: a ~40-line LL counter patch.
- Optional RAM-retention test below 0x20008000.

**Fast-rest** (right half, runtime, opt-in). REST1/2/3 sample times via `sensor_attr_set` on the sysworkq:
- **Attribute ids.** The driver's enum is private (DRV src/pmw3610.h:97-120; values 4/5/6 starting at 0). Use local constants pinned to DRV@44b4a76 with a comment, or add the driver's src directory to the module includes.
- **Downshift coupling.** The driver programs the REST1/REST2 downshift registers against the compile-time sample times [V pmw3610.c:224-238]. Changing sample times rescales downshift times (e.g. 4.48 s → 1.12 s). Rewrite the downshift registers in the fast arm too, or record the coupling as part of the arm.
- **Cost:** ≈1.1–1.5 ms of sysworkq time (3 × ~300 µs `k_sleep` plus SPI) [V].
- **Serialise against `dpi_cyc` CPI writes**, which run from BT RX WQ on the right half [V pmw3610.c:150-163]. Apply only after ≥2 s with no split behavior invocation and ≥1 s with no ISR or right key, or right after a burst read in the same sysworkq item. Record any overlap in CFG_R.
- **Persistence:** settings are lost at every right reboot; the dongle re-sends them after HELLO_R.
- Whether the sensor honours a rate write while resting is hardware-only.

---

## 11. Host software (Python 3.14, stdlib only)

### 11.1 Processes

| Process | Started by | Role |
|---|---|---|
| **Supervisor** `dbgrec_supervisor.pyw` (pure Python + subprocess, ~200 lines including rescue) | HKCU `…\CurrentVersion\Run` value at logon (stdlib `winreg`; equivalent to a Startup-folder shortcut). The agent relaunches it if its heartbeat is stale or it is absent | Single instance via the named mutex `Local\dbgrec-supervisor`, which is released at process exit (byte-range locks may linger [LockFileEx docs]). **Adopts** a running agent before starting one: if `Local\dbgrec-agent` exists, it opens the PID recorded in `run\agent.pid` with SYNCHRONIZE\|PROCESS_TERMINATE\|PROCESS_QUERY_LIMITED_INFORMATION and keeps it only if its creation time equals the recorded one. Otherwise it starts the agent with `cwd = app dir` at NORMAL priority and keeps the Popen handle. Restarts with a 1/2/5/30 s backoff; an agent that exits because its mutex is taken counts as a retry, not a crash. An agent is hung only if the `ui_seq` in its heartbeat has not advanced during 30 s of the supervisor's own loop time, with each loop gap capped at 2 s. A loop gap >5 s (sleep, hibernate or starvation) restarts the window and suppresses kills for 60 s. Kills go through the held handle, never a bare PID. Runs the rescue watcher (§11.3). Runs `report --auto` and `maintain` every 30 min at BELOW_NORMAL. Writes `run\supervisor.hb` (with a seq) every 5 s |
| **Agent** `pythonw -m dbgrec agent` | Supervisor | Capture only (§11.4): no analysis in this process. Single instance via `Local\dbgrec-agent`; exits at once if it exists. The UI thread's timer writes `run\agent.hb` every 1 s: pid, creation time, ui_seq, device-poll and writer-flush counters, and the last resume time. The agent kills, through a handle checked against the creation time, and relaunches a supervisor whose `run\supervisor.hb` seq has not advanced during 30 s of the agent's own loop time (the same sleep rule). It relaunches the supervisor when `Local\dbgrec-supervisor` is absent. Detects an unclean previous exit through a `run\agent.running` marker |
| **Report subprocess** | Agent (60 s after each mark) and supervisor (every 30 min) | Decoding, rules, per-event reports (§12) |
| **Maintenance subprocess** `pythonw -m dbgrec maintain` | Supervisor (every 30 min, BELOW_NORMAL) | Compression and pruning (§11.5) |
| **CLI** `py -m dbgrec …` | User | Talks to the running agent through `\\.\pipe\dbgrec-<user>` (`multiprocessing.connection`, AF_PIPE, authkey file). A missing pipe (FileNotFoundError) means no agent, and only then does the CLI open HID_1 directly. A pipe that does not answer within 5 s means a hung agent: the CLI reports it and does not open HID_1 |

Every child process is started with the same `pythonw.exe` (`sys.executable`) or with `creationflags=subprocess.CREATE_NO_WINDOW`, so no console window ever opens. No PowerShell is used: device presence comes from cfgmgr32 through ctypes (§11.3; PowerShell `Get-PnpDevice` took ≈1.6 s per call here, cfgmgr32 0.05 ms).

Task Scheduler is not used [F23].

### 11.2 Install

`py -3.14 host\install_dbgrec.py`:
1. Copies the package to `%LOCALAPPDATA%\dbgrec\app\dbgrec\` and `dbgrec_supervisor.pyw` to `%LOCALAPPDATA%\dbgrec\app\`. A `.pyw` started by absolute path has its own directory on `sys.path`.
2. Writes a `.pth` file into `site.getusersitepackages()` pointing at `%LOCALAPPDATA%\dbgrec\app`, creating the user site directory if it is missing (it is missing on this PC), so `py -m dbgrec` works from any directory.
3. Writes `config.json`: hotkey, rescue on/off, slot map, the dongle serial (adopted at install from the HID_0 collections; the dongle must be plugged in) and learned half serials (§11.3).
4. Sets the HKCU Run value `dbgrec` (REG_SZ, no admin) to the fully expanded command line, e.g. `"C:\Users\<u>\AppData\Local\Programs\Python\Python314\pythonw.exe" "C:\Users\<u>\AppData\Local\dbgrec\app\dbgrec_supervisor.pyw"`, and deletes any `dbgrec` entry under `HKCU\…\Explorer\StartupApproved\Run`. A REG_SZ value does not expand `%LOCALAPPDATA%`. Explorer starts Run entries after its logon delay (≈10 s by default; no Serialize key here), at NORMAL priority and outside any job (checked on this PC).
5. Starts the supervisor, waits ≤15 s for the agent heartbeat, then prints `doctor`.

`--uninstall` reverses everything; data is kept unless `--purge`.

### 11.3 Rescue watcher and flash tool

**Flash tool.** `py -m dbgrec flash <zip> <dongle|right|left> [--target <name>] [--rescue]`:
1. Validates the bundle `MANIFEST.json`.
2. Extracts the board's UF2 to `staged\<board>.uf2`. If the zip holds more than one debug target for that board (e.g. `dongle_dbg` and `dongle_dbg2`), `--target` is required; without it the tool refuses. `--rescue` stages the production rescue image instead.
3. Archives `fw\<build_id>-r<run>\<target>\{zmk.elf, zmk.map, symbols.json, .config, zephyr.dts}` and the rescue images of the same CI run to `rescue\<sha8>\`. MANIFEST.json lists the SHA-256 of every `zmk.elf`, and the tool refuses to archive a different ELF under an existing key.
4. Appends a "staged" entry to `flashlog.jsonl` and prints Korean instructions, including "double-tap that board's reset within 30 min" (the watcher ignores older staged files).

It refuses a zip that has no rescue images.

**Import.** `py -m dbgrec rescue import <zip>` validates MANIFEST.json, archives the rescue images to `rescue\<sha8>\` and ELF/map/symbols to `fw\<build_id>-r<run>\<target>\`, appends an `imported` entry to flashlog.jsonl and stages nothing. Stage 1a starts with it; "newest flashlog SHA" includes imported entries.

**Board identity.** The bootloader drive cannot identify a board [F29]. All three boards run the same nice!nano bootloader (USB 239A:00B3, INFO_UF2.TXT `Board-ID: nRF52840-nicenano`, fixed FAT volume serial 0x00420042). The halves also enumerate as 1D50:615E whenever they are cabled. The identifier is the USB serial: the bootloader and ZMK both report `%08X%08X` of FICR DEVICEID[1], DEVICEID[0]. `config.json` holds `serial.dongle` and, once learned, `serial.right` / `serial.left`:
- `serial.dongle` is adopted at install from HidD_GetSerialNumberString on the MI_02 collection behind the Raw Input device, and is checked against HID_1 in 1b.
- A half's serial is learned by `py -m dbgrec learn right|left` with only that half cabled and running, or by user confirmation at the first staged half flash.

**Watcher** (supervisor, every 1 s; cfgmgr32 through ctypes, no PowerShell):
1. A new volume appears whose INFO_UF2.TXT has `Board-ID: nRF52840-nicenano`. The bootloader line is logged for A-13.
2. List the present bootloader devnodes with `CM_Get_Device_ID_ListW("USB", …, CM_GETIDLIST_FILTER_ENUMERATOR|CM_GETIDLIST_FILTER_PRESENT)` and keep `USB\VID_239A&PID_00B3\<serial>` (case-insensitive). Unless there is exactly one such devnode and exactly one new UF2 volume, do nothing and toast.
3. Choose by serial:
   - **`serial.dongle`.** Use `staged\dongle.uf2` if it was staged within the last 30 min. Otherwise use the rescue image of the newest flashlog SHA, but only while rescue is **armed**. Rescue is armed when the newest dongle flashlog entry is a staged debug build with no later rescue or production entry, or when `py -m dbgrec rescue drill` ran in the last 10 min. When disarmed, toast and do nothing: the user is assumed to be flashing by hand.
   - **`serial.right` / `serial.left`.** Copy that half's image only if it is staged; otherwise log and do nothing.
   - **Any other serial.** Do not copy. If exactly one half image is staged, ask in the tray or through `py -m dbgrec rescue confirm right|left`, and learn the serial on confirmation.
4. Wait 5 s. The tray "복구 일시중지 10분" item and `py -m dbgrec rescue pause` cancel the copy, for manual flashing.
5. Copy the file to the volume root, wait ≤30 s for the volume to disappear, then log `{utc, board, serial, file, sha, build_id, run, kind: staged|rescue, result}`. A staged file is moved to `flashed\`, so the next double-tap uses the rescue image.

An OSError at close may still be a success. A copy is recorded as successful only when `USB\VID_1D50&PID_615E\<expected serial>` re-enumerates within 20 s.

Hard rules: never copy an image unless the bootloader's USB serial equals the target board's adopted serial, or the user confirmed an unknown serial. Dongle presence means `CM_Locate_DevNodeW("USB\VID_1D50&PID_615E\<serial.dongle>")`, never a VID/PID wildcard. `rescue_auto=false` in config disables the watcher.

**Right-half rescue:** tray "오른쪽 복구 이미지 준비" or `py -m dbgrec flash <zip> right --rescue` stages the production right image. Then cable the half and double-tap its reset. Until `serial.right` is learned, the watcher asks for confirmation first (step 3). The laptop's own keyboard and touchpad work throughout [F22].

### 11.4 Capture agent

**UI thread:**
- A hidden top-level window (`WS_EX_TOOLWINDOW`, not message-only, so it receives broadcasts).
- `RegisterRawInputDevices({0x01, 0x02, RIDEV_INPUTSINK | RIDEV_DEVNOTIFY, hwnd})`.
- `WM_INPUT`: the device name is cached per hDevice via `GetRawInputDeviceInfoW(RIDI_DEVICENAME)` and matched **case-insensitively** against `vid_1d50&pid_615e&mi_02&col03` [F28].
- **S6 bins (100 ms):** n, Σ\|dx\|, Σ\|dy\|, n_wheel, Σ\|wheel\|, max inter-message gap, max loop lag. Counts may be coalesced by Windows [F20], so the rules use S4 Σ\|d\| on processor-free layers and gaps.
- **Lag** (for WM_INPUT and posted messages): `(GetTickCount() − (GetMessageTime() & 0xFFFFFFFF)) & 0xFFFFFFFF`; values ≥2^31 are treated as 0. **Heartbeat:** inter-arrival of `SetCoalescableTimer(hwnd, id, 100, NULL, TIMERV_NO_COALESCING)`; >150 ms means a loop stall. A unit test covers the wrap arithmetic [F21].
- Hotkey: `RegisterHotKey(MOD_CONTROL|MOD_ALT|MOD_SHIFT|MOD_NOREPEAT, 'M')`. The install warns if it is taken.
- Tray: `Shell_NotifyIconW`. `NIM_ADD` retries with backoff at start. `RegisterWindowMessageW("TaskbarCreated")` re-adds the icon after an Explorer restart.
- Power: `WM_POWERBROADCAST` (APMSUSPEND, APMRESUMEAUTOMATIC, APMRESUMESUSPEND) → HOSTEV.
- Session: `WTSRegisterSessionNotification` → lock/unlock HOSTEV. A 1 Hz input-desktop check (`OpenInputDesktop` + `GetUserObjectInformationW(UOI_NAME)`; failure counts as "not Default") records transitions. Neither is an input hook.
  - At start and after every resume, the agent reads the current state with `WTSQuerySessionInformationW(WTS_CURRENT_SESSION, WTSSessionInfoEx)`: SessionFlags 0 = locked, 1 = unlocked. WM_WTSSESSION_CHANGE reports only edges, so an agent restarted while locked would otherwise record "unlocked".
  - WTSRegisterSessionNotification is retried with backoff on RPC_S_INVALID_BINDING and paired with WTSUnRegisterSessionNotification before DestroyWindow.
  - Each input-desktop poll calls `OpenInputDesktop(0, FALSE, 0)` and then `CloseDesktop` (verified here: access 0 is enough and returns `Default`).
  - A 1 Hz foreground check records `fg_elevated` transitions (HOSTEV): GetForegroundWindow → GetWindowThreadProcessId → OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) → token integrity level. Access denied counts as elevated. It is not an input hook. Whether Windows withholds WM_INPUT from this medium-IL INPUTSINK window while an elevated window has focus is undocumented [A-56]; until 1a step 3b settles it, R4 and the 1a rules treat such intervals as host-blind.
- Robustness: every window-procedure branch is wrapped in try/except with an error counter that feeds the health state. `sys.unraisablehook` and `threading.excepthook` log to the rotating log (stderr is None under pythonw).
- Process setup: NORMAL priority class, and HighQoS via `SetProcessInformation(ProcessPowerThrottling, {Version 1, ControlMask EXECUTION_SPEED, StateMask 0})`. This matters on this hybrid-CPU laptop on battery. HighQoS does not lift the DC maximum processor state (30% in the active Balanced scheme on this PC), and Task Manager's Efficiency mode can override it. The agent therefore re-reads GetPriorityClass and GetProcessInformation(ProcessPowerThrottling) every 60 s, re-applies them and logs an AGENTEV on any change. doctor prints both values and the AC/DC processor caps.

**Device thread:**
- **Discovery:** SetupDi over the HID interface GUID → paths containing `vid_1d50&pid_615e` (case-insensitive) → `HidP_GetCaps`: UsagePage 0xFFDB, Usage 1, FeatureReportByteLength == 128 → `HidD_GetSerialNumberString` must equal `serial.dongle` (another serial is logged and ignored). Never by COM number or MI number.
- **Poll:** STATUS at 1 Hz; 4 Hz for 5 s after a mark_count change or while catching up. CHUNK per space until `more` clears. SEEK oldest at start and after a mismatch. De-duplication by (boot_nonce, space, seq).
- **Errors:** any `OSError` closes the handle and rediscovers after a 1/2/5 s backoff. PBT_APMSUSPEND closes; PBT_APMRESUMEAUTOMATIC reopens after 2 s.
- **New boot_nonce:** device-reboot HOSTEV, then push SLOTMAP and the desired mode.

**Pipe thread** (separate, daemon). It hosts the CLI server (`multiprocessing.connection.Listener`, AF_PIPE, authkey file). `accept()` blocks with no timeout [V Python 3.14 connection.py:725-746], so it never runs in the device thread.
- Requests are JSON over `send_bytes`/`recv_bytes`, never pickle.
- Each connection runs in its own short-lived thread with `poll(5)` timeouts.
- HID operations (`status`, `ctl`, `selftest`) are queued to the device thread and answered from it.
- The listener is created right after the agent mutex. A `PermissionError` (an existing pipe instance, FILE_FLAG_FIRST_PIPE_INSTANCE) makes the agent exit.

**Writer thread:** §11.5.

### 11.5 Storage and disk budget

**Layout** (`%LOCALAPPDATA%\dbgrec\`, outside OneDrive):
- `data\YYYY\MM\DD.dbr` (+`.zst`), `reports\`, `fw\`, `rescue\`, `staged\`, `flashed\`, `run\`, `log\`;
- `flashlog.jsonl`, `marks.jsonl`, `notes.jsonl`, `boots.jsonl`.

**Block format:**
- Block header (32 B): `'DBB3' u32, payload_len u32, n_frames u32, utc_ns_base u64, qpc_base u64, crc32 u32`.
- Frame: `len u16, kind u8, dqpc_us u32 (qpc_before − qpc_base), rtt_us u16, payload`.
- Kinds: STATUS, CHUNK (raw records verbatim), RAWBIN, HOSTEV, AGENTEV, MARKH (hotkey/tray marks and notes).
- A block is flushed and fsynced every 10 s or 64 KB. A truncated last block is cut off at start. Raw frames are decoded offline, so decoder fixes re-analyse history.

**STATUS thinning.** A STATUS frame is stored only if a field other than uptime64, cyc32 and the three spaces' head_seq/oldest_seq/read_seq changed (sequence progress is recoverable from CHUNK first_seq, n_rec and lost_before), or it is the minimum-RTT sample of the last 10 s (clock fit).

**Compression:** never in the agent. The supervisor's 30-min maintenance subprocess (`pythonw -m dbgrec maintain`, BELOW_NORMAL) compresses every past-day `.dbr` that has no `.zst` yet:
- level 19 on AC and level 9 on battery. Measured here on 30 MB: level 19 took 9.5 s CPU and about 100 MB of compressor memory; level 9 took 0.4 s for a 15% larger file. The DC maximum processor state is 30% on this PC.
- It writes a temp file and uses `os.replace`, verifies the `.zst` by decompressing it, then deletes the `.dbr`, retrying on PermissionError because a report may have it open.
- Days that ended while the PC was asleep are picked up at the next run.

**Budget [E, A-26].**
- Active second: CHUNK frame ≈131 B (9 B frame + 14 B CHUNK header + 108 B BINS) + RAWBIN ≈149 B + one STATUS per 10 s ≈14 B → ≈294 B/s ≈ 1.06 MB/h raw. Without the thinning rule above, STATUS adds 137 B/s (≈1.5 MB/h). Idle awake: ≈13 B/s.
- 8 active of 24 awake hours ≈10 MB raw → **≈2–4 MB/day** compressed. Worst case ≈8 MB/day (v2's format measured 5–8 MB/day; v3 drops per-frame CRC, absolute timestamps and idle STATUS).
- Cap: 365 days of data days, plus 4 GB as a backstop. Candidate reports (not mark reports) older than 90 days are pruned, and so are fw archives of builds that are neither among the newest 5 nor referenced by a mark. Rescue images, flashlog and notes are kept. doctor prints the size of each exempt class.
- Measure for a week in 1a/1b.

### 11.6 Tray, toasts, doctor, bundle

**Tray colours** (reason always in the tooltip, e.g. "마지막 데이터 1 s 전 · 동글 abc1234 · 3h12m · 오늘 마크 2"):
- **Green:** HID_1 polled within 5 s, the Raw Input device present, no unseen red condition. Stage 2: also a right SUM_R/HB_R within 2 min while connected.
- **Yellow:**
  - the Raw Input device is seen but HID_1 is missing ("기록 펌웨어 없음": production flashed out of habit);
  - dongle absent;
  - right diag not live for ≥10 min while connected (stage 2);
  - `mark_cfg_ok=0`;
  - running build older than the newest archived build;
  - disk >80% of the cap;
  - right SOC <20% (stage 2).
- **Red:** loss since last look beyond a threshold; a crash since last look; level SAFE/INERT (dongle, or the right half's BOOT_R level); an agent error counter rising; disk cap reached. How a red condition is marked as seen (e.g. opening the tray menu) is decided in implementation and then written here.

**Toasts:**
- once per logon: "기록 중 · 동글 abc1234";
- each mark;
- health events (crash, level, firmware missing, agent restarted after a crash), rate-limited.

Toasts may not appear: Do Not Disturb may route them to the notification centre, and new tray icons start in the overflow area (README: pin the icon). The absence of a toast never means the agent is dead; `doctor` and the heartbeat decide.

**`doctor`** checks:
- supervisor and agent heartbeats; the Run value equals the expected expanded command line and is not disabled in `HKCU\…\Explorer\StartupApproved\Run` (first byte 03/07 = disabled in Settings → Apps → Startup or Task Manager); the pythonw.exe path exists;
- HID_1 present, its serial equals `serial.dongle`, and its build_id/run vs flashlog; the Raw Input device;
- rescue images present and matching the config SHA;
- hotkey registered; tray present;
- the agent's priority class and power-throttling state, and the AC/DC processor caps;
- last data age; error counters; disk, with the size of each exempt class.

**`bundle --mark N | --since 3d`** writes a zip with:
- raw frames for the window, decoded CSV, report.md (rules version, evidence lines, data-quality gaps, firmware arm);
- flashlog, build ids with symbols.json, the agent log;
- Windows build and hub info.

Serial and nonce are redacted. It is written so an AI session can act on it without the binaries.

### 11.7 CLI

```
py -m dbgrec status | doctor | mark ["memo"] | note <n> <tag> | unmark <n>
py -m dbgrec report [--mark N | --since 7d | --auto] | bundle (--mark N | --since 3d) | maintain
py -m dbgrec flash <zip> <dongle|right|left> [--target <name>] [--rescue]
py -m dbgrec rescue (import <zip> | drill | confirm <right|left> | pause | resume | status)
py -m dbgrec learn <right|left>
py -m dbgrec ctl mode <off|normal> [--board right] | diag hello
py -m dbgrec selftest <dongle|right> <kind> --i-know
```

- `rescue import` archives a bundle's rescue images without staging anything; `rescue drill` arms the dongle rescue for 10 min; `rescue confirm` answers the watcher's unknown-serial question (§11.3).
- `learn` records a half's USB serial with only that half cabled and running.
- `diag hello` (stage 2, test only) forwards a CMD HELLO through CTRL RIGHT_CMD.
- `selftest` needs `--i-know` (§6.4).

---

## 12. Analysis and reports (Python; every threshold lives here)

### 12.1 Pipeline

1. **Decode** the raw frames (schema byte; an unknown schema produces a report line, never a crash).
2. **Clock-map** them (§8.6).
3. **Episode finder.** Look in [mark − 30 s, mark + 2 s] and take the most recent of:
   - an S6 or S4 gap ≥150 ms preceded by motion (≥3 events in the prior 300 ms);
   - a diverted interval (L1/L4/L5 with S4 flowing, or S6 wheel while S4 carries x/y);
   - the note "키도 멈춤".

   If none: "first motion after idle" (gap preceded by ≥1 s idle), else "no pipeline anomaly".
4. **First diverging point:** the earliest observation point (S0–S6) whose rate falls below 10% of its pre-episode baseline while the point before it stays ≥50%.
5. **Rules** for the current stage. Each cause gets CONFIRMED / LIKELY / POSSIBLE / RULED OUT / NO DATA with numeric evidence lines.

### 12.2 Stage-1a rules (S6 only)

| Finding | Report |
|---|---|
| S6 continuous through the marked interval | "pointer delivered (perception/app)" |
| S6 gap while the session is unlocked, the input desktop is Default, the foreground is not elevated and loop lag is clean | "device or USB" |
| S6 gap while any of those host gates fails | "host-blind (판정 불가)" |
| Wheel instead of x/y | "layer diverted (C4)" |

Every result carries the note context and power/lock state.

### 12.3 Stage-1b rules (first match wins)

| Rule | Condition | Verdict |
|---|---|---|
| R0 quality | LOST/overrun/bins_lost covering the window; agent coverage < window; clock residual >20 ms; mode off; level ≠ NORMAL | "판정 불가 (H6)" plus the reason |
| R1 dongle reset | A new boot_nonce within [onset − 2 s, end] | C9/C10 dongle, with the crash slot (kind, func+off, thread, LL file:line) when valid. A POR right after a hibernate resume is benign (USB power cut, F22) |
| R2 link | A half's LINK disc/reconnect within [onset − 5 s, end] | "link loss ≥4 s **or** right-half reset (separable in stage 2)". Reason 0x08 ≈4 s after the last arrival |
| R3 layer | L1/L4/L5 set through the episode with S4 flowing, or S6 wheel while S4 carries x/y | C4. A KEYX lost release before or in the window → "lost release (C3 key drop)". Otherwise "key held (user/hardware) or unknown" |
| R4 host/USB | S5 reports flowing (s5_n > 0 in the gap bins) while S6 is silent ≥150 ms, **and** endpoint USB, USB configured, session unlocked, input desktop Default, foreground not elevated (gate kept unless 1a step 3b shows it is unnecessary), loop lag clean (heartbeat gaps <150 ms, WM_INPUT lag <50 ms) | C8-host. Variants: USB suspended or not configured → C8-device; `lst_max ≥30 ms` covering the gap → C8-device (HID send timeout) |
| R5 dongle-internal | An S4 gap overlapping any of: sysq_late ≥40 ms, pevq_hwm = 5, inq_hwm ≥14 (16 = queue full), cpu_gap ≥20 ms; or KEYX in the window; or orphan_n > 0 with pevq_hwm = 5 or inq_hwm = 16 in the same or previous bin. An orphan without a full dongle queue is reported as "upstream loss" (R6 / stage 2), not C3 | C3 / dongle stall, citing the lane |
| R6 upstream silent | An S4 gap ≥150 ms mid-motion with every dongle lane clean | "upstream: right half or link". Annotations: right presses in the 2 s before onset (C1 plausibility); **right keys arriving during the gap** (right link alive → right input path or sensor, not RF); left keys during the gap (dongle radio alive); profile open/unconnected (advertising) and halves_conn < 2 (scanning) for C7 context; right SOC |
| R7 no anomaly | S4 and S6 continuous | "pipeline delivered motion (perception/app)" |

**Power backfill:** WM_POWERBROADCAST records are primary. When the agent was not running, use System Power-Troubleshooter Id 1 SleepTime/WakeTime. Never use Kernel-Power 107's TimeCreated as the wake time.

### 12.4 Stage-2 rules (refine R2 and R6)

| Cause | Signature |
|---|---|
| C1 (B2 loop: right-hand typing fills the right's `position_state_msgq`, the right sysworkq blocks in ~100 ms quanta, and sensor reads and notifies stall together) | `keys_2s > 0`; posq_hwm = 10; sysq ≥90 ms repeated in ~100 ms quanta; pin_stuck ≥50 ms; notify blocked with att = 0; jump on resume |
| C2 (RF) | Notify blocked (and att = 0) **while** sysq is healthy and posq is not full |
| C5a (REST wake) | Gap at the first motion after idle with few ISRs in the first 100 ms |
| C5b (sensor silent) | Note "공을 굴리던 중" with isr_n = 0, pin inactive, sysq healthy |
| C11 | Onset 0.5–2 s after the right's HELLO/security event, with R-CPU/R-SYSQ |
| Right reset | New HELLO_R boot_nonce + raw RESETREAS + CRASH_R |

**Attribution:** if att or hand-off latency rose **before** the first ≥90 ms sysq event, report "link-triggered, C1 amplified".

### 12.5 Automatic candidates (no mark)

The report runs every 30 min and finds:
- (a) an S4 gap ≥300 ms mid-motion (prior 200 ms speed above threshold) that resumes ≤10 s with a jump, with no R1–R3 explanation;
- (b) R4 conditions with a gap ≥300 ms;
- (c) KEYX;
- (d) BOOT or crash;
- (e) LINK disc with a reason other than user/local.

Each new candidate gets a per-event report, capped at 20/day; marks are never capped. Natural pauses are excluded by the mid-motion and jump criteria. Candidates never toast until 2b.

### 12.6 Report content (`reports\mark-<n>.{md,html,csv}`, `index.{md,html}`)

**Per event:**
- verdict box: cause, confidence, one-sentence reason, ruled-out list with reasons;
- 100 ms per-point table S0–S6 for [−10 s, +5 s] (CSV alongside) with context lanes;
- note, power/lock state, firmware arm and observer deltas;
- data-quality footer.

**Index:**
- marks and candidates table;
- per-day counts;
- marks per active hour vs the 1a baseline, split by arm (flashlog) and mode;
- health: agent uptime %, HID_1 attached %, loss, boots by cause, stack minima, right SOC.

The HTML is self-contained (no CDN) and mirrors the Markdown; SVG timelines come in stage 3.

---

## 13. Cause signatures (C1–C11) and the stage that can show them

| Cause (old H) | Key evidence | Stage |
|---|---|---|
| C1 B2 loop (H2) | 1b: R6 with right typing before onset (plausibility). 2: posq_hwm = 10, sysq ~100 ms quanta, pin stuck, notify blocked at att = 0, jump | 1b hint, 2 likely, 3a decisive (posq put −EAGAIN), 4 `_fix3110` A/B |
| C2 RF <4 s (H2/H4) | 2: notify blocked with a healthy sysq and posq; right keys also silent; left alive | 2; 2b RSSI support |
| C2 RF ≥4 s (H3) | LINK disc 0x08 + reconnect, no right BOOT | 1b (right reset not excluded until 2) |
| C3 dongle drops (H5) | 1b: pevq_hwm = 5 / inq_hwm ≥14 / sysq late during S4 gap, orphan-X coinciding with a full dongle queue, KEYX. 2b: exact S3−S4, `pevq_pred_loss` | 1b likely, 2b confirmed, 3a decisive |
| C4 stuck layer (H5) | L1/L4/L5 through the episode, S6 wheel; root cause KEYX lost release (1b) or D-STUCKLAYER (2b) | 1b |
| C5a REST wake (H1) | First-motion gaps, few early ISRs | 2; 4 fast-rest A/B |
| C5b sensor silent (H1) | Note "moving" with isr_n = 0, pin inactive, healthy downstream | 2; 3b decisive |
| C6 CPI SPI race | Note "&dpi" or 2b CPI_STEP ≤1 s before onset, then an ISR storm with Σ\|d\| ≈ 0 | 2b; 3b decisive |
| C7 radio contention / LL fixes (H4) | Rate higher with profile open/unconnected (adv) or halves_conn < 2 (scan); both links stall together; LL assert file in lll*/ull* | 1b context; 3a/4 decisive |
| C8 USB/host (H5) | R4 | 1a/1b |
| C9 reset/fault/assert (H3) | New nonce, raw RESETREAS (SREQ + crash slot / LOCKUP / DOG / PIN / 0 → POR-BOR), slot symbols | 1b dongle, 2 right |
| C10 stack overflow | Watermarks trending to 0; crash in a thread near its stack bound | 1b/2; 3 MPU variant decisive |
| C11 reconnect CCC store | Onset 0.5–2 s after the right's HELLO/security, R-CPU ≈7 ms (≈85–90 ms when a flash page erase is included) | 2; 3a decisive |
| H6 data loss / observer | R0; `mode off` A/B against the baseline | all |

---

## 14. Build and CI

**Production** (`build.yml`, `build.yaml`) is unchanged and never loads `dbgrec/`. The reusable workflow adds a module only for a root `zephyr/module.yml` [V build-user-config.yml:84-91]. West discovery checks only each project root, and the manifest project is `config/` [V CFG config/west.yml:28-29; ZEP scripts/zephyr_module.py parse_modules]. Its `paths-ignore` lists only `README.md` and `docs/**` [CFG build.yml:2-9], so it still runs on pushes that touch only `dbgrec/**` or `host/**`. Those runs rebuild identical firmware and cost only runner minutes. Default: leave `build.yml` as it is. If the repository is private and Actions minutes run short (Q12), add `dbgrec/**`, `host/**` and `.github/workflows/dbgrec.yml` to `paths-ignore` under both `push` and `pull_request`. That is the only permitted edit to the production workflow. `dbgrec.yml` fails if a root `zephyr/module.yml` exists.

**`dbgrec/build-dbg.yaml`:**
```yaml
stage: 1a   # prep includes only debug entries whose stage ≤ this (1a < 1b < 2 < 2b < 3 < 3a < 3b < 4)
debug:      # board, shield, the base snippet and cmake-args come from the build.yaml entry named in `from`
  - {name: dongle_dbg,  from: charybdis_dongle, snippets: "dbgrec-common dbgrec-dongle", stage: 1b}
  - {name: right_dbg,   from: charybdis_right,  snippets: "dbgrec-common dbgrec-right",  stage: 2}
  - {name: dongle_dbg2, ... dongle_dbg + cmake: "-DCONFIG_DBGREC_CLIENT=y", stage: 2}
  # 2b: dongle_dbg2b (-DCONFIG_DBGREC_SHADOW=y -DCONFIG_DBGREC_CPI_STEP=y -DCONFIG_DBGREC_ACL_CREDITS=y; retried with ACL_CREDITS=n per §10.5),
  #     dongle_dbg_rssi (-DCONFIG_DBGREC_RSSI=y; allow: [CONFIG_BT_CTLR_CONN_RSSI])
  # 3: *_mpu (allow: [CONFIG_HW_STACK_PROTECTION, CONFIG_MPU_STACK_GUARD]); 3a: *_wrap (-DCONFIG_DBGREC_WRAP=y); 3b: right_sensor (patch)
  # 4: right_fix3110, dongle_q16 (allow: [CONFIG_ZMK_SPLIT_BLE_CENTRAL_POSITION_QUEUE_SIZE]),
  #    *_wq4096 (allow: [CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE]), *_llfix, *_llstats
rescue: generated in prep from build.yaml (below)
```

**Rescue entries** are generated in prep from `build.yaml`, so they never drift:
- It takes the entries whose artifact-name is `charybdis_dongle`, `charybdis_left` and `charybdis_right`; `settings_reset` is skipped, and a missing entry fails prep.
- It copies board, shield, snippet (one `-S` with the whole string, as build-user-config.yml:93-95) and cmake-args verbatim, with no module and no dbgrec args.
- Prep fails if a root `zephyr/module.yml` exists, because production would then add `-DZMK_EXTRA_MODULES=$GITHUB_WORKSPACE` [build-user-config.yml:84-91].
- These are the production arguments, but the build directory, the container digest and the west fetch are separate. The image is therefore the production configuration, not the production workflow's artifact, and it is not claimed to be byte-identical.
- Debug entries take board, shield, the base snippet and cmake-args from the same build.yaml entry and only add dbgrec snippets, cmake args and `allow:`.

**`.github/workflows/dbgrec.yml`:**
- **Triggers:** push to `my-keymap` on `config/**`, `build.yaml`, `dbgrec/**`, `host/**` or the workflow; `workflow_dispatch`. A keymap edit therefore rebuilds the debug and rescue images from the same SHA. Set `concurrency: {group: dbgrec-${{ github.ref }}, cancel-in-progress: true}`, and restore west modules with `actions/cache` keyed on `config/west.yml` as production does [build-user-config.yml:110-126]. Optionally, a push that changes only `host/**` runs only `host_tests`.
- **Job `host_tests`** (`windows-latest`; `actions/setup-python` with `python-version: "3.14"`): `python -m unittest discover -s host/dbgrec/tests -t host` (host/dbgrec and its tests directory carry `__init__.py`). It covers FakeHid, decoders, a synthetic frame stream per cause, clock fit, storage truncated block, lag wrap and the rescue decision table (serials, arming, import). Neither the runner's system Python nor the container's (3.12.3 [prod log:683]) has `compression.zstd`, and the host code uses Windows ctypes. Without `-t host`, the name `dbgrec` resolves to the repo-root firmware directory.
- **Job `prep`** (ubuntu runner, no container):
  1. `python dbgrec/ci/keymap_check.py config/charybdis.keymap config/boards/shields/charybdis/charybdis_layout.dtsi config/boards/shields/charybdis/charybdis_right.overlay`. It is a text parser and uses no preprocessor, since prep has no ZMK tree for `#include <behaviors.dtsi>`. Steps: strip `/* */` and `//` comments first (the keymap carries a commented-out `utility_layer`, CFG charybdis.keymap:63-75); take the child nodes of the `compatible = "zmk,keymap"` node in source order; split each `bindings = < … >` on `&`; fail on any bare macro token at a checked position. Halves: read `RC(r,c)` in `default_transform` map order; a column ≥ the right overlay's `col-offset` (6) is right. Checks:
     - layer order Base…Extra = 0…6;
     - 16/17 `&none` on 2 and 6, `&trans` on 4 and 5;
     - 23/35 `&none` on 1;
     - matrix transform halves as §7.4;
     - no combos node other than `/combos`.

     A failure stops the workflow, so a leaking mark chord is never built. gates_single.py repeats the position and layer checks on the dongle builds' `zephyr.dts`, which is fully preprocessed and authoritative. The prep check is the early stop.
  2. Schema constants: compare the `DBGREC_SIZE_*` macros in `rec.h` with `schema.py` (text compare; the firmware has `_Static_assert`s).
  3. Resolve the container digest: `docker pull zmkfirmware/zmk-build-arm:stable` + `docker inspect --format '{{index .RepoDigests 0}}'` → output `image`. The `needs` context is allowed in `jobs.<id>.container.image`. The digest goes to `container-digest.txt`. Production keeps the floating `stable` tag [build-user-config.yml:56], so the two can differ.
  4. Build the matrix JSON → output. Convert `build.yaml` and `dbgrec/build-dbg.yaml` with `yq -oj` (preinstalled; production uses it [build-user-config.yml:41]); then use stdlib json only. Include only debug entries whose `stage` ≤ the file's top-level `stage`, plus the three rescue entries.
- **Job `build`** (`needs: [host_tests, prep]`; matrix; `container: image: ${{ needs.prep.outputs.image }}`; `defaults: run: shell: bash`, which gives `bash -eo pipefail`):
  1. `west init -l config && west update --fetch-opt=--filter=tree:0 && west zephyr-export`, then `west list -f "{name} {sha}" > west-list.txt`.
  2. Patches (3b/4): `git apply --3way` or `git -c user.name=dbgrec-ci -c user.email=ci@invalid cherry-pick -x`, after fetching the commits into the shallow trees (§10.13). Zephyr patches run only when `west-list.txt` shows the Zephyr SHA they were tested on. A failure fails the job.
  3. Build:
     ```bash
     if [ "$KIND" = rescue ]; then
       SN=(); [ -n "$SNIPPET" ] && SN=(-S "$SNIPPET")          # verbatim, as build-user-config.yml:93-95
       EXTRA=($CMAKE_ARGS)                                      # build.yaml cmake-args, verbatim
     else
       SN=(); for s in $SNIPPET $SNIPPETS; do SN+=(-S "$s"); done
       EXTRA=($CMAKE_ARGS -DZMK_EXTRA_MODULES="$GITHUB_WORKSPACE/dbgrec" -DCONFIG_DBGREC_BUILD_ID=0x${GITHUB_SHA:0:8} \
         -DCONFIG_DBGREC_BUILD_RUN=$((GITHUB_RUN_NUMBER*100+GITHUB_RUN_ATTEMPT)) -DCONFIG_DBGREC_VARIANT=$VID $CMAKE)
     fi
     west build -s zmk/app -d build -b "$BOARD" "${SN[@]}" -- -DZMK_CONFIG="$GITHUB_WORKSPACE/config" \
       -DSHIELD="$SHIELD" "${EXTRA[@]}" 2>&1 | tee build.log
     ```
     Rescue entries get no dbgrec arguments: Kconfig rejects undefined symbols. The fallback for A-03 is `-DSNIPPET_ROOT=$GITHUB_WORKSPACE/dbgrec`.
  4. **`gates_single.py`.** It runs with the interpreter CMake used, `Python3_EXECUTABLE` in `build/CMakeCache.txt`, today /usr/bin/python3 3.12.3 [prod log:683]. pyelftools and PyYAML are importable there because `gen_isr_tables.py:14` and `snippets.py` import them in every build [prod log:1170]. Never `pip install`: it is the Ubuntu system Python. `dbgrec/ci/*.py` must run on Python 3.12 with only stdlib, pyelftools and PyYAML. Checks:
     - `.config` required, forbidden and numeric values (§6.1). Rescue entries must not contain `CONFIG_DBGREC`.
     - DTS (`zephyr.dts`):
       - all entries: `storage_partition` = 0xec000/0x8000;
       - dongle entries: exactly one `zephyr,cdc-acm-uart` node;
       - debug entries: `code_partition` = 0x26000/0xc3000 and `dbgrec_partition` = 0xe9000/0x3000;
       - dongle debug entries: exactly one `zmk,combos` node. Its first two children are `dbg_mark_ptr` and `dbg_mark_sym` with the specified positions and layers, and no child has a single key position (§7.7). The keymap position and layer checks of prep are repeated on this preprocessed DTS;
       - rescue entries: `code_partition` = 0x26000/0xc6000, no `dbgrec_partition`, no `dbg_mark` node.
     - Source grep: `behavior_dbg_mark.c` defines no `get_parameter_metadata`/`parameter_metadata`; no `k_thread_foreach(`.
     - ELF (`build/zephyr/zmk.elf`):
       - `symbols.json` (FUNC/OBJECT, Thumb bit cleared);
       - RAM free ≥40 KB (dongle) and ≥60 KB (right) from the linker memory report; FLASH ≤ the code partition;
       - right: the `zzz_dbgrec_svc` static-service entry is placed after `split_svc` and `bas` (symbol addresses).
     - Gate (dongle debug entries): in `.event_subscription` (`zmk.map`), the dbgrec `zmk_position_state_changed` entry comes after `combo.c.obj` and `keymap.c.obj` (§7.4). The order is also saved to the bundle.
  5. Upload with `actions/upload-artifact` as `t-${{ matrix.name }}`. Names must be unique per run [cf. build-user-config.yml:219-236]. Files: `<artifact>-<sha8>.uf2` (from `build/zephyr/zmk.uf2`), `zmk.elf`, `zmk.map`, `.config`, `zephyr.dts`, `build.log`, `symbols.json`, `west-list.txt`. ZMK sets `CONFIG_KERNEL_BIN_NAME="zmk"` [V prod_dongle.config:500; prod log "Linking C executable zephyr/zmk.elf"], so there is no `zephyr.elf`. `zephyr_pre0.elf` is an earlier link stage and must never be used for symbols.
- **Job `gates`** (`needs: build`). Use `actions/download-artifact` with `pattern: t-*` and no `merge-multiple`, so each leg keeps its own directory (all legs have the same file names). It runs in the pinned container, or reads only text inputs (`.config`, the memory lines of `build.log`, `symbols.json`, `west-list.txt`); a plain runner has no pyelftools. Checks:
  - (a) every leg's `west-list.txt` is byte-identical, else the job fails. It prints the Zephyr SHA and warns when it is not 10ba6d0 (§1 facts were verified against 10ba6d0);
  - (b) `gates_compare.py`: each debug entry's protected values (`dbgrec/ci/protected.txt`, §6.1) equal those of the rescue build of the same role, except symbols listed in that entry's `allow:` field in build-dbg.yaml. Every allowed delta is printed in `$GITHUB_STEP_SUMMARY` and in MANIFEST.json;
  - it writes RAM/flash deltas to the summary.
- **Job `bundle`** (`needs: [prep, gates]`, so a failed gate produces no bundle): one artifact `dbgrec-<sha8>`. Upload the directory tree, not a zip file; GitHub's download zip is the file `flash` and `rescue import` take. It contains:
  - all debug targets built at this `stage`;
  - `rescue/{dongle,left,right}.uf2`;
  - per-target ELF/map/symbols;
  - one `west-list.txt` (identical across legs, checked by gates), `build-id.txt` (build_id and run), `container-digest.txt`, `MANIFEST.json` (targets, SHA-256 of every UF2 and `zmk.elf`, allowed deltas).

  Retention 90 days. The flash tool archives everything locally, so there is no release job.

**Branch strategy:** the single branch `my-keymap`. Debug and production are separated by workflow, module location and snippets. The `_dbg` artifact naming is kept.

---

## 15. Compliance with the BRIEF timing and safety rules

| Rule | Compliance |
|---|---|
| LL prepare ≤275 µs: no immediate logging, no output or large memcpy under locks | ISR work ≤5 µs. Spinlocks guard word updates and ≤114 B copies. dbgrec uses no logging, UART/CDC output or shell in stages 1–2. Stack scans run unlocked |
| Flash is ticker-synchronised; no continuous writes | Recorder flash I/O happens only at POST_KERNEL 99 (before bt_enable) or in the fault handler just before the reset. No runtime flash. One-time writes are listed (§6.6) |
| Right sysworkq = TX pump + sensor reader + CCC store | Only the gated K_NO_WAIT pump (≤1 in flight), an O(1) probe and the listener run there. Fast-rest is stage 4 and serialised |
| Right input thread blocks K_FOREVER on att_pool | The recorder never originates traffic there. Pump gate: `input_msgq` empty, not in notify, att ≥2 |
| B2 loop | Read-only sampling. The pump also waits for an empty posq |
| Dongle 5-slot pevq (K_NO_WAIT drops) | The recorder never puts into it (the EV_MSC probe was dropped) |
| Dongle RX back-pressure | BT RX callbacks are O(1). At most one module ATT request on the whole dongle |
| HCI command pool = 1 | dbgrec issues no HCI commands [F7] |
| Stacks unchanged; no guard in production | Sizes and priorities enforced by CI. No MPU guard until the stage-3 variant. Hooks use <64 B of stack; watermarks are watched |
| Fatal = permanent halt in production | Recorded reset at every level (§6.3) |
| Studio overrides DT bindings | The mark is a combo with no settings storage; dbg_mark cannot be bound from Studio; runtime index/id check (§7.8) |
| Time wraps | u32 ms in records plus 64-bit anchors |
| Retention unproven | Not relied on |
| Privacy | §8.7; CONFIG_LOG off in stages 1–2 |

---

## 16. Hardware verification per stage

**Stage 1a** (PC only, production firmware):

0. **Import:** `py -m dbgrec rescue import <zip>` with the first CI bundle. `doctor` shows the rescue images OK; nothing is staged.
1. **Rescue drill:** `py -m dbgrec rescue drill` (arms rescue for 10 min), nothing staged; double-tap the dongle reset and touch nothing. Keyboard and pointer are back within 20 s, and flashlog shows a rescue copy confirmed by the dongle serial re-enumerating.
2. Right half in its bootloader (cable) with nothing staged: the watcher does **not** flash it.
   - 2a. With the right half cabled and running, double-tap the dongle (after `rescue drill`). It is identified by serial and the rescue proceeds.
   - 2b. With the dongle unplugged and the right half cabled, double-tap the right half with only dongle.uf2 staged. Nothing is copied.
   - 2c. Double-tap the dongle while rescue is disarmed. Nothing is copied.
3. While rolling: Raw Input is attributed only to MI_02 Col03 (case-insensitive). Record the background message rate and Σ\|d\| (coalescing magnitude, A-50).
   - 3b. Roll for 30 s with an elevated Task Manager focused and record whether WM_INPUT continues (A-56).
4. Hotkey from any focused app: toast within 1 s. Install reports no hotkey conflict.
5. Kill the agent: it is back within 5 s and the tray reappears. Kill the supervisor: the agent relaunches it within 60 s, and exactly one agent remains (adopted, same PID). Restart Explorer: the tray icon returns.
6. One S3 night and one S4 hibernate cycle: green next morning, one instance each, no stale heartbeat. After a resume from a >60 s sleep, no agent restart is logged (no AGENTEV restart, no crash toast).
7. Lock screen and a UAC prompt: HOSTEV lock and desktop transitions recorded.
8. Dev-flag injected 250 ms stall: the heartbeat gap is recorded; the lag-wrap unit test passes.
9. `doctor` all OK. CI: rescue images built; host tests and the keymap check green; the production workflow still builds.

**Stage 1b** (dongle_dbg):
1. `py -m dbgrec flash <zip> dongle` and double-tap the dongle reset: the keyboard works. Get-PnpDevice shows MI_00 still COM33, MI_02 COL01–03 unchanged and a new MI_03 vendor HID (A-01). Studio connects and reads the keymap.
2. Tray green; STATUS build_id matches the staged zip; the BOOT reset cause is plausible; one first-boot local-ID settings write, visible as a CPU gap.
3. HID: the agent opens MI_03 non-admin; 1000 STATUS GETs p95 ≤1 ms; a CTRL SET is acknowledged in `last_ctrl_seq` (optional USBPcap: SET_REPORT wLength = 128) (A-46).
4. 60 s of fast rolling: s4_dsum vs S6 Σ(\|dx\|+\|dy\|) within 1% over bins on Base/POINTER (no L1/L4/L5 bit); sysq_late max <5 ms; orphan_n = 0; the S6 rate equals the 1a baseline within noise.
5. Both chords toast within 2 s with the correct src. Fast typing of R, T, [ and ' on Base never marks.
6. Hold POINTER then SCROLL for 12 s while rolling: the report shows L4 for 12 s plus S6 wheel (C4).
7. Right half off then on, 5 times: LINK disc 0x08 ≈4 s after off, reconnect, trackball OK. The same for the left half.
8. Selftests `oops`, `llassert`, `llassert_isr`, `fault_isr`, 5× each (some while rolling, one during a Studio save): keyboard back within 3 s each time; each slot valid and symbolised (func+off, thread). `early` twice → STATUS level SAFE; 60 s later STATUS `gpregret2_now` has count 0; after selftest `reboot` the level is NORMAL. Single-tap reset → GPREGRET2 cleared (A-22r). The rescue gesture still restores production.
9. Unplug/replug, one S3 night, one hibernate: no unexplained loss. The POR after hibernate is labelled benign (A-20).
10. After 30 min of mixed use: minima of sysworkq, input, BT RX, usbd_workq and dbgrec ≥256 B.
11. Ongoing (not a gate): marks per active hour over ≥3 days vs 1a; at least 2 `mode off` days.

**Stage 2** (right_dbg + dongle_dbg2):
1. Rescue drill for the right (`py -m dbgrec flash <zip> right --rescue`, cable, double-tap; the first time, `py -m dbgrec learn right` or the tray confirmation records its serial).
2. `py -m dbgrec flash <zip> right` and `py -m dbgrec flash <zip> dongle --target dongle_dbg2`; cable the right half and double-tap each board's reset. Unplugged, the trackball and right keys work without re-pairing. One-time writes as in §6.6.
3. DIAG `live` within ≈15 s of the ball going idle, and **HELLO_R after every right power cycle** (10 cycles; the trackball works each time).
   - 3b. Send HELLO 3× on one connection (CLI `diag hello`), then reset the dongle. Repeat with a dongle reset ≈20 ms after a HELLO. The right reconnects within 5 s each time and SUM_R resumes.
4. SUM_R ≈1/s while rolling; `gate_blocked` shows no sends while input_msgq is non-empty or in notify.
5. **B2 provocation** (roll plus fast right-hand typing for 30 s): posq_hwm = 10, sysq in ~100 ms quanta, an ANOM_R with notify ≥50 ms. Any freeze is reported as C1.
6. **RF provocation** (cover the right half or walk away briefly): ANOM_R with notify blocked and sysq healthy → C2. Out of range: 0x08 on both sides.
7. `py -m dbgrec selftest right oops --i-know`: CRASH_R relayed after reconnect; trackball back within 3 s.
8. Right stack minima (input 1024, sysworkq 2048, BT RX 2200, split notify 756, dbgrec 1024, and the interrupt stack 2048 scanned for the INIT_STACKS fill) ≥256 B after 30 min (A-55).
9. Right SOC slope over 3–5 days within ≈2% of 1b; `mode off` A/B days.

---

## 17. Costs [E; CI and hardware replace these]

| | Dongle | Right (stage 2) | Left |
|---|---|---|---|
| Flash | +12–25 KB (268 → ≈290 KB of 780 KB) | +10–20 KB (197 → ≈215 KB) | 0 |
| RAM | ≈83 KB (E 16, B 64, buffers, thread), taken from the ~180 KB free in production, leaving ≈100 KB; CI requires ≥40 KB left | ≈6 KB, taken from the ~218 KB free in production | 0 |
| CPU | <0.3% | ≈0.2% while moving; ~0 idle | 0 |
| Battery | USB powered | ≈1 PDU/s while active; ticks only while active; ≤2% target | 0 |
| PC | agent ≈30 MB RAM; the maintenance subprocess uses ≈+100 MB for ≤30 s per day; <0.5% CPU, ≈2–4 MB/day disk (≤8) | | |
| Code | Stage 1b ≈900 lines C + 120 Kconfig/DT/CMake; stage 2 ≈500 right + ≈220 dongle client | | |
| Host | Stage 1a ≈1,000 lines Python + 150 tests + 150 workflow; 1b +≈400; 2 +≈300 | | |

---

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The recorder changes timing and freezes stop (Heisenbug) | Hooks ≤5 µs; production stacks/queues/conn parameters enforced by CI; no HCI, no logging, no runtime flash; gated pump. `mode off` days against the 1a baseline. If freezes vanish only with the recorder on, that is itself evidence |
| Debug firmware breaks the dongle | One-gesture rescue (§11.3) drilled before the first flash; levels SAFE/INERT; recorded resets |
| HID_1 renumbers interfaces or confuses Studio | Source-verified ordering with exactly one CDC (CI). First check of 1b. Discovery by usage page and serial |
| Fault handler writes the wrong flash | slot_ready magic, address window, erased-check, latch (§6.3) |
| A boot loop caused by the recorder | SAFE after 2 early crashes; INERT after 5; pin reset clears; rescue gesture |
| Diag subscription disturbs ZMK (stage 2/2b) | Diag client touches only its own service; one ATT request at a time; idle gate re-checked per request; VOLATILE via atomic_set_bit; no unsubscribe; shadow only in 2b with the SENT check |
| Studio layer reorder retargets the combos | 60 s index/id check, tray yellow, README |
| Windows Raw Input coalescing or lock screen fakes host gaps | Σ\|d\|/gap criteria; lock/desktop/endpoint/lag gating (R4) |
| Agent silently dead | Named-mutex single instances, agent adoption, mutual heartbeat sequence counters judged on loop time (no kill after sleep), Run key, `doctor`, tray states |
| Rescue flashes the wrong board | Boards identified by USB serial only [F29]; rescue armed only after a staged debug flash or a drill; unknown serials need confirmation |
| Disk growth | Thinned STATUS, block format, zstd (19 on AC, 9 on battery) in a maintenance subprocess, 365-day cap plus 4 GB backstop, pruning of old candidate reports and fw archives; measured |
| CI artifact expiry | The flash tool archives ELF and symbols locally by build id |
| Patches stop applying (3b/4) | ZMK and DRV are pinned by SHA. Zephyr follows `v4.1.0+zmk-fixes`, so Zephyr patches (_llfix) run only when west-list.txt shows the Zephyr SHA they were tested on; otherwise the job fails loudly |
| Debug and rescue images come from different trees | gates fails unless every leg's west-list.txt is identical; build_id plus run identifies each binary |
| A keymap edit breaks the mark assumptions | CI keymap check fails the debug build |

---

## 19. Playbook and open questions

### 19.1 One-page playbook (`host/README.ko.md`, Korean)

- **Keyboard dead after a flash, or a reboot loop:** double-tap the dongle reset and wait 20 s (rescue). The laptop keyboard and touchpad still work.
- **Studio cannot connect:** roll back the same way.
- **Freezes seem more frequent than in the 1a baseline:** `py -m dbgrec ctl mode off` for two days, then roll back if it persists.
- **Tray red "crash":** `py -m dbgrec bundle --since 1d`.
- **Tray yellow "기록 펌웨어 없음":** production is flashed. To keep recording, stage again with `flash` and double-tap.
- **Mark chord:** keep POINTER held until R and T are both down (holding it until both are up is also fine). If SYMBOLS is stuck, use the pinky chord, not POINTER.
- **Studio:** do not reorder or remove layers during the debug period, and do not rebind 16/17 on layers 2, 4, 5, 6 or 23/35 on layer 1 (the tray warns if you do). Other binding edits are fine.
- **Manual flashing of the dongle:** while rescue is armed, pause it first (tray "복구 일시중지 10분" or `py -m dbgrec rescue pause`).
- **PC without the agent:** double-tap the dongle reset and copy `rescue/dongle.uf2` from the bundle zip to the `NICENANO` drive by hand.
- **Ending the debug period:** roll the dongle (and in stage 2 the right half) back, then `py -3.14 host\install_dbgrec.py --uninstall` (`--purge` also deletes data).
- **Tray icon:** pin it.
- **Timing:** never flash a new stage when 10 minutes of fallout is not affordable.

### 19.2 Open questions (the design works without the answers; they set priorities)

Needed before 1a: Q1, Q2, Q12. Before 1b: Q3–Q6, Q11 (layer bits). The others before their stage: Q7 (3b/4), Q8 (3a), Q9 (4), Q11 (&dpi, 2b), Q13 (2), Q14 (if C8 shows up), Q15 (when a fix candidate appears). The numbers match the Korean plan; Q10 was removed in v3.1 without renumbering.

- **Q1.** What does a freeze look like? Do keys stall too? How long does it last? Mid-motion or first motion after idle? Does the cursor jump on resume? Any link to right-hand typing, &dpi, SYMBOLS/SCROLL, or battery?
- **Q2.** Autostart through the HKCU Run key with a supervisor and tray icon: OK? Is the laptop usually left awake for days, docked with the lid closed, or used on its own keyboard?
- **Q3.** Mark chords as specified, and the Ctrl+Alt+Shift+M hotkey (with right Shift): comfortable?
- **Q4.** Left half on production in all stages: OK? Is it always switched on?
- **Q5.** Has Studio ever saved edits on the dongle, especially layer reorders or removals?
- **Q6.** Is a BLE host profile paired or connected, or is it USB only? (C7 context.)
- **Q7.** Are workflow-applied patch files acceptable for stages 3b/4?
- **Q8.** Is the stage-3a wrap pack acceptable?
- **Q9.** Is the stage-4 fast-rest A/B (slightly higher sensor current on "fast" days) acceptable?
- **Q11.** Privacy: OK to record 100 ms layer bits during activity, and in 2b the time of &dpi presses (direction only)?
- **Q12.** Is the repo private or public (artifact retention; Actions minutes for the optional `paths-ignore`, §14)?
- **Q13.** Acceptable right-half battery cost (target ≤2%)?
- **Q14.** Would you try a direct PC port instead of the hub for a few days if C8 shows up?
- **Q15.** Promote fixes on the report's recommendation, or case by case?

---

## 20. Verification register

Status: **CONFIRMED** (from source, no further work), **NEEDS CI**, **NEEDS HW**, **PARTIAL** (v2 claim partly refuted; the v3 rule is named and the remaining part has its own check), **DEFERRED** (belongs to a later stage), **REPLACED** (v2 claim refuted; v3 mechanism named), **DROPPED** (feature removed).

| Id | Claim (v3 form) | Status | How / when |
|---|---|---|---|
| A-01 | HID_1 = interface 3 / EP 0x84 with exactly one CDC; MI_00/MI_02 unchanged | Source CONFIRMED; Windows NEEDS HW | Get-PnpDevice + Studio at 1b step 1; CI one-CDC gate |
| A-02 | v2 "SETs ≤64 B, buffer 128 suffices" | REPLACED by A-46 (128 B reports) | — |
| A-03 | snippet_root via ZMK_EXTRA_MODULES; layout with a separate common snippet | Mechanism CONFIRMED (incl. snippet order, §5.2); build NEEDS CI | First CI run with `stage: 1b` (dongle_dbg): `.config` has DBGREC=y, DTS has dbgrec_partition |
| A-04 | att_pool by name, avail_count | CONFIRMED (strcmp; may read one high transiently) | Stage-2 bench: 3 idle |
| A-05 | `acl_pkts` compiles via the internal header with the listed includes | NEEDS CI (2b), retry-with-=n fallback | 2b CI |
| A-06 | `bt_gatt_notify_cb` from the sysworkq never waits | CONFIRMED | — |
| A-07 | `zzz_dbgrec_svc` sorts after `split_svc`/`bas`; ZMK handles unchanged | CONFIRMED; side effects in §6.6 | CI symbol check; stage-2 no re-pair |
| A-08 | Second GPIO callback per dispatch, registered at POST_KERNEL 99 after the driver (90), so it runs before the driver's | CONFIRMED (counts burst cycles) | Stage-2 S0 ≈ burst rate |
| A-09 | v2 "shadow never writes CCC" | REPLACED by the SENT-flag design (§10.1) | 2b HW: 10 cycles per half, ZMKSUB order_ok |
| A-10 | Module ATT use does not starve ZMK | PARTIAL → rules: one request dongle-wide, chained in callbacks, gate per request | Stage-2 HW: reconnect while rolling, ZMK still subscribed (2b SENT check) |
| A-11 | NVMC writes from fault contexts are reliable | Mechanism CONFIRMED with guards; HW for CPU stall during NVMC and low battery | 1b selftests incl. `llassert_isr`, `fault_isr`, during a Studio save |
| A-12 | POST_KERNEL 99 precedes bt_enable; no ticker needed | CONFIRMED (erase delays bt_enable ~85 ms) | — |
| A-13 | UF2 reflash leaves 0xE9000–0xEBFFF intact | NEEDS HW | Record a selftest crash, reflash, confirm the slot replays; read INFO_UF2.TXT |
| A-14 | MPU guard + FPU_SHARING effects | CONFIRMED (stage-3 variant only) | — |
| A-15 | On-device SYMTAB | DROPPED (PC symbolisation, Thumb bit cleared) | — |
| A-16 | RAM/flash budgets (dongle ≈83 KB, right ≈6 KB) | NEEDS CI | gates job deltas; first CI run with `stage: 1b` (dongle_dbg), then stage 2 |
| A-17 | Studio cannot edit combos | CONFIRMED; reorder risk handled by A-18 (index→id identity check, §7.8) | — |
| A-18 | v2 boot name/binding self-check | REPLACED: index→id identity + device-pointer bindings every 60 s | 1b: mark_cfg_ok = 1 |
| A-19 | Raw Input device name and delivery | Name CONFIRMED on this PC; "every report" REPLACED by A-50 | 1a step 3 |
| A-20 | Dongle stays powered in S3; S4 cuts power | NEEDS HW | 1b step 9 |
| A-21 | RESETREAS 0 after an app clear = POR/BOR | CONFIRMED (raw register; precondition: previous boot cleared) | 1b: compare battery pull (right, stage 2) vs pin vs soft reset |
| A-22 | v2 "GPREGRET2 survives pin reset; sys_reboot zeroes GPREGRET" | REPLACED (F8). A-22r: GPREGRET2 survives sys_reboot and is cleared by pin reset; the 60 s work clears the early-crash count at every level, and the next boot is NORMAL | 1b step 8 |
| A-23 | EV_MSC probe | DROPPED | — |
| A-24 | Fast-rest via sensor_attr_set | PARTIAL → stage 4 with fixes (§10.13); rest-time honouring NEEDS HW | Stage 4 |
| A-25 | Upload pacing | DEFERRED (stage 3) | — |
| A-26 | v2 "2–3 MB/day" | REPLACED by the v3 format estimate 2–4 (≤8) MB/day | Measure a week in 1a/1b |
| A-27 | Right→dongle lower-envelope residual ≤10 ms p95 | NEEDS HW | Stage 2 |
| A-28 | Task Scheduler semantics | DROPPED (Run key + mutual supervision, A-49) | — |
| A-29 | v2 "KEYDESYNC zero in normal use" | REPLACED: KEYX in 1b; UNKNOWN-state keystate in 2b | 1b: normal day KEYX ≈0; `sysq150` while typing produces KEYX |
| A-30 | pevq depth predicts loss | PARTIAL → `max(0, used + k − 5)`, order_ok connections only | 2b |
| A-31 | Log-package parsing | PARTIAL → format walker, exact-name allowlist (stage 3) | Stage-3 CI unit test |
| A-32 | Timer-ISR-safe reads | CONFIRMED | — |
| A-33 | HID callbacks on usbd_workq | CONFIRMED (cooperative −1, 1 KB) | — |
| A-34 | Studio DTR flag | DROPPED | — |
| A-35 | `--wrap` takes effect on ZMK calls | Source CONFIRMED; call-site redirection NEEDS CI (`-Wl,-y`) | Stage 3a |
| A-36 | Patches apply to ZMK/DRV at their pinned SHAs and to the current Zephyr branch head (checked against west-list.txt) | NEEDS CI | Stage 3b/4 |
| A-37 | dbg_mark cannot be bound from Studio | CONFIRMED from source (listed as a zero-parameter behavior; binding rejected) [studio/behavior_subsystem.c:19-42,189-209] | — |
| A-38 | v2 "HCI RSSI holds the buffer ≤1 ms" | REPLACED: no HCI. A-38r: `ll_rssi_get` variant | 2b CI + HW |
| A-39 | CCC read as ZMK liveness | REPLACED: precondition only (§10.1) | — |
| A-40 | nm in the container | REPLACED: pyelftools; digest via prep job | First CI run |
| A-41 | ZMK log level 2 and no DBG text | Kconfig CONFIRMED; privacy gate changed to exact formats (stage 3); stages 1–2 have no LOG | Stage-3 CI |
| A-42 | Position bitmap = keys held | PARTIAL → last delivered snapshot; UNKNOWN until the first notification | 2b |
| A-43 | v2 lag guard | REPLACED: wrap-safe 32-bit lag + no-coalescing timer heartbeat; weeks-long reliability NEEDS HW | 7 days of continuous running counted from the start of 1a (continues into 1b), injected stall |
| A-44 | One-time writes | CONFIRMED and extended (§6.6) | 1b/2: CPU gaps only at those boots |
| A-45 | Position events carry a slot source | CONFIRMED (bonded slot index) | — |
| A-46 | (new) Non-admin open of the vendor TLC; HidD_Get/SetFeature with 128 B buffers; feature-only TLC accepted | NEEDS HW | 1b step 3 |
| A-47 | (unused: number retired during v3 drafting) | — | — |
| A-48 | (new) `ll_rssi_get` from a thread compiles and links (local prototype; `ll.h` has no includes) and reads plausibly | NEEDS CI + HW | 2b variant |
| A-49 | (new) Run key + mutual supervisor keep exactly one agent alive across S3/S4/Explorer restarts/kills, including adoption and the resume rule | NEEDS HW | 1a steps 5–6 |
| A-50 | (new) Size of background Raw Input coalescing on this build | NEEDS HW | 1a step 3, 1b step 4 |
| A-51 | (new) Diag handshake completes within the idle gate and re-arms after every right reboot; a repeated HELLO takes no extra connection reference | NEEDS HW | Stage 2 steps 3 and 3b |
| A-52 | (new) KEYX false-positive rate in normal use (listener position, reconnect epochs) | NEEDS HW | 1b ongoing; CI gates the subscription order |
| A-53 | (new) `sys_rand32_get()` returns entropy at POST_KERNEL 99 on these builds | CONFIRMED from source: XOSHIRO seeded on first use from entropy_nrf5 (chosen zephyr,entropy=&rng, PRE_KERNEL_1); the thread path blocks on the RNG ISR and returns 0 [random_xoshiro128.c; entropy_nrf5.c:225-249,318-321; nrf52840.dtsi:11; prod_dongle.config:755]. The first call may take ~1–2 ms. CI keeps a .config gate: XOSHIRO_RANDOM_GENERATOR=y and no TIMER_RANDOM_GENERATOR or TEST_RANDOM_GENERATOR | CI with `stage: 1b`, then the first 1b boots (nonces differ) |
| A-54 | (new) Board identity by USB serial (bootloader serial = app serial, CONFIRMED on this PC for all three boards [F29]) | NEEDS HW only for 1a steps 2a–2c | 1a steps 2a–2c |
| A-55 | (new) Right stack minima with the stage-2 hooks (input 1024, sysworkq 2048 incl. the pump and `dbgrec_tx_done`, BT RX 2200, split notify 756, dbgrec 1024, interrupt stack 2048) stay ≥256 B | NEEDS HW | Stage 2 step 8 |
| A-56 | (new) WM_INPUT keeps arriving at the medium-IL INPUTSINK window while an elevated window has focus | NEEDS HW (undocumented) | 1a step 3b; until then the elevated-foreground gate stays in R4 and the 1a rules |

**Confirmed from source for v3**, no further work: F1–F19, F25–F27, F29 (with this PC's PnP history), A-04, A-06, A-07, A-08, A-12, A-14, A-17, A-21 (with conditions), A-32, A-33, A-37, A-45, A-53. Also: the request-buffer check is `>` [usb_device.c:321]; `ll_rssi_get` exists under CONFIG_BT_CTLR_CONN_RSSI [ull_conn.c:688-700]; slot->conn is set at `bt_conn_le_create` [central.c:820]; the combo virtual position [combo.c:284]; `bt_workq` is static, and connected/security callbacks run in it, disconnected on the sysworkq [conn.c:2167-2230; hci_core.c:93,4331-4335].

---

## 21. v3.1 changes

This pass applied a second source verification (dongle, right half, host, CI) and two proofreading reviews.

**Dongle (stage 1b)**
- Record sizes fixed: MARK payload 16 B, LINK 13 B. BOOT uses the name `crash_page_erases` and gains `build_run` (23 B). STATUS byte 91 is `gpregret2_now`; offset 100 is `build_run`.
- Bin q byte: `inq_hwm:5` (0–16; 16 = full, the drop condition). The per-bin orphan bit is gone; `orphan_n` stays per second.
- Orphan-X re-scoped: a Y lost anywhere between the right driver and S4. R5 and C3 count it as dongle-side only with a full dongle queue.
- KEYX: `connected` (CENTRAL only) increments `key_epoch`; the listener clears `seen`; a MODE change clears both sets. The listener's position after combo.c and keymap.c is a CI gate instead of an informational print.
- The mark-chord leak is corrected: releasing POINTER between the R and T presses types "t", not "r". User rule: hold POINTER until R and T are both down.
- Mark `src` depends on combo order; CI requires `dbg_mark_ptr`/`dbg_mark_sym` as the first two `/combos` children and no single-position combo.
- Safety levels: a late crash resets the count, bit 7 is set only before a slot write, a `k_work_delayable` clears the count after 60 s at every level, every static hook checks the level, dbg_mark only counts at SAFE/INERT, and right-half SAFE/INERT behaviour is defined.
- Tick lateness is `k_cycle_get_32() − k_uptime_ticks()` inside the expiry (uptime is the scheduled time there); `t_submit` uses cycles.
- 0xEA000–0xEBFFF is stated as unused. A-37 and A-53 are confirmed from source. `ll_rssi_get` is declared locally.

**Right half (stage 2)**
- Handshake: no reference in BT RX; the pump arms on `arm_req == conn_epoch` and holds exactly one reference; only `disconnected` unrefs; a repeated HELLO only re-queues HELLO_R/BOOT_R; `-ENOTCONN` no longer unrefs. New hardware step 3b.
- `dbgrec_tx_done` removes exactly the sent record by seq; FIFO drop order and a separate control queue; an idle pump does not reschedule.
- Delivery is at-least-once only up to controller hand-off; the PC de-duplicates by (latest HELLO_R boot_nonce, seq).
- The dongle resends HELLO (5 s, ≤3 per connection, DIAG `no_hello`).
- Tick start and stop rules; S0 registration time; `inq_full` bits in SUM_R and ANOM_R; F26 corrected (one `bt/hash` write, no CF entry expected); BOOT_R carries `build_run16`; the stack check covers dbgrec and the interrupt stack (A-55).

**Host**
- The rescue watcher identifies boards by USB serial only (F29). Rescue is armed only after a staged debug flash or a drill. New commands: `rescue import`, `rescue drill`, `rescue confirm`, `learn`, `diag hello`, `maintain`. cfgmgr32 replaces PowerShell; success is confirmed by re-enumeration.
- Supervisor and agent: named mutexes, agent adoption, heartbeat sequence numbers judged on loop time, kills only through held handles.
- The CLI pipe server runs in its own thread and speaks JSON.
- Host gates: elevated-foreground tracking (A-56) and gated 1a S6 rules and baseline.
- Compression moved to a maintenance subprocess (level 19 on AC, 9 on battery). STATUS thinning ignores sequence fields. Budget recomputed. Cap: 365 days plus a 4 GB backstop, with pruning of old candidate reports and fw archives.
- Run value fully expanded and checked against StartupApproved; HighQoS re-applied every 60 s; session state read at start and resume; `CloseDesktop`; `CREATE_NO_WINDOW` for children.
- The S4–S6 comparison uses `s4_dsum` on processor-free layers (F20).
- `flash --target`; archive key `<build_id>-r<run>`.

**CI**
- `paths-ignore` is the only optional production edit; concurrency and a west cache.
- New `host_tests` job (Windows, Python 3.14). prep converts YAML with `yq`. `keymap_check.py` parsing rules and inputs are specified.
- Debug entries derive board, shield, snippet and cmake-args from `build.yaml`; a top-level `stage:` key; ACL credits in `dongle_dbg2b`; `allow:` lists for variants that change protected values.
- Rescue generation rules, per-kind DTS gates, `zmk.elf`/`zmk.map` names, unique upload names, identical `west-list.txt` across legs, and `bundle` depends on `gates`.
- Zephyr is a floating branch: notation, rescue wording, patch rules and the cherry-pick fetch are updated; `DBGREC_BUILD_RUN` is added.
- Stage 1a CI builds rescue images and runs host tests and the keymap check only.

**Editorial**
- S0–S6 are "observation points". Q10 removed (no renumbering) and questions grouped by when they are needed. Register legend adds PARTIAL and DEFERRED; A-47 marked unused; the A-18r reference fixed; usb_device.c:321; RIGHT_CMD args ≤17; the playbook and user-day table extended.
