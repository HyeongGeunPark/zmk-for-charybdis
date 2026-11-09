# Charybdis BLE 동글 구성

> 대상 브랜치: `my-keymap`<br>
> 현재 구성이 왜 이렇게 되어 있는지와, 구성을 바꿀 때 다시 밟기 쉬운 함정을
> 기록한다. 값의 출처는 각 설정 파일의 주석이며, 이 문서는 그 배경을 묶어 둔다.

## 1. 구성

```text
left half  --\
              BLE split (bond + 암호화) --> nice!nano v2 dongle --> USB 또는 BLE --> host
right half --/                                   central
```

| Target | ZMK 역할 | 하는 일 |
| --- | --- | --- |
| `charybdis_dongle` | central | keymap/layer/behavior 처리, host HID, ZMK Studio(USB), pointer 가공 |
| `charybdis_left` | peripheral | key position 송신 |
| `charybdis_right` | peripheral | key position과 PMW3610 raw motion 송신 |
| `settings_reset` | - | topology를 바꾸거나 처음 flash할 때 세 board 모두에 먼저 굽는다 |

- Central은 동글 하나뿐이다. `Kconfig.defconfig`가 동글에만
  `ZMK_SPLIT_ROLE_CENTRAL`을 켜고, peripheral 2개와 host profile 5개를 위해
  `BT_MAX_CONN`/`BT_MAX_PAIRED`를 7로 둔다.
- Split hop은 BLE connection interval인 약 7.5 ms이고, 동글의 USB poll
  interval은 1 ms다.
- 두 번째 keyboard set은 별도 설정이 필요 없다. BLE bonding이 set을 구분한다.

### 1.1 DTS 분리

- `charybdis_layout.dtsi`: 세 target 공통. 56-position matrix transform,
  physical layout, CPI behavior. Physical layout에는 `kscan` property를 두지
  않고 각 target의 `chosen zmk,kscan`이 정하게 한다.
- `charybdis.dtsi`: 두 half의 hardware(kscan row, encoder, LED). 동글은 이
  파일을 include하지 않고 `zmk,kscan-mock`을 쓴다.
- Keymap은 세 target이 공유한다. 한쪽에만 있는 node(`&spi3`, encoder,
  `&sensors`, underglow chosen)를 keymap에서 참조하면 동글 build가 깨진다.
  Underglow와 encoder는 shield 파일에서 끈다.

### 1.2 트랙볼 경로

1. Right: `zmk,input-split`(reg 0)에 `device = <&trackball>`을 지정해 raw
   motion만 보낸다.
2. Dongle: 같은 reg의 proxy를 두고 `zmk,input-listener`가 그것을 구독한다.
3. Scroll/snipe 같은 가공은 전부 동글 listener의 layer별 processor chain이다.

Listener가 동글에 있어야 하는 이유는 두 가지다. ZMK는 input listener를
central에만 build하고, layer state도 central의 것이다. Listener의 `layers`는
raw layer 번호이므로 keymap의 `SYMBOLS`/`SCROLL`/`SNIPE` define과 손으로
맞춘다.

### 1.3 Studio와 battery

- Studio와 `studio-rpc-usb-uart` snippet은 동글에만 있다. Studio BLE
  transport는 끈다.
- 두 half의 battery 잔량은 동글이 가져와 host에 대신 보고한다
  (`ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING`/`_PROXY`).

### 1.4 Deep sleep

- 두 half는 입력 없이 5분이 지나면 deep sleep(전원 off)에 들어간다. 무선
  마우스가 흔히 쓰는 시간이다. 설정은 `charybdis_left.conf`와
  `charybdis_right.conf`에 같은 값으로 두고, 동글에는 넣지 않는다. 동글에는
  깨울 키가 없다.
- 깨우는 것은 키 입력뿐이다(`charybdis.dtsi`의 kscan `wakeup-source`).
  트랙볼로는 깨어나지 않는다. 깨운 키 자체는 보통 입력되지 않고, 깨어난 half는
  동글에 다시 연결해야 한다.
- Right half에서는 트랙볼 움직임도 입력으로 친다. `ZMK_POINTING`이 켜져 있으면
  모든 input event가 idle timer를 초기화하기 때문이다. Left half는 자기 키
  입력만 센다.
- 깨어나는 것은 재부팅이므로 runtime CPI가 400으로 돌아간다(§3).

## 2. 트랙볼 드라이버

[badjeff/zmk-pmw3610-driver](https://github.com/badjeff/zmk-pmw3610-driver)를
exact SHA로 pin한다.

- Compatible `pixart,pmw3610-alt`와 `CONFIG_PMW3610_ALT_*` namespace를 써서
  Zephyr 4.1 native `pixart,pmw3610` driver와 충돌하지 않는다.
- `cpi`, `swap-xy`, `invert-x`, `invert-y`가 devicetree 속성이다. 센서가
  회전 장착되어 있어 `swap-xy` + `invert-x` + `invert-y`를 쓴다. 이전
  software mapping `(x, y) = (-raw_y, -raw_x)`와 같다.
- Scroll, snipe, automouse는 driver 기능이 아니다. §1.2의 processor chain으로
  구성한다. 현재 scroll은 SYMBOLS와 SCROLL layer에서 수평만 반전하고
  `zip_scroll_scaler 1 2`로 줄인다(smooth scrolling 기준, 하드웨어에서 맞춘
  값). Snipe는 `zip_xy_scaler 1 2`다.
- `CONFIG_PMW3610_ALT_INIT_POWER_UP_EXTRA_DELAY_MS`: nice!nano v2 + ext-power
  조합에서 cold boot 시 `Incorrect product id 0xFF`로 초기화가 실패한다.
  1000 → 300 → 100으로 줄였고 100은 cold boot에서 검증했다.
- `CONFIG_PMW3610_ALT_REST3_SAMPLE_TIME_MS=300`: 오래 멈춘 뒤 첫 움직임을
  놓치는 시간을 줄인다. Driver 기본값은 500 ms다.

### 2.1 Sampling rate

- 현재는 driver 기본값인 8 ms(125 Hz)다.
- PMW3610의 하드웨어 상한은 약 250 Hz다. Performance register에 1 ms mode는
  없다.
- 250 Hz로 올리려면 trackball node에 `force-awake`와 `force-awake-4ms-mode`를
  함께 넣는다. 다만 `force-awake`는 ZMK가 active인 동안 센서의 downshift를
  막아 right half의 battery 소모가 늘어난다. 동글을 통해 잔량을 볼 수 있으니
  소모를 관찰한 뒤 결정한다.

## 3. Runtime CPI

POINTER layer의 `&dpi (-1)` / `&dpi 1`은 input processor 배율이 아니라 센서의
실제 CPI를 바꾼다. Driver가 `sensor_driver_api.attr_set`으로
`PMW3610_ALT_ATTR_CPI`(enum의 첫 값, `attr = <0>`)를 노출하므로 driver는
수정하지 않았다.

Behavior module은 fork해서 쓴다:
[HyeongGeunPark/zmk-behavior-sensor-attr-cycle](https://github.com/HyeongGeunPark/zmk-behavior-sensor-attr-cycle).
Upstream 그대로는 이 구성에서 동작하지 않는다.

- Locality가 `EVENT_SOURCE`라 키를 누른 half에서 실행된다. CPI 키는 왼쪽,
  센서는 오른쪽이므로 `GLOBAL`로 바꿨다.
- `sensor_device`가 required phandle이라 센서가 없는 동글과 left가 link에
  실패한다. Optional로 바꾸고 NULL guard를 넣었다. 센서가 없는 target도
  index는 갱신해 서로 어긋나지 않는다.
- `param1`이 unsigned라 `-1`이 0xFFFFFFFF로 도착해 역방향이 동작하지 않았다.
  Signed로 계산한다.

단계는 400/600/800/1200이고 첫 값이 overlay의 `cpi`와 같아 현재 상태에서
cycle이 시작한다. 저장하지 않으므로 부팅할 때마다 400에서 시작한다. Snipe는
선택된 CPI에 비례해 따라간다.

## 4. 함정

### 4.1 DTS는 Kconfig보다 먼저 처리된다

Zephyr는 devicetree를 Kconfig보다 먼저 preprocess한다. 그래서 keymap이나
overlay의 `#if defined(CONFIG_SHIELD_CHARYBDIS_RIGHT)` 같은 guard는 항상
거짓이고, 그 블록은 build error 없이 사라진다. Shield별 DTS는 그 shield의
overlay에 직접 둔다. 예전 keymap의 `&trackball` override가 실제로 한 번도
적용되지 않았던 원인이 이것이다.

### 4.2 Split behavior node 이름은 8자 이하

Central이 peripheral로 behavior를 보낼 때 이름을 고정 길이 field에 담는다
(`ZMK_SPLIT_RUN_BEHAVIOR_DEV_LEN` = 9, 8자 + null). 더 길면 잘린 채 도착하고
peripheral은 `-EINVAL`로 실패한다. Build 경고가 없고 증상은 "키를 눌러도
아무 일이 없다"뿐이다. Peripheral의 USB log에서만 보인다.

```
split_svc_run_behavior: dpi_cycl with params 1 0: pressed? 1
<err> zmk: Failed to invoke behavior dpi_cycl: -22
```

처음 이름 `dpi_cycle`(9자)이 이 경우였고 `dpi_cyc`로 줄여 해결했다.

### 4.3 동글 LED가 깜빡인다

동글 LED가 약 0.5초 주기로 pulse하며 펌웨어로 끌 수 없다. 같은 board인 두
half는 깜빡이지 않고, P0.15를 gpio-hog로 low에 고정해도 멈추지 않았다.
Battery 없이 USB 전원만 받으면 charging IC가 충전 시도와 완료 판단을 반복하는
것으로 본다. 불투명 tape를 붙이거나 시야 밖에 둔다.

## 5. Build와 flash

- Build는 GitHub Actions에서만 한다. 이 PC에는 west/Zephyr SDK workspace가
  없다.
- `config/west.yml`의 ZMK revision과 `.github/workflows/build.yml`의 reusable
  workflow ref는 같은 SHA여야 한다. 하나만 올리지 않는다.
- `README.md`와 `docs/**`만 바뀐 push는 build를 돌리지 않는다. 수동 build는
  `workflow_dispatch`로 한다.
- 처음 flash하거나 topology를 바꿀 때는 세 board 모두에 `settings_reset`을
  먼저 굽고 left, right, 동글 순으로 production image를 굽는다. 기존 bond가
  남아 있으면 동글이 두 half를 잡지 못하고, host 재페어링이 한 번 생긴다.
- 동글에는 키가 없으므로 UF2 bootloader는 물리 double-reset으로만 들어간다.
