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

여기까지는 compile 및 artifact 검증이다.

## 하드웨어 검증 결과 (2026-09-19)

위 표의 artifact를 left/right에 flash하여 실제 동작을 확인했다.

- 재페어링 불필요: 기존 host bond가 유지되어 flash 후 바로 연결됐다.
- 키 매트릭스, 좌·우 BLE split, USB 입력 모두 정상이다.
- 트랙볼만 동작하지 않는다. sensor node와 driver를 의도적으로 제거한 결과이며
  regression이 아니다.

따라서 Zephyr 4.1 keyboard-only 기준선은 통과로 확정하고, 이 상태를 config
repository의 작업 기준선(`my-keymap`)으로 삼는다. 다음 구현 순서는 새 PMW3610
driver, BLE dongle/input-split, ESB다.

이전 v0.3 + legacy driver 조합으로 되돌릴 계획은 없다. Rollback 대상은 이
keyboard-only 기준선이며, §7의 v0.3 rollback 절차는 더 이상 유지하지 않는다.

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

### 2.5 Pointer 기능 구성

> 2026-09-19 개정. 기존 custom driver의 runtime behavior ABI
> (`PMW_CPI_INC`, `PMW_SNIPE_HOLD`, `PMW_DRAG_SCROLL` 등)는 폐기한다.

ZMK 0.4는 pointer 가공을 sensor driver가 아니라 input-processor chain에서
처리한다. 따라서 driver는 얇게 두고 기능은 keymap에서 구성한다.

채택 driver: [badjeff/zmk-pmw3610-driver](https://github.com/badjeff/zmk-pmw3610-driver)

- `zmk-feature-split-esb`와 같은 저자이므로 Phase 4까지 toolchain 정합성이
  유지된다.
- compatible `pixart,pmw3610-alt`, Kconfig `CONFIG_PMW3610_ALT_*`를 사용하여
  Zephyr 4.1 native `pixart,pmw3610`과 충돌하지 않는다.
- split peripheral shield에서 동작하도록 설계되어 §2.4 input-split과 맞는다.
- scroll-mode, snipe-mode, auto-layer가 driver에서 제거되어 layer별
  `zmk,input-listener` override로 구성한다.
- `cpi`, `swap-xy`, `invert-x`, `invert-y`가 Kconfig가 아니라 devicetree
  속성이다. multi-sensor와 shared SPI bus를 지원한다.
- sampling rate와 reporting rate를 분리하고 interrupt 사이 변위를 누적한다.
  `CONFIG_PMW3610_ALT_REPORT_INTERVAL_MIN`으로 RF 환경에 맞춰 조정한다.
- `sensor_driver_api.attr_set`으로 `PMW3610_ALT_ATTR_CPI`와 downshift/sample
  time을 runtime에 변경할 수 있다.

기능 대응:

| 기존 기능 | ZMK 0.4 구현 |
| --- | --- |
| pointer 이동 | `pixart,pmw3610-alt` + `zmk,input-listener` |
| drag scroll | POINTER layer override + `&zip_xy_to_scroll_mapper`, `&zip_scroll_scaler` |
| snipe | layer override + `&zip_xy_scaler` |
| CPI inc/dec | `&zip_xy_scaler` 단계 전환, 또는 `attr_set` 기반 behavior |
| automouse layer | `&zip_temp_layer` |
| mouse button | `&mkp` (ZMK 내장) |
| split 전송 | `zmk,input-split` (Phase 2·3), 이후 ESB (Phase 4) |

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

### Phase 1: PMW3610 driver 교체

> 2026-09-19 개정. 기존 fork `HyeongGeunPark/zmk-pmw3610-driver`를 Zephyr 4.1로
> port하지 않고 `badjeff/zmk-pmw3610-driver`로 교체한다. 레거시 유지 목표는 없다.

1. `config/west.yml`에 `badjeff` remote와 `zmk-pmw3610-driver` project를 exact
   SHA로 pin한다. `main` branch가 zmk-0.4 line이다.
2. `charybdis_right.overlay`에 spi0 pinctrl과 `pixart,pmw3610-alt` node를
   복원한다. 기존 pin(SCK P0.08, MOSI/MISO P0.17, CS P0.20, IRQ P0.06)은 그대로
   쓰고, `cpi`, `evt-type`, `x-input-code`, `y-input-code`를 devicetree에 둔다.
3. 방향 설정을 이관한다. 기존 `CONFIG_PMW3610_ORIENTATION_90` +
   `CONFIG_PMW3610_INVERT_X` 조합에 대응하는 `swap-xy` / `invert-x` /
   `invert-y` 조합은 실측으로 확정한다.
4. `charybdis_right.conf`에 `CONFIG_SPI`, `CONFIG_INPUT`, `CONFIG_PMW3610_ALT`를
   켠다. nice!nano v2 + ext-power 구성이므로
   `CONFIG_PMW3610_ALT_INIT_POWER_UP_EXTRA_DELAY_MS`를 먼저 적용하여
   `Incorrect product id 0xFF` 초기화 실패를 회피한다.
5. right shield에 `zmk,input-listener`를 두고 base processor chain을 구성한다.
6. keymap POINTER layer에 listener override를 추가하여 snipe와 drag-scroll을
   복원한다. `&pmw` behavior와 `PMW_*` define은 제거 상태로 둔다.
7. build 통과 후 driver SHA를 config manifest에 고정한다.

Gate:

- right-central에서 pointer 이동, snipe, drag-scroll, mouse button이 동작한다.
- left와 settings-reset build target이 깨지지 않는다.
- flash 후 BLE 재페어링이 발생하지 않는다.

함정: devicetree는 Kconfig보다 먼저 preprocess된다
(`zephyr_default.cmake`의 module 순서가 `dts` 다음 `kconfig`). 따라서 keymap이나
overlay에서 `#if defined(CONFIG_SHIELD_CHARYBDIS_RIGHT)` 같은 guard를 쓰면 항상
거짓이고, 그 블록은 **빌드 에러 없이 조용히 사라진다**. shield별 DTS는 해당
shield의 overlay에 직접 둬야 한다. 기존 v0.3 keymap의 `&trackball` override도
같은 이유로 적용된 적이 없었다. Phase 2·3에서 dongle overlay를 만들 때 다시
밟기 쉬운 함정이다.

구현 상태 (2026-09-19): 위 1~7을 `my-keymap`에 적용했다. driver pin은
`44b4a76b74d293a93cec4ccb7e04cb8d29c10f93`이다. snipe와 drag-scroll은 POINTER
layer의 기존 키 위치에 `&mo SNIPE` / `&mo SCROLL`로 두고, 두 layer는 binding이
전부 `&trans`인 pointer mode layer다. CPI inc/dec는 대체 구현 없이 비워 두었다.
하드웨어 검증 (2026-09-19): pointer 이동, snipe, drag-scroll 모두 동작을
확인했다. 축 방향(`swap-xy` + `invert-x` + `invert-y`)과 snipe 배율, scroll
분모 24는 그대로 둔다. 이어서 두 가지를 반영했다.

- SYMBOLS layer(1)를 scroll layer로 복원했다. v0.4 이전에는 overlay의
  `scroll-layers = <1>`로 동작하던 것이며, keymap의 override가 위 guard 때문에
  적용된 적이 없어 유지되고 있었다.
- scroll 방향은 수평만 반전한다
  (`zip_scroll_transform INPUT_TRANSFORM_X_INVERT`). 처음에 수직까지 함께
  반전했으나 수직은 원래 방향이 맞아 되돌렸다.
- `CONFIG_PMW3610_ALT_INIT_POWER_UP_EXTRA_DELAY_MS`를 1000에서 300으로 줄였다.

Phase 1은 이로써 종료한다.

### Phase 2: BLE dongle

> 2026-09-19 개정. Zephyr 4.1 이관을 먼저 했으므로 이 phase는 v0.3이 아니라
> 현재 pin된 v0.4 baseline 위에서 수행한다. 그 결과 Phase 3의 1~4번은 이미
> 충족되며, 남는 것은 ESB module을 manifest에 두되 transport는 끄는 작업뿐이다.

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

구현 상태 (2026-09-19): 위 1~8 중 flash를 제외한 전부를 `my-keymap`에
적용했다.

- Shared layout을 `charybdis_layout.dtsi`로 분리했다. physical layout node의
  `kscan` property는 제거하여 각 target의 `chosen zmk,kscan`이 결정하게 했다.
  Dongle은 이 파일만 include하고 `zmk,kscan-mock`을 쓴다.
- `charybdis.dtsi`에는 두 half의 hardware(kscan row, encoder, LED)만 남겼다.
- Central role을 right에서 dongle로 옮겼다. `Kconfig.defconfig`에서 right의
  `ZMK_SPLIT_ROLE_CENTRAL` default를 제거하고 dongle에 peripheral 2,
  `BT_MAX_CONN`/`BT_MAX_PAIRED` 7을 설정했다.
- Trackball은 right에서 `zmk,input-split`(reg 0)로 raw motion만 보내고,
  listener와 processor chain 전체는 dongle로 옮겼다. ZMK는 input listener를
  central에만 build하며 layer state도 central의 것이므로 이 배치가 강제된다.
- Studio와 `studio-rpc-usb-uart` snippet을 right에서 dongle로 옮겼다.
- Keymap에서 half 전용 node 참조(`&spi3`, encoder, `&sensors`, underglow
  chosen 삭제)를 모두 걷어냈다. Dongle에는 그 node들이 없어 build가 깨진다.
  Underglow와 encoder는 이제 shield 파일에서 끈다.
- `build.yaml`은 dongle/left/right/settings_reset 네 target이며 각각
  `artifact-name`으로 role을 명시한다.

Flash 전 필요한 것:

- Dongle용 nice!nano v2 보드 한 장이 추가로 필요하다.
- 세 board 모두에 `settings_reset`을 먼저 flash해야 한다. 기존 bond가 남아
  있으면 dongle이 두 half를 잡지 못한다. 이 과정에서 host 재페어링도 한 번
  발생한다.

### Phase 3: 폐기 (BLE와 NCS는 공존할 수 없다)

> 2026-09-19. 이 phase는 성립하지 않는다. 시도했고, 실패했으며, 그 실패가
> Phase 4의 전제를 바꾼다.

원래 의도는 최종 dependency를 적용하되 split은 BLE로 둬서, dependency로 인한
regression과 transport 전환으로 인한 regression을 분리하는 것이었다. 1~4번과
6번은 Phase 1·2에서 이미 충족되었으므로 남은 것은 ESB module과 NCS를
manifest에 올리는 5번뿐이었다.

Manifest에 `zmk-feature-split-esb`, `badjeff/sdk-nrf`, `nrfconnect/sdk-nrfxlib`
세 project를 추가했다(세 revision 모두 당시 각 branch HEAD와 일치). 결과는
CMake generate 실패다.

```
CMake Error at nrf/subsys/nrf_security/src/CMakeLists.txt:96 (add_library):
  Cannot find source file: /programs/ssl/library/pk.c
No SOURCES given to target: mbedcrypto / psa_core / oberon_psa_driver
```

경로가 `/programs/...`로 시작하는 것은 mbedtls module path 변수가 빈
문자열이기 때문이다. NCS가 workspace에 들어오면 Zephyr의 mbedtls 대신 자신의
`nrf_security`로 BLE crypto를 처리하려 하는데, 그것이 요구하는 NCS용 mbedtls
fork가 manifest에 없다. Build log의 `Generating psa_crypto_config` 단계가
`nrf_security`가 개입한 증거다.

ESB source 자체는 `if(CONFIG_ZMK_SPLIT_ESB)` 안에 있어 컴파일되지 않았다.
깨진 것은 transport가 아니라 NCS와 BLE의 공존이다.

이는 module README의 다음 문장 그대로다.

> UPDATE FOR ZMK 0.4: I'm too stupid to make BLE security libraries in NCS 3.1
> be compiled on Zephyr 4.1.

조사 문서는 이 문장을 runtime topology 제약으로 기록했으나 실제로는 **build
제약**이다. 저자의 동작하는 reference config가 `CONFIG_ZMK_BLE=n`인 것도 같은
이유다.

결론: NCS를 manifest에 두는 것과 BLE를 켜는 것은 양립하지 않는다. 따라서 이
phase는 폐기하고, dependency 추가와 transport 전환은 Phase 4에서 한 번에
수행한다. 분리 검증은 불가능하다는 것이 이 phase의 산출물이다.

Commit `e30caee`에서 시도했고 `HEAD`에서 revert했다.

### Phase 3 (원안, 참고용): Pinned Zephyr 4.1 stack, BLE 유지

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
