# Half가 멈추는 문제: 조사 기록

> 브랜치: `debug/half-halt` (`my-keymap`의 `e8fc856`에서 분기)<br>
> 작성: 2026-11-23<br>
> 상태: 조치 하나를 적용하고 관찰 중이다. 재발하면 이 문서의 §6에서 다시
> 시작한다.

적용한 조치 자체는 `docs/dongle.md` §4.5에 있다. 이 문서는 그 조치로 덮이지
않는 원인 후보와, 재발했을 때 할 일을 기록한다.

표기: **[확인]** 은 소스나 빌드 출력에서 직접 본 것, **[보고]** 는 분석
서브에이전트의 보고를 다시 검증하지 않고 옮긴 것, **[추정]** 은 추론이다.

## 1. 증상과 경과

- 2026-11-09: `4dd95d7` 빌드를 세 board에 올렸다.
- 2026-11-19: right half가 동글에서 끊긴 뒤 돌아오지 않았다.
- 2026-11-20: left half가 같은 증상을 보였다. Reset 버튼을 누르면 곧바로
  연결된다. 이날 동글은 USB에서 다시 잡힌 기록이 없다.
- 그 뒤 재발했을 때, 끊긴 half를 reset 전에 USB로 PC에 꽂아도 장치로 잡히지
  않았다. 정상 half는 `VID_1D50&PID_615E`로 잡힌다.
- 2026-11-22: `c6e5f15`로 아래 설정을 세 target에 넣고 board에 올렸다.

  ```
  CONFIG_BT_CTLR_ADVANCED_FEATURES=y
  CONFIG_BT_CTLR_ASSERT_OVERHEAD_START=n
  ```

결론: half의 CPU가 멈춘다. BLE만 멈춘 것이 아니다. 멈춘 당시의 log는 없다.

## 2. 왜 멈추면 돌아오지 않는가 [확인]

- 이 Zephyr의 기본 `k_sys_fatal_error_handler`(`kernel/fatal.c`)는 재부팅하지
  않고 `arch_system_halt`로 영원히 멈춘다.
- ZMK는 이 handler를 바꾸지 않는다. Watchdog도 없고,
  `CONFIG_RESET_ON_FATAL_ERROR`는 이 fork에 없다.
- 그래서 k_oops, hard fault, 오류로 끝나는 stack overflow는 밖에서 보면 모두
  같은 증상이다.

## 3. 적용한 조치가 덮는 범위

- Peripheral의 검사 위치는 `lll_peripheral.c`의 `LL_ASSERT_OVERHEAD(overhead)`
  이다. Option을 끄면 이 macro는 아무 일도 하지 않고, 이벤트는
  `-ECANCELED`로 취소된다. `lll.c`는 option이 꺼져 있으면 이 값을 0으로
  바꾼다. **[확인]**
- `c6e5f15` 빌드의 Kconfig 출력에 `CONFIG_BT_CTLR_ADVANCED_FEATURES=y`가 있고
  `ASSERT_OVERHEAD_START`는 없다(출력은 꺼진 option을 싣지 않는다). Left와
  right 모두 같다. **[확인]**
- 끊긴 뒤 advertising을 다시 켜는 경로(`lll_adv.c`)도 같은 macro를 써서 함께
  덮인다. **[보고]**
- 같은 지연 경로에 남는 것은 timing 검사가 아니라 내부 장부 검사다(clock
  참조 수, done-event pool, prepare pipeline 가득 참, preempt ticker). **[보고]**

## 4. 남은 원인 후보

| 순위 | 후보 | 가능성 | 근거 |
| --- | --- | --- | --- |
| 1 | Tx ack FIFO index 경쟁 조건 (`ull.c`의 `ll_rx_get`과 ISR의 `ll_rx_put`) | 가능 | Upstream 수정 zephyrproject-rtos/zephyr#92779가 이 fork에 없다 **[확인]**. #93260도 없다 **[보고]**. 두 half가 공통으로 실행하는 코드이고 드문 경쟁이라 며칠에 한 번꼴과 맞는다 **[추정]** |
| 2 | Thread stack overflow | 가능 | Stack 보호가 전부 꺼져 있다: `HW_STACK_PROTECTION`, `MPU_STACK_GUARD`, `STACK_SENTINEL` 모두 Kconfig 출력에 없다 **[확인]**. 넘치면 옆 RAM을 조용히 망가뜨리고 나중에 엉뚱한 곳에서 오류가 난다 **[추정]** |
| 3 | Host의 HCI command timeout 검사 (`hci_core.c`) | 가능 | `CONFIG_BT_ASSERT=y` **[확인]**. 끊긴 뒤 advertising을 다시 켤 때 controller가 10초 안에 응답하지 않으면 k_oops다. 원인은 결국 controller 쪽이다 **[보고]** |
| 4 | Flash 쓰기와 radio timing 충돌 | 가능, 지금은 완화 | `SOC_FLASH_NRF_RADIO_SYNC_TICKER=y`이고 partial erase는 꺼져 있다 **[확인]**. Erase 한 번이 약 90 ms 동안 radio를 막는다. Upstream #92873도 빠져 있다. 조치 전에는 §3의 검사로 이어졌고, 지금은 이벤트 누락이나 끊김으로 끝날 것으로 본다 **[보고]** |
| 5 | Radio interrupt 지연 검사 (`lll_conn.c`의 `LL_ASSERT(!radio_is_address())`) | 낮음 | Interrupt를 150 µs 넘게 막는 코드를 ZMK와 PMW3610 driver에서 찾지 못했다 **[보고]** |
| 6 | 배터리 전압 저하 | 낮음 | 배터리 상태에서 reset만으로 살아난 것과 맞지 않는다 **[추정]** |
| 7 | 연결 parameter 절차의 RX node 누수 | 낮음 | Upstream #115384가 빠져 있지만, 동글이 잘못된 control packet을 보내야 한다 **[보고]** |

Stack 크기(byte) **[보고, 일부 확인]**: ISR 2048, main 1024, idle 320, system
work queue 2048(확인), BT RX work queue 2200(확인), BT long work queue 1400,
controller RX 896 / RX prio 448(확인), split peripheral notify queue 756, ZMK
low-priority queue 768, input thread 1024, USB work queue 1024.

## 5. 배제한 것

- **열흘에 맞춰 넘치는 counter**: 찾지 못했다. RTC는 512초, 연결 event
  counter는 약 491초마다 돌고, kernel 시간과 timeout은 64-bit다. 두 half가
  하루 차이로 멈춘 것은 시한 버그보다 드문 무작위 사건으로 본다. **[보고]**
- **교착 상태**: USB 인식은 별도 work queue(priority -1)와 POWER/CLOCK
  interrupt만 있으면 된다. System work queue가 죽거나 mutex에서 교착돼도 USB는
  잡힌다. 멈춘 half가 USB에 잡히지 않았으므로 배제한다. 남는 것은 halt,
  높은 priority의 cooperative thread가 도는 경우, interrupt 폭주뿐이다.
  **[보고]**
- **설정 저장소와 heap**: half는 주기적으로 flash에 쓰지 않는다(CCC는 쓸
  때만, ext-power는 toggle할 때만, CPI는 저장하지 않는다). ZMK는 heap을 쓰지
  않는다. **[보고]**
- **트랙볼 driver와 CPI module**: left에는 없는 코드라 두 half의 멈춤을
  설명하지 못한다. Left와 right의 Kconfig 차이는 SPI와 PMW3610뿐이다. Halt로
  이어질 버그도 찾지 못했다. **[보고]**
- **`9ebbeff` → `4dd95d7` 변경, 동글 쪽 원인, deep sleep**: `docs/dongle.md`
  §4.5 참조.

## 6. 재발하면

재발은 §3의 조치로 덮이지 않는 원인이라는 뜻이다. 순서대로 한다.

### 6.1 먼저 기록할 것

- 날짜와 시각, 어느 half인지.
- Reset 전에 USB에 꽂았을 때 잡히는지. 잡히지 않으면 halt가 맞다.
- 멈추기 직전에 동글이나 PC 쪽 연결이 끊겼는지. 끊겼다면 재연결 경로(후보
  3, 4), 아니면 평상시 경로(후보 1)다.
- CPI 변경이나 ext-power toggle 직후였는지(flash 쓰기, 후보 4).

### 6.2 원인을 기록하고 스스로 재부팅하게 한다

작은 module을 만든다. Config 저장소에 `zephyr/module.yml`을 두면 ZMK의 build
workflow가 `ZMK_EXTRA_MODULES`로 넣는다. **[보고]**

1. `k_sys_fatal_error_handler(reason, esf)`를 재정의한다. Weak symbol이라
   그대로 덮인다.
2. `reason`, `esf->basic.pc`, `esf->basic.lr`, 현재 thread 이름
   (`CONFIG_THREAD_NAME` 필요)을 reset 뒤에도 남는 RAM 영역에 적는다.
3. `CONFIG_BT_CTLR_ASSERT_HANDLER=y`로 `bt_ctlr_assert_handle(char *file,
   uint32_t line)`도 정의해 controller assert의 파일과 줄 번호를 적는다. 이
   함수는 return하면 안 된다.
4. `sys_reboot(SYS_REBOOT_COLD)`로 재부팅한다. `CONFIG_REBOOT`는 이미 켜져
   있다.
5. 부팅할 때 기록이 있으면 settings에 옮겨 적고, USB logging build에서
   출력한다. `hwinfo_get_reset_cause`도 함께 본다.

주의할 점 **[보고]**:

- 기록 영역은 Adafruit bootloader가 쓰는 RAM을 피해야 한다. Bootloader는
  `0x20007F7C`부터 위쪽과 RAM 맨 위의 stack을 쓴다. `sram0`의 시작을 256
  byte 올리고 그 자리를 `zephyr,memory-region`으로 잡는다. 평범한 `__noinit`
  변수는 덮일 수 있다.
- GPREGRET은 ZMK가 boot mode에 쓰므로 쓰지 않는다. GPREGRET2는 bootloader가
  건드리지 않는다.
- 이 board의 bootloader version은 확인하지 않았다. 일부러 `k_oops`를 내서
  기록이 살아남는지 한 번 시험한다.
- Build는 `.uf2`만 올린다. PC 값을 해석하려면 같은 commit의 `zmk.elf`가
  필요하다.

### 6.3 Kconfig만으로 되는 것

- `CONFIG_HW_STACK_PROTECTION=y`: stack overflow를 즉시 오류로 만든다(후보
  2). 6.2와 함께 넣어야 원인이 기록된다.
- `CONFIG_SOC_FLASH_NRF_PARTIAL_ERASE=y`: flash erase를 3 ms 단위로 쪼갠다
  (후보 4).
- Stack 여유를 재려면 debug build에 `CONFIG_THREAD_ANALYZER`,
  `CONFIG_THREAD_ANALYZER_AUTO`, `CONFIG_ZMK_USB_LOGGING`을 넣는다.

### 6.4 기록으로 원인이 드러난 뒤

- 후보 1로 확인되면 Zephyr fork를 따로 고정한다: `10ba6d0`에 #92779,
  #93260, #92873, #115384를 얹고 `config/west.yml`에 `zephyr` project를 직접
  적는다. Kconfig로는 고칠 수 없다. 유지 부담이 있어 확인 전에는 하지 않는다.
- Halt가 아닌 멈춤(thread가 도는 경우, interrupt 폭주)까지 덮으려면 hardware
  watchdog을 쓴다: `CONFIG_WATCHDOG=y`(`wdt0`는 이미 켜져 있다)와
  `CONFIG_TASK_WDT`. 한번 켜면 멈출 수 없고 soft reset 뒤에도 돌기 때문에,
  bootloader의 update mode에서 문제가 없는지 먼저 확인한다.

위 6.2~6.4는 어느 것도 build하거나 board에서 시험하지 않았다.

## 7. 참고 자료

Upstream 이슈와 PR:

- zmkfirmware/zmk#3331: 같은 board에서 overhead assert로 멈추고 hardware
  reset만 통한다는 보고. §3 조치의 근거.
- zmkfirmware/zmk#3480: central의 prepare pipeline 문제. 수정 `10ba6d0`이
  이미 build에 들어 있다.
- zmkfirmware/zmk#3370: core dump 실험(draft).
- zephyrproject-rtos/zephyr#92779, #93260: Tx ack FIFO 경쟁 조건 수정.
- zephyrproject-rtos/zephyr#92873: flash와 ticker 간격 수정.
- zephyrproject-rtos/zephyr#92186: 연결 갱신과 flash 쓰기가 겹칠 때의
  overhead assert.
- zephyrproject-rtos/zephyr#115384: 연결 parameter 절차의 RX node 누수 수정.

이 PC에 받아 둔 소스(저장소 밖, `charybdis-dongle/src-ref/`):

- `zmk`: `4dd95d7`
- `zephyr`: zmkfirmware/zephyr `v4.1.0+zmk-fixes`, `10ba6d0c`
- `zmk-pmw3610-driver`, `Adafruit_nRF52_Bootloader`
- `run_44991367133.log`, `kconfig_left.txt`, `kconfig_right.txt`: `c6e5f15`
  build의 log와 Kconfig 출력
- `upstream_prs/`: 위 Zephyr PR들의 설명과 diff
