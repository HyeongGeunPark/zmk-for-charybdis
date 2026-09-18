# Charybdis 동글 및 ESB 전환 계획

> 작성일: 2026-09-17<br>
> 전제 조사: [dongle-esb-research.md](dongle-esb-research.md)<br>
> 목표: nice!nano v2 동글을 유일한 central로 사용하고, 좌·우 하프를
> ESB peripheral로 구성하여 1 ms급 split/USB transport를 구현·실측한다.

## 현재 적용 상태 (2026-09-18)

사용자 결정에 따라 원래 순서보다 Zephyr 4.1 기준선 이관을 먼저 수행했다.

- Config branch: `codex/zmk-v04-migration`
- Migration code commit: `c69f9c8e218b464d50ed8fa800dc533b911db2bb`
- ZMK pin: `6e2ef41e022d555b10f116e395832913f71717b3`
- Board target: `nice_nano@2.0.0//zmk`
- Topology: 기존 right-central BLE 유지
- Legacy PMW3610 module: 제거됨
- PMW3610 이동 및 runtime control: 새 드라이버가 들어올 때까지 비활성
- Build verification: left, right + USB Studio, settings-reset 모두 성공
- [GitHub Actions run 35297671581](https://github.com/HyeongGeunPark/zmk-for-charybdis/actions/runs/35297671581)

검증 artifact:

| UF2 | SHA-256 |
| --- | --- |
| `charybdis_left-nice_nano@2.0.0__zmk-zmk.uf2` | `630699A04E9EE9B031D30B3C14F0D0CAE035CFF5F7DE353197F5184803794F35` |
| `charybdis_right-nice_nano@2.0.0__zmk-zmk.uf2` | `5E815517FD62397A882EB0EF5CA325A5E0DB20ACCCF44980BA15B570C93A3ED6` |
| `settings_reset-nice_nano@2.0.0__zmk-zmk.uf2` | `0DD6BE82134D011C8EE58794940F87E03B4EAF8E859AB336EF123BCA190EEF3A` |

여기까지는 compile 및 artifact 검증이다. 실제 키 매트릭스, BLE split, USB
Studio와 재페어링은 하드웨어 smoke test가 남아 있다. 다음 구현 순서는 새
PMW3610 driver, BLE dongle/input-split, ESB 순이다.

## 1. 확정한 목표와 범위

최종 데이터 경로는 다음과 같다.

```text
left half  --\
              ESB 2 Mbps --> nice!nano v2 dongle --> USB --> PC
right half --/                 central / PRX
```

확정 사항:

- Dongle: nice!nano v2/nRF52840, UF2 bootloader
- Host connection: USB-only
- Split transport: `zmk-feature-split-esb`
- Left/right: ESB peripheral/PTX
- Sensor: 현재 PMW3610 유지
- PMW mode: 현재 125 software mode에서 250 Hz mode로 변경
- Transport target: ESB 및 USB 1 ms, 측정으로 검증
- 기능 보존: 56 keys, layers, holds, mouse buttons, CPI, snipe, drag scroll,
  Shift reversal, Studio USB, sleep/wake, battery reporting, UF2 recovery
- 제외: 실제 1 kHz sensor, sensor/PCB 교체, encoder/RGB 활성화, BLE host fallback

성공의 의미는 PMW3610에서 초당 1,000개의 새 좌표를 얻는 것이 아니다.
PMW3610 fresh sample은 약 250 Hz이며, 별도 synthetic event로 ESB/USB path가
1,000 change reports/s를 처리하는지 검증한다.

## 2. 목표 interface와 build contract

### 2.1 Shield, build target, UF2 image

새 public build target:

- `charybdis_dongle`
- `charybdis_left`
- `charybdis_right`
- `settings_reset`

각 build entry의 `artifact-name`에도 위 role을 명시한다. ZMK reusable workflow가
생성물을 하나의 `firmware` artifact로 병합하더라도 그 안의 UF2 filename으로
target을 구분하여 잘못된 board에 flash하는 위험을 줄인다.

### 2.2 역할

| Target | ZMK role | Transport role | Host I/O |
| --- | --- | --- | --- |
| `charybdis_dongle` | central | ESB PRX | USB HID + Studio |
| `charybdis_left` | peripheral | ESB PTX, ID 1 | 없음 |
| `charybdis_right` | peripheral | ESB PTX, ID 2 | 없음 |

`CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y`는 dongle에만 존재해야 한다. Right의 현재
BLE-central default는 제거한다.

### 2.3 Shared layout

Logical layout/transform을 half-specific GPIO DTS에서 분리한다.

- 모든 target이 같은 56-position matrix transform과 physical layout node를
  같은 이름으로 include한다.
- Dongle은 `zmk,kscan-mock`, rows/columns/events 0을 사용한다.
- Left/right만 실제 kscan, row/column GPIO와 각자의 column offset을 적용한다.
- Dongle DTS에 half hardware를 통째로 include한 후 node를 반복 삭제하는 구조는
  사용하지 않는다.

### 2.4 Trackball input split

Shared DTS interface:

```dts
split_inputs {
    #address-cells = <1>;
    #size-cells = <0>;

    trackball_split: trackball_split@0 {
        compatible = "zmk,input-split";
        reg = <0>;
        status = "disabled";
    };
};
```

실제 implementation에서는:

- right가 `trackball_split`에 `device = <&trackball>`을 지정하고 enable한다.
- dongle이 같은 proxy를 enable한다.
- dongle의 `zmk,input-listener`가 `&trackball_split`을 구독한다.
- right의 기존 direct `zmk,input-listener`는 제거한다.
- left에는 shared label resolution을 위해 node가 남되 disabled 상태다.

### 2.5 PMW runtime behavior ABI

Keymap의 기존 binding은 유지한다.

- `PMW_CPI_INC` / `PMW_CPI_DEC`
- `PMW_SNIPE_CPI_INC` / `PMW_SNIPE_CPI_DEC`
- `PMW_SNIPE_HOLD`
- `PMW_DRAG_SCROLL`

Driver behavior 변경 contract:

- locality: `BEHAVIOR_LOCALITY_GLOBAL`
- sensor 없는 target: return success/no-op
- right sensor target: 실제 state/CPI 변경
- modifier-dependent parameter: central에서 Shift를 반영하여 INC/DEC로 변환 후
  peripheral에 전달
- press/release command 모두 idempotent하고 timeout 이후 stuck mode가 없어야 함

Zephyr 4.1 port에서는 native driver와 충돌하지 않도록 다음 namespace를 쓴다.

- compatible: `pixart,pmw3610-alt`
- Kconfig: `PMW3610_ALT_*`
- runtime dt-binding/keymap ABI: 기존 이름 유지

### 2.6 Studio와 keymap

- `CONFIG_ZMK_STUDIO`와 USB Studio transport는 dongle에만 둔다.
- `studio-rpc-usb-uart` snippet을 right build에서 dongle build로 옮긴다.
- Final ESB keymap에서 `BT_SEL`, `BT_CLR`, `BT_CLR_ALL`, `OUT_BLE` binding은
  `&none`으로 바꾼다.
- `OUT_USB`는 유지한다.
- Left/right bootloader binding은 유지한다.
- Dongle은 physical double-reset으로 UF2에 들어간다.

## 3. 단계별 구현

각 phase는 별도 branch/commit series로 만들고, 해당 gate가 통과하기 전에는
다음 phase의 dependency나 transport 변경을 섞지 않는다.

### Phase 0: baseline 보존

1. 현재 successful Actions `firmware` artifact의 left/right/settings-reset UF2를
   저장한다.
2. 각 file의 SHA-256과 다음 source revision을 기록한다.
   - config repository commit
   - ZMK revision
   - PMW driver revision
3. 현재 keyboard에서 acceptance checklist를 한 번 수행하여 known-good behavior를
   고정한다.
4. Rollback UF2와 flash 순서를 keyboard와 함께 접근 가능한 곳에 보관한다.

Gate:

- Baseline 두 half가 현재와 동일하게 정상 동작한다.
- Rollback UF2 image와 각 checksum이 로컬에 존재한다.

### Phase 1: PMW driver를 split-command-safe하게 변경

인접 PMW driver repository에서:

1. Runtime behavior locality를 CENTRAL에서 GLOBAL로 바꾼다.
2. Compile-time sensor node가 없는 target에서 `-ENODEV` 대신 성공 no-op한다.
3. `binding_convert_central_state_dependent_params`를 구현한다.
4. Central Shift 상태를 기준으로 CPI command 방향을 확정한다.
5. `125_SW` 대신 250 Hz performance option을 사용한다.
6. Current right-central topology로 먼저 build 및 regression test한다.
7. 통과한 driver commit을 config manifest에 exact SHA로 pin한다.

Gate:

- Right-central에서 기존 CPI/snipe/drag 기능과 Shift reversal이 동일하다.
- Continuous motion에서 약 250 fresh sample/s를 확인한다.
- Sensor 없는 build target에 behavior를 포함해도 build/runtime error가 없다.

### Phase 2: ZMK v0.3 BLE dongle

이 단계는 ZMK `v0.3`과 BLE split을 유지한다.

1. `charybdis_dongle` shield metadata, Kconfig, overlay/conf를 추가한다.
2. Shared logical layout DTS와 half hardware DTS를 분리한다.
3. Dongle에 mock kscan, full layout, central role, USB HID, Studio를 둔다.
4. Left/right를 explicit peripheral로 바꾼다.
5. Shared `trackball_split@0`과 dongle listener를 구성한다.
6. Right direct trackball listener를 제거한다.
7. `build.yaml`에 네 build target과 role이 명확한 UF2 `artifact-name`을 설정한다.
8. `settings_reset`을 세 board에 적용하고 BLE dongle firmware를 flash한다.

BLE dongle config에서는 두 peripheral을 위한 connection/bond count를 확보한다.
Host output은 USB를 기본으로 사용한다. Danger layer의 BT key는 이 phase의 pairing
diagnostic을 위해 임시로 유지할 수 있으며 final ESB phase에서 제거한다.

Gate:

- Dongle만 central이다.
- Left/right key event가 정확한 56 positions로 매핑된다.
- Right trackball이 dongle USB mouse로 동작한다.
- CPI/snipe/drag command가 왼쪽과 오른쪽 source key 모두에서 동작한다.
- Studio가 dongle USB에서 연결된다.
- Dongle/half power-cycle 및 한 half 분리·복귀 후 복구한다.

### Phase 3: Pinned Zephyr 4.1 stack, BLE 유지

최종 dependency를 적용하되 split은 아직 BLE로 둔다. 이 gate의 목적은
HWMv2/driver port 문제와 ESB 문제를 분리하는 것이다.

Manifest pins:

| Dependency | Exact revision |
| --- | --- |
| `zmkfirmware/zmk` | `6e2ef41e022d555b10f116e395832913f71717b3` |
| `badjeff/zmk-feature-split-esb` | `314c7cbaf4a74e1add1d6ffc8249de3e29965b8c` |
| `badjeff/sdk-nrf` | `9b3d2623fdcd9c0fd0284f860beea924568c9826` |
| `nrfconnect/sdk-nrfxlib` | `dfadf17305d8f000eda9aa74a5b9ff1c5647a23e` |

Implementation:

1. GitHub reusable workflow ref도 ZMK exact SHA로 바꾼다.
2. Board ID를 `nice_nano@2.0.0//zmk`로 바꾼다.
3. 기존 PMW driver와 runtime binding을 제거한 keyboard-only baseline을 먼저
   build하고 실제 하드웨어에서 검증한다.
4. 새 PMW driver는 native `pixart,pmw3610`과 충돌하지 않는 namespace로 별도
   구현하고, resulting tested commit을 exact SHA로 pin한다.
5. ESB module은 manifest에 있어도 transport는 disabled 상태로 둔다.
6. Phase 2의 전체 BLE-dongle regression을 반복한다.

Gate:

- 모든 target이 clean HWMv2 build에 성공한다.
- Native PMW3610과 custom alternate driver의 binding/device 충돌이 없다.
- Phase 2 기능 checklist에 regression이 없다.

### Phase 4: ESB-only final transport

Final common direction:

```text
CONFIG_ZMK_SPLIT=y
CONFIG_ZMK_BLE=n
CONFIG_ZMK_SPLIT_BLE=n
CONFIG_ZMK_SPLIT_WIRED=n
CONFIG_ZMK_SPLIT_ESB=y
```

Role-specific values:

```text
# left
CONFIG_ZMK_SPLIT_ESB_PERIPHERAL_ID=1

# right
CONFIG_ZMK_SPLIT_ESB_PERIPHERAL_ID=2

# dongle
CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y
CONFIG_ZMK_SPLIT_ESB_PERIPHERAL_COUNT=3
CONFIG_ZMK_SPLIT_ESB_AUTO_HEAL_KEY_POS_MAX=56
CONFIG_ZMK_BATTERY_REPORTING=y
CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING=y
CONFIG_ZMK_SPLIT_BLE_CENTRAL_PERIPHERALS=2
CONFIG_BT_MAX_PAIRED=2
```

Initial transport/resource values:

```text
CONFIG_ZMK_SPLIT_ESB_CTLR_TX_PWR_PLUS_8=y
CONFIG_ZMK_SPLIT_ESB_PROTO_TX_ACK=y
CONFIG_ZMK_SPLIT_ESB_MSG_POSTFIX_CRC=y
CONFIG_ZMK_SPLIT_ESB_PROTO_TX_RETRANSMIT_DELAY=600
CONFIG_ZMK_SPLIT_ESB_PROTO_TX_RETRANSMIT_COUNT=3
CONFIG_MPSL_TIMESLOT_SESSION_COUNT=1

CONFIG_ZMK_SPLIT_ESB_PROTO_MSGQ_ITEMS=64
CONFIG_ZMK_SPLIT_ESB_EVENT_BUFFER_ITEMS=64
CONFIG_ZMK_SPLIT_ESB_CMD_BUFFER_ITEMS=16
CONFIG_ESB_MAX_PAYLOAD_LENGTH=48
CONFIG_ESB_TX_FIFO_SIZE=1

CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4096
CONFIG_INPUT_THREAD_STACK_SIZE=4096
CONFIG_INPUT_QUEUE_MAX_MSGS=256
CONFIG_USB_HID_POLL_INTERVAL_MS=1
```

Steps:

1. Cryptographic RNG로 한 keyboard set 전용 ESB base/prefix address를 생성한다.
   같은 address를 세 image에 넣되 이를 secret으로 취급하지 않는다.
2. IDs 1/2와 array capacity 3을 적용한다. BLE가 꺼져 있어도 ESB battery proxy가
   사용하는 `CONFIG_ZMK_BATTERY_REPORTING=y`,
   `CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING=y`,
   `CONFIG_ZMK_SPLIT_BLE_CENTRAL_PERIPHERALS=2`, `CONFIG_BT_MAX_PAIRED=2`를
   dongle config에 명시한다.
3. ACK, CRC, RF hopping 및 module loss-sensitive retry default를 유지한다.
4. Pointer input application retry는 우선 0으로 둔다.
5. BLE config와 dead keymap binding을 제거한다.
6. `CONFIG_USB_HID_POLL_INTERVAL_MS=1`을 명시한다.
7. Dongle/left/right를 mutable source를 공유하지 않는 isolated clean CI job에서
   각각 build한다.
8. 세 device를 다시 settings-reset한 뒤 final firmware를 flash한다.

Gate:

- Static config/DTS gate, functional gate, transport-rate gate, stress/RF gate를
  모두 통과한다.
- Gate 실패 시 ACK/CRC를 끄거나 결과를 true 1 kHz라고 표기하지 않는다.

## 4. CI와 build 전략

현재 PC에는 이 project용 west/Zephyr SDK workspace가 없으므로 GitHub Actions를
reproducible primary builder로 사용한다.

Requirements:

- Workflow와 manifest를 같은 ZMK exact SHA에 맞춘다.
- 병합된 `firmware` artifact 안의 각 UF2 filename에 target role을 명시한다.
- Dongle/left/right는 각각 clean checkout/pristine workspace에서 build한다.
- Generated `.config`와 merged DTS를 diagnostic artifact로 보존한다.
- Release build는 verbose ESB logging을 끈다.
- 별도 diagnostic build에서만 ESB debug counters/USB logging을 켠다.
- Documentation-only push는 firmware build를 실행하지 않는다.
- `workflow_dispatch`는 항상 남겨 필요할 때 수동 build가 가능하게 한다.

Local debug가 필요하면 WSL2 Ubuntu 24.04에 두 repository 밖 별도 west workspace를
만든다. ESB module이 ZMK header를 조정하므로 build variant 간 같은 mutable
checkout을 공유하지 않는다.

## 5. 검증과 합격 기준

### 5.1 Static config/DTS

네 firmware build target이 clean build되어야 한다. 각 generated output에서
다음을 확인한다.

- Central role은 dongle 하나뿐이다.
- Left/right는 peripheral이며 host USB가 disabled다.
- Final build는 BLE split off, wired split off, ESB on이다.
- Left/right IDs는 1/2, central capacity는 3이다.
- `AUTO_HEAL_KEY_POS_MAX=56`이다.
- Dongle USB poll interval은 1 ms다.
- 모든 part에 동일한 56-position layout/transform이 있다.
- Right physical PMW -> input-split reg 0 -> dongle listener path가 enable된다.
- Studio transport는 dongle에만 있다.

### 5.2 Functional matrix

- 56 keys 각각의 press/release
- 빠른 chord와 양쪽 동시 입력
- momentary layer와 hold behavior
- 양쪽 Shift 및 modifier 조합
- mouse buttons 1~5
- continuous X/Y movement
- CPI up/down
- snipe CPI up/down
- snipe hold press/release
- drag scroll press/release
- Shift-reversed CPI operation
- ZMK Studio USB connection
- sleep/wake
- battery reporting
- dongle unplug/replug
- left 또는 right power-off/rejoin
- 세 board의 UF2 recovery

합격 조건은 key transition loss와 stuck key가 0이고 PMW mode release가 유실되어
stuck snipe/scroll 상태가 되지 않는 것이다.

### 5.3 1 ms USB endpoint

Windows USBView 또는 USBPcap/Wireshark로 dongle HID endpoint descriptor의
`bInterval=1 ms`를 확인한다. `.config`만으로 합격시키지 않는다.

### 5.4 Synthetic 1 kHz transport benchmark

PMW3610 rate limit을 제외한 transport capability를 검증하기 위한 test-only
firmware/config를 만든다.

1. Right peripheral에서 1 ms마다 값이 바뀌는 synchronized relative input event를
   60초간 생성한다.
2. Generated count, ESB TX count, dongle RX count, USB packet count를 기록한다.
3. USBPcap timestamp로 host-facing report interval을 계산한다.
4. Clean RF에서 queue overflow/drop이 0이어야 한다.
5. 평균 observed rate가 1,000 reports/s의 ±1% 안에 있어야 한다.

이 gate가 실패하면 firmware를 사용할 수 있더라도 "true 1 kHz transport"라고
표현하지 않는다. Drop 원인은 input queue, ESB queue, radio retry, dongle HID
coalescing, host capture 순서로 분리한다.

### 5.5 Real PMW test

- Continuous circular motion으로 fresh report rate를 측정한다.
- 약 250 sample/s가 기대값이다.
- Sensor 1,000 sample/s를 합격 기준으로 사용하지 않는다.
- X/Y event 두 개가 split queue를 압박하지 않는지 확인한다.
- Cursor discontinuity와 packet loss counter를 함께 관찰한다.

### 5.6 Stress/RF

최소 10분 동안 continuous trackball movement와 빠른 typing을 동시에 수행한다.

합격 조건:

- lost/stuck key 0
- input/ESB queue-full 0
- central command press/release loss 0
- power-cycle/rejoin 후 자동 복구

일반 desk environment와 deliberate 2.4 GHz traffic에서 TX failure, CRC, retry,
channel hop count를 기록한다.

Pointer loss가 clean RF에서도 발생하면:

1. pointer input retry를 0에서 1로 올려 재시험한다.
2. 다시 transport throughput과 tail latency를 측정한다.
3. 그래도 fail하면 queue size나 FIFO를 임의로 키우기 전에 trace를 남긴다.
4. CRC/ACK/hopping을 꺼서 benchmark 숫자만 맞추지 않는다.

`ESB_TX_FIFO_SIZE=1`은 pinned latest ACK fix와 함께 baseline으로 유지한다.
Repeatable command delivery failure가 있을 때만 FIFO 2를 별도 experiment로
비교한다.

### 5.7 Debounce와 end-to-end latency

기존 7 ms debounce는 transport bring-up 동안 유지한다. USB 1 ms와 switch
debounce는 다른 단계다. Chatter 측정 없이 debounce를 낮추지 않는다.

추후 end-to-end latency를 최적화할 때는 GPIO latency tester 또는 동등한
hardware timestamp 장비로 switch actuation부터 USB event까지 따로 측정한다.

## 6. Flash 절차

BLE dongle 전환과 final ESB 전환 때 각각 수행한다.

1. Dongle, left, right의 UF2 double-reset 경로를 확인한다.
2. 세 board 모두에 `settings_reset`을 flash한다.
3. Left peripheral production image를 flash한다.
4. Right peripheral production image를 flash한다.
5. Dongle central production image를 flash하고 USB에 연결한다.
6. Enclosure를 닫기 전에 key/trackball/Studio smoke test를 수행한다.
7. Firmware SHA, 동글·좌·우 production UF2와 settings-reset UF2의 checksum을
   기록한다.

ESB에는 OTA provisioning/update가 없으므로 physical reset 접근성을 제거하지
않는다.

## 7. Rollback

Final gate 실패 시 원래 right-central 구성으로 복구한다.

1. Left와 right에 `settings_reset`을 flash한다.
2. 보관한 baseline left/right UF2를 flash한다.
3. Dongle을 분리한다.
4. 원래 right USB central 구성의 전체 baseline checklist를 반복한다.

Driver-only regression이면 config repository와 sibling driver pin을 모두 이전
SHA로 되돌려야 한다. 한 repository만 rollback하여 manifest와 source가 어긋나지
않게 한다.

## 8. 완료 정의

작업은 다음이 모두 충족될 때 완료다.

- Reproducible exact-SHA manifest와 workflow가 존재한다.
- 네 firmware image가 isolated clean CI에서 성공하고 병합 artifact에 포함된다.
- Dongle만 central이고 좌·우가 ESB peripheral로 동작한다.
- 56 keys와 모든 현재 사용 중인 pointing/runtime 기능이 보존된다.
- Studio가 dongle USB에서 동작한다.
- USB descriptor가 1 ms를 광고한다.
- Synthetic benchmark가 합격하거나, 불합격 사실과 측정치가 명확히 기록된다.
- Real PMW3610이 안정적인 약 250 Hz fresh sample을 제공한다.
- Stress test에서 key loss/stuck/queue overflow가 없다.
- 세 board의 physical UF2 recovery와 baseline rollback이 검증된다.

## 9. 명시적 가정과 위험

- Final firmware는 USB dongle 없이는 사용할 수 없다.
- BLE host fallback은 구현하지 않는다.
- ESB address는 authentication/encryption key가 아니다.
- `zmk-feature-split-esb`는 release/tag가 없는 experimental dependency다.
- Pinned dependency update는 새 migration으로 취급하고 전체 test를 반복한다.
- PMW3610 250 Hz는 battery consumption을 현재 125 software mode보다 늘릴 수
  있으므로 사용 시간은 별도 실측한다.
- 현재 inactive encoder/RGB는 이 작업의 regression gate에 포함하지 않는다.
