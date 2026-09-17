# Charybdis 동글 및 ESB 전환 조사 기록

> 조사 기준일: 2026-09-17<br>
> 조사 대상: 이 ZMK config 저장소, 인접 PMW3610 드라이버 저장소,
> ZMK 및 `zmk-feature-split-esb` 공개 코드·문서, 현재 PC의 빌드 환경<br>
> 상태: 관찰·설계 기록이며 아직 동글/ESB 펌웨어를 구현한 결과가 아니다.

## 1. 결론 요약

- 현재 오른쪽 하프가 ZMK BLE central이며 PC와 USB HID로 연결된다.
- 동글 구성에서는 nice!nano v2 동글이 유일한 central이 되고 좌·우 하프는
  모두 peripheral이 되어야 한다.
- 오른쪽 PMW3610은 `zmk,input-split`을 통해 동글로 전달해야 한다. 현재의
  오른쪽 direct input listener는 peripheral 구성에서 동작하지 않는다.
- 현재 PMW3610 runtime behavior는 central-local이므로 동글 구성에서 CPI,
  snipe, drag-scroll 명령이 깨진다. 인접 드라이버 수정이 필수다.
- 현재 USB-facing central의 HID poll interval은 이미 1 ms다. ESB의 주된
  이점은 7.5 ms 단위 BLE split hop을 교체하는 것이다.
- PMW3610은 현재 약 125 fresh report/s이며 현재 드라이버에서 현실적인
  상한은 약 250 Hz다. USB/ESB 1 ms와 sensor sample 1 kHz는 다른 목표다.
- `zmk-feature-split-esb` 최신 계열은 USB-only 동글 구성을 지원하지만
  릴리스 태그가 없는 실험적 모듈이다. ZMK, ESB, NCS, nrfxlib을 exact SHA로
  고정해야 한다.
- 가장 안전한 진행 순서는 드라이버 보완, ZMK v0.3 BLE 동글 검증, Zephyr
  4.1 포팅 검증, 마지막 ESB-only 전환이다.

## 2. 현재 저장소 조사

### 2.1 Git 및 빌드 기준선

조사 당시 상태는 다음과 같았다.

- 브랜치: `my-keymap`
- 커밋: `33b21d0` (`origin/my-keymap`과 동일)
- 작업 트리: clean
- ZMK manifest revision: `v0.3`
- PMW3610 driver revision:
  `75631d0abb94a47139afac0d4bb13bade3e3f13f`
- workflow: ZMK reusable workflow `@v0.3`
- build matrix: left, right, `settings_reset`

마지막으로 확인한 정상 기준 빌드는 세 matrix firmware build가 모두 성공했고,
생성된 UF2 세 개가 하나의 `firmware` artifact에 포함되었다.

- [GitHub Actions run 30211214147](https://github.com/HyeongGeunPark/zmk-for-charybdis/actions/runs/30211214147)

이 `firmware` artifact와 SHA는 실제 전환 전에 내려받아 각 UF2 checksum과 함께
보관해야 한다.
원래의 두 보드/right-central 구성으로 돌아갈 때 사용할 rollback 기준이다.

### 2.2 현재 split 역할

`config/boards/shields/charybdis/Kconfig.defconfig`에서 오른쪽 shield만
`CONFIG_ZMK_SPLIT_BLE_ROLE_CENTRAL=y`를 선택한다. 양쪽 모두 split 자체는
활성화한다.

공통 transform은 총 56개 key position을 표현한다.

- 4행 × 12열: 48개
- thumb cluster: 5개 + 3개

각 half는 물리적으로 6열을 스캔한다. 오른쪽 overlay가 column offset 6을
적용하고 왼쪽은 offset이 없다. 동글 central도 키가 없어도 이 전체 logical
transform과 physical layout을 동일한 node 이름으로 가져야 한다.

[ZMK 공식 동글 문서](https://zmk.dev/docs/hardware-integration/dongle)는 keyless
central에 `zmk,kscan-mock`을 사용하고 모든 part가 동일한 transform/layout을
가져야 한다고 설명한다.

### 2.3 현재 USB 및 BLE timing

성공한 baseline artifact의 생성 `.config`를 확인한 결과:

- 오른쪽: `CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y`
- BLE preferred split interval: 6 × 1.25 ms = 7.5 ms
- USB HID polling interval: `CONFIG_USB_HID_POLL_INTERVAL_MS=1`

따라서 현재도 USB endpoint 자체는 1 ms로 설정되어 있다. ESB의 목표는
USB 설정을 처음 1 ms로 만드는 것보다, BLE split hop을 저지연 ESB hop으로
바꾸는 데 있다.

### 2.4 공통 config와 keymap

조사 당시 주요 설정은 다음과 같다.

- press/release debounce: 7 ms
- BLE passkey pairing
- BLE TX power: +8 dBm
- battery reporting 및 settings 활성화
- pointing/runtime control 활성화
- ZMK Studio 활성화, Studio BLE transport 비활성화
- 오른쪽 build에만 `studio-rpc-usb-uart` snippet 적용
- 오른쪽 PMW 설정: `CONFIG_PMW3610_POLLING_RATE_125_SW=y`

Pointer layer에는 다음 runtime PMW 동작이 있다.

- normal CPI 증가/감소
- snipe CPI 증가/감소
- snipe hold
- drag scroll

Danger layer에는 BLE profile 선택·삭제, BLE/USB output 선택, 양쪽 bootloader
binding이 있다. 최종 BLE-off firmware에서는 BT binding과 `OUT_BLE`가
무의미하므로 제거하거나 `&none`으로 바꿔야 한다. `OUT_USB`와 half별
bootloader binding은 유지할 수 있다.

Keymap은 left encoder/SPI를 다시 disable하고 RGB chosen property를 지운다.
따라서 encoder와 RGB는 현재 보존해야 할 활성 기능이 아니다.

## 3. PMW3610 드라이버 조사

### 3.1 이벤트 생성 방식

인접 `zmk-pmw3610-driver`는 timer polling 방식이 아니다.

1. MOTION GPIO가 assert된다.
2. ISR이 interrupt를 잠시 끈다.
3. system workqueue에 motion work를 제출한다.
4. burst read 후 X와 Y를 Zephyr input event로 report한다.
5. interrupt를 다시 활성화한다.

한 motion sample에서 X는 `sync=false`, Y는 `sync=true`로 두 input event가
생성된다. 250 Hz sensor mode에서는 최대 약 500 input event packet/s가
split input 경로에 들어갈 수 있으므로 input queue와 system workqueue의
여유가 중요하다.

### 3.2 125/250 Hz와 하드웨어 한계

드라이버 Kconfig가 제공하는 모드는 250, 125, 125 software다. 현재 사용하는
125 software와 250 mode는 모두 PMW3610 `PERFORMANCE` register에 `0x0d`를
쓴다. 이 값은 run period를 4 ms로 정한다. 125 software mode는 연속된 두
delta를 합쳐 한 번만 report한다.

결과적으로:

- 현재: 약 125 fresh report/s
- 250 mode: 약 250 fresh report/s
- ESB/USB가 1 ms여도 PMW3610 fresh sample은 약 250/s

[PMW3610 data sheet](https://trackballs.eu/media/Nakabayashi/Digio2/PMW3610DM-SUDU.pdf)의
Performance register에도 1 ms mode는 없다. 일부 low-speed position mode의
최단 period가 2 ms이지만 다른 velocity/position mode는 4 ms다. 모든 동작
구간에서 1,000개의 독립 sample/s를 만드는 것은 불가능하다.

Zephyr 4.1의 native PMW3610 driver도 초기값으로 `PERFORMANCE=0x0d`를 사용한다.
센서를 1 ms마다 읽거나 USB에 빈/동일 report를 더 자주 보내는 것은 true
1,000 fresh sensor sample/s가 아니다.

### 3.3 동글 전환 시 runtime behavior가 깨지는 이유

현재 `behavior_pmw3610.c`는 locality를 `BEHAVIOR_LOCALITY_CENTRAL`로
고정한다. right-central일 때는 central에 sensor가 있으므로 맞지만,
dongle-central에는 `pixart,pmw3610` node가 없어 runtime 명령이 `-ENODEV`로
끝난다.

단순히 `EVENT_SOURCE`로 바꿔도 해결되지 않는다. 여러 PMW control key가
왼쪽 물리 half에 있으므로 명령 source가 sensor 없는 왼쪽이 되기 때문이다.

필요한 수정은 다음과 같다.

- locality를 `GLOBAL`로 변경한다.
- sensor 없는 dongle/left에서는 성공 no-op으로 처리한다.
- sensor가 있는 right peripheral만 실제 명령을 실행한다.
- central에서 Shift 상태를 먼저 해석해 INC/DEC parameter를 정규화한다.

마지막 항목이 필요한 이유는 현재 driver가 명령을 실행하는 board에서
`zmk_hid_get_explicit_mods()`를 읽어 Shift 반전을 판단하기 때문이다. right
peripheral에는 dongle central의 HID modifier state가 보장되지 않는다.
`binding_convert_central_state_dependent_params`에서 방향을 확정한 뒤
forward해야 한다.

### 3.4 Layer state와 automouse

현재 driver 내부에는 local active layer를 읽는 scroll/snipe 처리와 local
automouse layer activation이 있다. right가 peripheral이면 local layer state는
dongle의 keymap state와 다르다.

현재 keymap은 scroll/snipe layer list를 비우고 runtime hold/drag behavior를
사용하며 automouse를 끈 상태이므로 이번 migration의 직접 blocker는 아니다.
향후 이 기능들을 다시 켠다면 dongle의 `zmk,input-listener`와 input processor로
옮겨야 한다.

### 3.5 Zephyr 4.1 native driver 충돌

ZMK main/Zephyr 4.1에는 이미 `pixart,pmw3610` native driver가 있다. 현재
external driver를 그대로 올리면 같은 compatible/binding/device instance를
두 구현이 소유할 수 있다.

이번 migration에서 기존 runtime feature를 보존하려면 custom fork를 다음과
같이 port하는 것이 가장 좁은 변경이다.

- DTS compatible: `pixart,pmw3610-alt`
- Kconfig namespace: `PMW3610_ALT_*`
- 기존 keymap의 PMW dt-binding 상수와 `zmk,behavior-pmw3610` ABI 유지

ESB가 안정된 뒤 native driver와 central input processor로 정리하는 작업은
별도 후속 과제로 분리한다.

## 4. ZMK 동글 및 pointing 조사

### 4.1 역할과 데이터 흐름

목표 역할은 다음과 같다.

| 장치 | ZMK 역할 | 입력 |
| --- | --- | --- |
| USB dongle | central | split event를 처리하고 USB HID report 생성 |
| left half | peripheral | matrix/key event 송신 |
| right half | peripheral | matrix/key와 PMW input event 송신 |

동글은 keyboard 전체 keymap/layer/behavior를 처리하는 keyless central이다.
동글이 없으면 두 peripheral은 PC에 직접 연결할 수 없다.

### 4.2 필요한 input-split 구조

Shared DTS에 disabled-by-default `zmk,input-split` node와 central listener를
정의한다. 예를 들어 한 trackball은 모든 part에서 동일하게 `reg=<0>`을
사용한다.

- right overlay: proxy에 `device=<&trackball>`을 지정하고 enable
- dongle overlay: proxy와 listener를 enable하고 listener가 proxy를 구독
- left overlay: node는 정의만 유지하고 disable
- 기존 right direct listener: 제거

공식 구조는 [ZMK pointing-device integration](https://zmk.dev/docs/hardware-integration/pointing)에
설명되어 있다. 과거 third-party split input relay는 현재 ZMK의 built-in
`zmk,input-split`을 사용할 때 필요하지 않다.

### 4.3 Studio 이동

Studio USB transport와 `studio-rpc-usb-uart` snippet은 USB-facing central에
있어야 한다. 따라서 right build에서 dongle build로 옮기고 halves에서는
Studio/host USB를 끈다.

### 4.4 Settings reset

Central role과 split bonding을 바꿀 때 기존 persistent settings가 남아 있으면
pairing/role 문제가 생길 수 있다. [ZMK dongle guide](https://zmk.dev/docs/hardware-integration/dongle)도
새 topology를 flash하기 전에 모든 device에 `settings_reset`을 적용하도록
안내한다. Dongle, left, right 세 장치 모두 reset 대상이다.

## 5. `zmk-feature-split-esb` 조사

### 5.1 지원 상태

대상 모듈은 [badjeff/zmk-feature-split-esb](https://github.com/badjeff/zmk-feature-split-esb)다.
Nordic Enhanced ShockBurst를 ZMK split transport로 추가한다.

- dongle: primary receiver(PRX)
- halves: primary transmitter(PTX)
- radio: 2 Mbps
- peripheral -> central: event uplink
- central -> peripheral: ACK payload command downlink

현재 문서상 지원 topology는 USB-only dongle + ESB-only peripherals 한 가지다.
BLE host와 ESB를 동시에 사용하는 설명은 README에서 취소선 처리되어 있고,
NCS 3.1/Zephyr 4.1 security library와 radio resource 문제로 지원 경로가 아니다.

저장소에는 tag/release가 없고 radio, queue, race, hopping, command ACK 관련
수정이 계속 들어왔다. `main`이나 branch 이름을 그대로 manifest에 쓰면
재현 가능한 firmware가 되지 않는다.

### 5.2 조사한 ESB branch

| Branch | 조사 당시 HEAD | 특징 |
| --- | --- | --- |
| `zmk-0.3` | `1068e7945a9d95c491af0853a89fcf10aeb26d0d` | 현재 ZMK/driver와 가까우나 최신 hopping, type별 retry, auto-heal, peripheral-count 및 command ACK fix 부족 |
| `zmk-0.4` | `1f4cd4558bb9e0626ec2507f334f239862af859d` | Zephyr 4.1 전환용 중간 branch이며 공식 ZMK v0.4 release가 아님 |
| `main` | `314c7cbaf4a74e1add1d6ffc8249de3e29965b8c` | 최신 조사 시점의 ACK pipe fix와 reliability 기능 포함 |

`zmk-0.3`으로 바로 ESB bring-up하는 것은 가능하지만 central peripheral count와
최신 ACK/retry fix를 private backport해야 한다. BLE dongle로 topology를 먼저
검증하고 최종적으로 pinned main stack으로 가는 편이 유지보수 위험이 낮다.

### 5.3 조사 기준 호환 snapshot

2026-09-17에 확인한 exact revisions:

| Project | Revision |
| --- | --- |
| `zmkfirmware/zmk` | [`641514a97db345f499dd50b0360e594270f008fe`](https://github.com/zmkfirmware/zmk/commit/641514a97db345f499dd50b0360e594270f008fe) |
| `badjeff/zmk-feature-split-esb` | [`314c7cbaf4a74e1add1d6ffc8249de3e29965b8c`](https://github.com/badjeff/zmk-feature-split-esb/commit/314c7cbaf4a74e1add1d6ffc8249de3e29965b8c) |
| `badjeff/sdk-nrf` | [`9b3d2623fdcd9c0fd0284f860beea924568c9826`](https://github.com/badjeff/sdk-nrf/commit/9b3d2623fdcd9c0fd0284f860beea924568c9826) |
| `nrfconnect/sdk-nrfxlib` | [`dfadf17305d8f000eda9aa74a5b9ff1c5647a23e`](https://github.com/nrfconnect/sdk-nrfxlib/commit/dfadf17305d8f000eda9aa74a5b9ff1c5647a23e) |

ESB author sample의 ZMK fork HEAD와 upstream ZMK의 위 commit은 동일한 commit
object였다. 따라서 final config는 upstream ZMK URL과 exact SHA를 사용할 수
있다.

[ZMK pinning 안내](https://zmk.dev/blog/2025/06/20/pinned-zmk)도 floating main
대신 revision 고정을 권장한다.

### 5.4 Zephyr 4.1/HWMv2

ZMK main은 Zephyr 4.1/HWMv2로 이동했다. nice!nano v2 target은 기존
`nice_nano_v2`에서 `nice_nano@2.0.0//zmk` 또는 short form
`nice_nano//zmk`로 바뀐다.

- [ZMK Zephyr 4.1 update](https://zmk.dev/blog/2025/12/09/zephyr-4-1)

조사 시점에 공식 `v0.4` tag는 없었다. ESB의 `zmk-0.4` branch 이름을 ZMK
정식 release로 오해하면 안 된다.

### 5.5 Address, ID, count

세 장치는 같은 `zmk,esb-split` base address와 prefix를 compile해야 한다.
README의 sample address를 복사하지 말고 keyboard 세트마다 random address를
생성해야 한다.

권장 assignment:

- left ID: 1
- right ID: 2
- physical peripheral count: 2
- `CONFIG_ZMK_SPLIT_ESB_PERIPHERAL_COUNT`: 3

마지막 값이 3인 이유는 source ID를 array index로 사용하는 코드가 있어 ID
1과 2에 slot 0..2가 필요하기 때문이다. README의 "max ID 이상"이라는 표현만
따라 2로 두는 것보다 안전하다.

ESB-only battery proxy는 이름에 BLE가 남아 있는 기존 central 설정을 재사용한다.
Dongle에는 `CONFIG_ZMK_BATTERY_REPORTING=y`,
`CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING=y`,
`CONFIG_ZMK_SPLIT_BLE_CENTRAL_PERIPHERALS=2`, `CONFIG_BT_MAX_PAIRED=2`를
명시해야 한다. 실제 split transport는 이 경우에도 ESB이며 BLE는 disabled다.

ESB address는 인증 key가 아니다. 조사한 구현에는 BLE bonding에 해당하는
authentication/encryption이 없다. 주소는 인접 ESB set과의 충돌 방지용이다.

### 5.6 초기 radio/queue 설정

조사한 module README/Kconfig에서 중요한 baseline은 다음과 같다.

- ACK enabled
- application CRC enabled
- 2 Mbps ESB
- retransmit delay 600 us
- retransmit count 3
- RF channel hopping enabled
- input-event application retry 0
- key/sensor/battery event는 loss-sensitive retry
- command retry enabled
- ESB max payload 48
- protocol message queue 64
- event buffer 64
- command buffer 16
- `ESB_TX_FIFO_SIZE=1`
- system workqueue stack 4096
- input thread stack 4096
- input queue 256

README에는 hopping channel count 4라고 쓰면서 예시에 5, 23, 41, 59, 77 다섯
값을 적은 불일치가 있다. 최초 bring-up에서는 pinned module default를 유지하고
실제 RF trace 후에만 조정해야 한다.

Pointer retry 0은 stale motion을 늦게 전달하지 않는 대신 혼잡 환경에서 cursor
delta를 잃을 수 있는 선택이다. Key event는 절대 잃거나 stuck 상태가 되면 안
되므로 loss-sensitive retry와 auto-heal을 유지해야 한다.

### 5.7 Peripheral count build workaround

최신 ESB module은 CMake에서 ZMK central header를 직접 수정하여 ESB peripheral
count를 반영한다. Shared local checkout에서 여러 variant를 병렬 build하면 서로
영향을 줄 수 있다. Dongle, left, right는 각각 pristine/isolated CI job에서
build해야 한다.

### 5.8 알려진 이슈와 수정 이력

조사에 참고한 주요 항목:

- [Behavior command 전달 issue #5](https://github.com/badjeff/zmk-feature-split-esb/issues/5)
- [Radio busy/ACK issue #8](https://github.com/badjeff/zmk-feature-split-esb/issues/8)
- [Dongle display assumption issue #2](https://github.com/badjeff/zmk-feature-split-esb/issues/2)
- [Encoder bounce issue #7](https://github.com/badjeff/zmk-feature-split-esb/issues/7)
- [최신 조사 시점 command ACK pipe fix](https://github.com/badjeff/zmk-feature-split-esb/commit/314c7cbaf4a74e1add1d6ffc8249de3e29965b8c)
- [MPSL hard-fault fix](https://github.com/badjeff/zmk-feature-split-esb/commit/1347fb4589de)
- [Race/buffer fix](https://github.com/badjeff/zmk-feature-split-esb/commit/d45ec822427c)

Central-to-peripheral runtime PMW command가 ACK payload를 사용하므로 press와
release가 모두 right에 도달하는지 stress test해야 한다. 물리 link status와
내부 connection status가 항상 일치한다고 가정해서도 안 된다.

### 5.9 가장 가까운 공개 사례

Charybdis 전용 공식 migration은 찾지 못했다. 가장 가까운 author example은
dongle, 양 peripheral, pointing-device variant를 포함한
[Donki36 ESB-only config](https://github.com/badjeff/zmk-config/tree/esb-shield-only/boards/shields/donki36)다.

## 6. 1 kHz의 정확한 의미

전체 path는 다음 단계로 구성된다.

```text
switch/PMW sample
  -> Zephyr input and ZMK behavior processing
  -> ESB queue/transmit/retry
  -> dongle HID report coalescing
  -> USB 1 ms frame
  -> host scheduling
```

따라서 아래는 서로 다른 측정값이다.

- USB endpoint `bInterval=1 ms`
- ESB가 매 1 ms 변화 event를 sustain하는지
- PMW3610 fresh sample rate 약 250 Hz
- switch debounce 7 ms
- event-to-host end-to-end latency와 tail latency

ESB README가 주장하는 것은 minimum latency 1 ms이며 sustained 1,000
report/s의 독립 측정 자료는 아니다. `CONFIG_USB_HID_POLL_INTERVAL_MS=1`만
확인하고 true 1 kHz라고 부르면 안 된다.

검증에는 다음이 필요하다.

- USBView/USBPcap으로 endpoint descriptor 확인
- PMW 한계를 우회한 test-only 1 ms synthetic peripheral input source
- ESB TX/RX/drop/queue counter 비교
- USB packet timestamp capture
- real trackball continuous-motion 측정
- typing + motion 동시 stress test

Transport benchmark가 1 kHz를 통과해도 실제 trackball fresh data는 약 250 Hz다.
실제 sensor 1 kHz가 필요하면 PMW3610, lens/footprint, PCB, power 조건과 driver를
함께 교체해야 한다.

## 7. 전력, recovery, security

- Dongle PRX는 계속 수신하지만 USB powered이므로 전력 부담이 작다.
- Peripheral PTX는 주로 event가 있을 때 송신하지만 +8 dBm, 250 Hz trackball,
  retry/hopping 설정에 따라 half battery 소모가 달라진다. 실제 측정 전에는
  BLE보다 몇 배 낫다고 단정하지 않는다.
- ESB OTA provisioning/update 기능은 없다.
- Nice!nano UF2/double-reset recovery는 유지할 수 있다.
- Dongle에는 key event source가 없으므로 physical reset 접근성을 반드시
  남긴다.
- 고정 ESB address는 encryption/authentication을 제공하지 않는다.

## 8. 현재 PC의 실행 여건

공개 문서에 불필요한 사용자 경로나 USB serial은 기록하지 않았다. 조사 당시
재현에 필요한 상태는 다음과 같다.

- Windows에 Git, GitHub CLI, CMake, Ninja, Python이 설치되어 있었다.
- GitHub CLI 인증으로 이 저장소의 Actions를 조회·운영할 수 있었다.
- `west`, local ZMK/Zephyr workspace, Zephyr SDK, `nrfutil`, OpenOCD, J-Link,
  Docker는 이 project용으로 준비되어 있지 않았다.
- WSL2 Ubuntu 22.04/24.04는 있었지만 west/SDK workspace는 없었다.
- 조사 시 nice!nano/ZMK UF2 device는 연결되어 있지 않았다.

따라서 최초 재현 가능한 build 경로는 GitHub Actions다. Low-level logging이
필요하면 두 repository 밖에 WSL2 Ubuntu 24.04 west workspace를 별도로 만들고
mutable source tree를 build variant 간 공유하지 않는 것이 안전하다.

## 9. 최종 판단

기술적으로 nice!nano v2 USB dongle + 두 nRF52840 ESB peripheral 구성은 가능할
것으로 판단한다. 다만 module의 release maturity와 driver/toolchain migration을
고려하면 다음을 지켜야 한다.

1. 기존 working firmware를 보존한다.
2. Runtime PMW behavior를 먼저 transport-safe하게 만든다.
3. 현재 ZMK v0.3에서 BLE dongle topology와 input-split을 검증한다.
4. Pinned Zephyr 4.1 stack에서도 BLE dongle을 다시 검증한다.
5. 마지막에 transport만 ESB-only로 바꾼다.
6. USB descriptor와 synthetic traffic을 실제 capture하기 전에는 true 1 kHz라고
   부르지 않는다.

구체적인 구현 순서, 설정 contract, 합격 기준, flashing과 rollback은
[migration plan](dongle-esb-migration.md)에 정리한다.

## 10. 출처

- [ZMK Keyboard Dongle](https://zmk.dev/docs/hardware-integration/dongle)
- [ZMK Split Keyboards](https://zmk.dev/docs/features/split-keyboards)
- [ZMK Pointing Device Integration](https://zmk.dev/docs/hardware-integration/pointing)
- [ZMK Input Processors](https://zmk.dev/docs/keymaps/input-processors)
- [Pin your ZMK version](https://zmk.dev/blog/2025/06/20/pinned-zmk)
- [ZMK Zephyr 4.1 Update](https://zmk.dev/blog/2025/12/09/zephyr-4-1)
- [zmk-feature-split-esb](https://github.com/badjeff/zmk-feature-split-esb)
- [Donki36 ESB-only example](https://github.com/badjeff/zmk-config/tree/esb-shield-only/boards/shields/donki36)
- [Nordic ESB overview](https://docs.nordicsemi.com/r/bundle/nrf5_sdk_v11.0.0/page/esb_users_guide.html)
- [PMW3610 data sheet](https://trackballs.eu/media/Nakabayashi/Digio2/PMW3610DM-SUDU.pdf)
