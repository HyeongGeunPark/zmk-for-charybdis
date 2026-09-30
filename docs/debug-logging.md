# 트랙볼 멈춤 진단: USB 로그 빌드 (`debug-logging` 브랜치)

> 진단 전용 브랜치다. `my-keymap`에 병합하지 않는다. `build.yaml`, `tools/`, `docs/`, `.gitignore`만 다르고
> `config/`는 `my-keymap`과 같다(`git diff my-keymap -- config`가 비어 있어야 한다).
> 이 브랜치의 `build.yaml`에는 프로덕션 항목이 없으므로 병합하면 프로덕션 빌드가 사라진다.

## 1. 무엇을 알아내려는가

경로: `PMW3610 센서 -> 오른쪽 반(입력 스레드, BLE 송신) -> 무선 -> 동글(수신, 입력 처리) -> USB HID -> PC`

| 후보 | 내용 | 이 빌드에서 보이는 것 |
|---|---|---|
| H1 센서 rest 지연 | 센서가 저전력(REST) 단계에서 첫 움직임을 늦게 알아챔 | 오른쪽 `x/y:` 줄의 간격 |
| H2 오른쪽 송신 정체 | BLE 송신 버퍼(3개)가 차서 입력 스레드가 막힘 | `x/y:`와 `input event:` 줄의 시간차, `Event dropped` |
| H3 링크 끊김 | 오른쪽 반과 동글의 연결이 끊겼다 재연결 | 오른쪽 `Disconnected from`, `Security changed`, 동글 상세 로그 |
| H4 무선 구간 지연 | 재전송/간섭/연결 파라미터로 이벤트가 늦게, 몰려서 도착 | 동글 `input event:`가 공백 뒤 한꺼번에 도착 |
| H5 동글 내부/USB | 입력 큐 넘침, USB 전송 실패, USB 일시정지/재열거 | 동글 `FAILED TO SEND OVER USB`, `Device ...` |
| H6 로그의 왜곡 | 로그 유실, 로그가 동작을 바꿈 | `messages dropped`, 5절의 추가 점검 |

CI `.config`(2026-09-30, `my-keymap` 빌드)로 확인한 사실:

- `CONFIG_ZMK_SLEEP`은 세 보드 모두 꺼져 있고, ZMK의 IDLE(30초)은 BLE나 센서를 재우지 않는다. 그래서
  "키보드 sleep-wake 지연"은 이 펌웨어에서는 후보가 아니다.
- 남는 "재우기"는 센서 자체의 단계 전환이다(드라이버 기본값): RUN 128 ms, REST1 5000 ms, REST2 17000 ms,
  REST 샘플 주기 40/100/500 ms. 드라이버의 정수 나눗셈으로 실제 등록 값은 128/4480/12800 ms이고 REST3에는
  마지막 움직임 후 약 17초 뒤 도달한다(순차 전환 가정). "REST 중에는 샘플 주기마다 움직임을 확인한다"는
  부분은 데이터시트로 확인하지 못한 추정이다.
- 분할 BLE는 간격 7.5 ms, latency 30이고 오른쪽 반의 송신 버퍼(`BT_BUF_ACL_TX_COUNT`, `BT_ATT_TX_COUNT`)는 3개다.
  X, Y 이벤트는 각각 BLE 알림 하나이고, 오른쪽 반은 입력 스레드에서 `bt_gatt_notify()`를 직접 부르며 버퍼가 없으면
  그 스레드는 무기한 기다린다(`input_split.c`, `service.c`, Zephyr `att.c` 소스 읽기). H2의 근거다.

## 2. 산출물과 로그 설정

`debug-logging`에 push하면 `firmware` 아티팩트에 다음이 들어 있다. 끝의 `_dbg`가 진단용 표시다.

| 파일 | 굽는 보드 | 설정 |
|---|---|---|
| `charybdis_dongle_dbg.uf2` | 동글 | **Studio 끔**, 로그용 USB 시리얼 하나. ZMK 로그는 경고 이상만, `INPUT_EVENT_DUMP`. 멈춤 간격 분석용 |
| `charybdis_dongle_dbg_zmkdbg.uf2` | 동글 | 위와 같고 ZMK 로그 전체(연결/끊김, 연결 파라미터, 스캔). 너무 많아 60초 이하 짧은 캡처용 |
| `charybdis_right_dbg.uf2` | 오른쪽 반 | `PMW3610_ALT_LOG_LEVEL_DBG`(읽기마다 `x/y`), `INPUT_EVENT_DUMP` |
| `charybdis_right_dbg_fastrest.uf2` | 오른쪽 반 | 위와 같고 REST 샘플 주기 10 ms (H1 A/B, 6절) |
| `settings_reset.uf2` | 굽지 않는다 | 페어링이 지워진다. 원래 항목을 그대로 둔 것 |

Studio를 끈 이유: 동글의 USB 시리얼이 로그 하나뿐이 되어 어느 COM 포트를 열지 헷갈리지 않고, 두 CDC 포트가 USB
전송 슬롯을 나눠 쓰는 위험도 없다. Studio는 프로덕션 펌웨어로 돌아오면 그대로 쓸 수 있다.

왼쪽 반은 굽지 않는다. 센서가 없어 트랙볼 경로에 없고, 로그를 보려면 USB 케이블이 하나 더 필요하다.
공통: 로그 버퍼 16384(기본 8192), 로그 시작 지연 5000 ms(부팅 로그를 PC가 포트를 연 뒤에 내보냄), 입력 스레드 스택
2048(기본 1024). CDC 링(기본 1024, 가득 차면 글자가 조용히 버려짐)은 오른쪽 16384, 동글 8192다. 오른쪽 반은
최대 속도로 굴릴 때 초당 약 32 KB를 쓰므로 16384는 약 0.5초 분량이다(줄 수와 크기로 계산한 추정, 실측 아님).

동글의 ZMK 로그를 경고 이상으로 줄인 이유: ZMK는 로그 모듈이 하나라 켜기만 해도 트랙볼 이벤트마다 여러 줄이
나오고, 동글의 로그는 HID와 같은 USB 컨트롤러로 나간다. 그래서 `charybdis_dongle_dbg`는 `Connected`/
`Disconnected`/`New connection params`가 빠진다. 그 정보가 필요하면(H3, H4) `charybdis_dongle_dbg_zmkdbg`로
짧게 재현한다. 두 빌드는 같은 동글에 번갈아 굽는다.

## 3. 준비, 빌드 받기, 굽기

1. 한 번만: `py -m pip install pyserial` (지금 PC에는 없다). 데이터 케이블 두 개(동글은 이미 연결, 오른쪽 반용).
   PuTTY, 시리얼 모니터는 닫는다(Windows는 COM 포트를 한 프로그램만 연다). PowerShell 또는 Windows Terminal에서
   실행한다.
2. **동글을 굽는 동안 이 PC의 입력 장치는 Charybdis뿐이다. 예비 키보드와 마우스를 준비한다.** 캡처 중 마크(Enter)도
   키보드가 필요하다.
3. 도구 자체 검사(하드웨어 불필요): `py tools\test_capture_log.py`
4. 빌드 받기:
   ```powershell
   gh run list --branch debug-logging --limit 3
   gh run watch <run-id>
   gh run download <run-id> --name firmware --dir firmware-dbg
   ```
   항목 하나라도 실패하면 병합 작업이 건너뛰어져 `firmware` 아티팩트가 없다. 그때는 끝난 항목을 개별로 받는다:
   ```powershell
   gh run download <run-id> --pattern "artifact-*" --dir firmware-dbg
   ```
   실패 원인은 Actions에서 `... Kconfig file`, `... Devicetree file` 단계를 본다. 동글 Devicetree에
   `zephyr,cdc-acm-uart` 노드가 하나이고 `zephyr,console`이 그 노드를 가리키는지, 링크 단계 `RAM:`이 256 KB 안인지
   (현재 프로덕션은 동글 75,876 B, 오른쪽 38,320 B) 확인한다. 받은 UF2 폴더는 `.gitignore`에 들어 있다.
5. 굽기: 보드의 리셋을 빠르게 두 번 눌러 `NICENANO` 드라이브를 열고 UF2를 복사한다. 동글에
   `charybdis_dongle_dbg.uf2`, 오른쪽 반에 `charybdis_right_dbg.uf2`. `settings_reset`은 굽지 않는다. 일반 UF2
   업데이트는 페어링을 지우지 않는 것이 정상이다(ZMK 문서 기준, 이 하드웨어에서는 미확인).

## 4. 캡처

1. 케이블을 하나씩 꽂으며 `py tools\capture_log.py --list`로 새로 생긴 COM 번호를 적는다. 동글과 오른쪽 반은 각각
   포트 하나로 예상한다(미확인). 보드는 **SERIAL 열**로 구분한다(동글과 오른쪽 반은 일련번호가 다르다). 셋 다 VID:PID는
   `1D50:615E`이고, LOCATION은 Windows에서 비어 있을 수 있다. 문서와 도구 설명의 `COM5`, `COM6` 같은 숫자는 예시일
   뿐이다(이 PC에서 COM5/COM6은 com0com 가상 포트다).
2. 본 캡처(저장소 루트에서, `COM<...>`를 실제 번호로):
   ```powershell
   py tools\capture_log.py --port COM<동글> --name dongle --port COM<오른쪽> --name right --mark --quiet --outdir logs
   ```
   각 줄은 `PC시각 [보드 부팅 후 시각] <수준> 모듈: 내용`이다. PC 시각은 파일끼리 대략 맞추는 데(오차 약 100 ms),
   보드 시각은 같은 보드 안의 정확한 간격에 쓴다. 두 보드의 시각은 서로 무관하다. `###` 줄은 도구가 쓴 것이다.
   `--quiet`는 장치 줄을 콘솔에 되풀이하지 않는다(초당 수백 줄이 PC에 부하를 주고 마크 확인이 묻힌다). `MARK n
   inserted`와 15초 무입력 안내는 그대로 나온다.
3. 부팅 로그(센서 초기화 값)까지 보려면: 도구를 먼저 켜고 오른쪽 반의 USB를 꽂은 다음, 오른쪽 반의 **리셋 버튼을 한 번**
   누른다(두 번 빠르게 누르면 부트로더로 들어간다). 배터리가 있는 반은 USB를 뽑았다 꽂는다고 재시작하지 않는다.
   부팅 후 약 5초 뒤에 로그가 나오기 시작하는 것은 정상이다. 호스트 없이 오래 켜져 있던 반에 처음 연결하면 처음 약
   4 KB는 오래된 로그가 묶여 나오므로 무시한다.
4. 멈춤 표시(분석 품질을 정한다):
   - 멈춘 것 같으면 볼을 멈추지 말고 계속 굴리면서 Enter. 굴리는 동안 센서가 무엇을 보고했는지가 핵심이다.
   - 메모를 먼저 쓰고 Enter를 치면 마크에 붙는다(`idle20 froze` + Enter는 `### MARK 3 idle20 froze`).
   - 마크는 Enter를 친 시각이라 반응 시간만큼 늦다. 마크 1~3초 전을 본다(5절의 스크립트). 멈춤이 없었으면 누르지 않는다.
   - 시나리오(각 5분 이상): 평소처럼 사용, 그리고 볼을 놓고 2/10/30/60초 기다렸다 굴리기(대기 시간을 메모).
5. Ctrl+C로 끝내면 파일별 요약이 나온다: `lines nonlog partial drop_markers dropped_messages`. 값이 0이 아니면 그 구간의
   결론은 보류한다. 0이어도 유실이 없다는 증거는 아니다(5절의 추가 점검을 한다).
6. `logs\` 전체, 어느 빌드를 어느 보드에 구웠는지, 시나리오와 시간, 마크마다 느낀 것을 알려 준다.

## 5. 로그 읽는 법

| 출처 | 줄 | 의미 |
|---|---|---|
| 오른쪽 | `<dbg> pmw3610: ... x/y: 3/-1` | 센서를 한 번 읽음(시스템 작업 큐, SPI 읽기 직후) |
| 둘 다 | `<inf> input: input event: dev=... type= 2 code=  0 value=3` | 입력 이벤트. `code=0` X, `code=1` Y |
| 둘 다 | `<inf> input: input event: dev=... SYN type= 2 code=  1 value=-1` | 묶음의 마지막 이벤트에 `SYN`이 붙는다. 두 축이 다 움직이면 Y 줄, X만이면 X 줄 |
| 오른쪽 | `Disconnected from <주소> (reason 0x08)`, `Security changed` | 연결 끊김(0x08은 시간 초과) |
| 오른쪽 | `interval N latency N timeout N` | 연결 파라미터가 바뀔 때만 나온다(연결 직후에는 안 나옴) |
| 동글 | `<err> zmk: FAILED TO SEND OVER USB`, `<inf> usb_hid: Device suspended` | HID 전송 실패, USB 일시정지 |
| 둘 다 | `<wrn> input: Event dropped, queue full ...` | 입력 큐(16개)가 차서 버려짐 |
| 둘 다 | `--- N messages dropped ---` | 보드의 로그 버퍼 넘침 |
| 동글(상세 빌드만) | `New connection params`, `Connected:`, `Disconnected:`, `scanning` | 동글이 본 BLE 연결 상태 |

`input event:`의 장치 이름은 오른쪽 `trackball@0`, 동글 `trackball_split@0`으로 예상하지만 확인하지 않았다.
정상 간격(RUN 모드 약 8 ms, 드라이버 주석 값, 실측 아님)을 먼저 확인하고 기준으로 삼는다.

| 후보 | 지지하는 패턴 | 배제하는 패턴 |
|---|---|---|
| H1 | 128 ms 이상 멈췄다 굴리기 시작한 직후 오른쪽 `x/y:`가 100 ms 이상 비었다 나오고 그 뒤 간격은 정상, 동글도 같은 시각에 받음. 정지가 길수록(17초 이상) 공백이 김. 공백 뒤 첫 `x/y:`의 값이 평소보다 크면(센서가 그동안 움직임을 쌓아 둠) 힌트이지 증거는 아니다. `x/y:` 공백만으로는 센서 깨어남과 시스템 작업 큐 지연을 구분할 수 없으므로 A/B(6절)로 판정 | 멈춘 느낌 내내 `x/y:`가 8 ms 안팎으로 끊김 없이 찍힘 |
| H2 | `x/y:`는 정상인데 대응하는 `input event:`가 점점 늦어짐(수십 ms 이상 누적), 이어서 `Event dropped`, 동글 쪽 누락 | 두 줄의 시간차가 항상 수 ms 이내, `Event dropped` 없음 |
| H3 | 마크 근처 오른쪽 `Disconnected from`/`Security changed`(끊긴 동안 움직이면 `No active transport ...` 경고 예상, 미확인), 그 동안 동글 `input event:` 정지. 동글 상세 빌드에서는 `Disconnected:`/`Connected:` | 캡처 전체에 `Disconnected` 없음 |
| H4 | 오른쪽 `input event:`는 정상인데 같은 이벤트(code/value 순서)가 동글에는 공백 뒤 같은 시각에 몰려 도착. 지연 = 동글 시각 - 오른쪽 시각 - 시계 차이. 공백 뒤 같은 (code,value) 순서가 동글에 다시 나타나야 한다. 나타나지 않으면 지연이 아니라 로그 유실이다 | 두 파일에서 같은 이벤트의 도착 간격이 거의 같음 |
| H5 | 동글 `input event:`는 정상인데 커서가 멈춤, 같은 시각 `FAILED TO SEND OVER USB`/`Device (suspended, resumed, reset detected, connected, configured, disconnected, error)`/`Event dropped` | 동글 도착이 정상이고 위 줄이 없음. 동글 이후(Windows, 앱, 가속 설정)를 의심 |
| H6 | `messages dropped`, 아래 추가 점검이 0이 아님, 로그를 켰을 때만 빈도가 달라짐 | `messages dropped` 없음 **그리고** 추가 점검 두 가지가 모두 0 |

읽는 순서: 오른쪽 `x/y:`(굴리는 동안 정상인가) -> 오른쪽 `input event:`(`x/y:`를 따라오는가) -> 동글 `input event:`(같은
속도로 오는가) -> 동글의 USB 이상 줄. 처음 어긋나는 단계가 원인 구간이다. 동글 쪽 BLE 상태는 상세 빌드로 본다.

**마크 전후 구간 뽑기**(호스트 시각 기준 3초 전 ~ 1초 후, 파일이 커지므로 파일로 저장):

```powershell
powershell -File tools\mark_window.ps1 -Mark 1 > mark1.txt
powershell -File tools\mark_window.ps1 -Mark 1 -Before 5 -After 2 > mark1.txt   # 구간 조정
```

**일정 시간 이상 벌어진 줄 간격 찾기**(보드 시각 기준, 동글 파일이면 `$pat = 'input event:'`). 사용자가 볼을
놓은 구간도 함께 나오므로 마크와 대조한다:

```powershell
$file = (Get-ChildItem logs\right_*.log | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
$pat = 'x/y:'; $gap = 100; $prev = $null
Get-Content $file -Encoding utf8 | ForEach-Object {
  if ($_ -match '^\S+ \[(\d\d):(\d\d):(\d\d)\.(\d{3}),\d{3}\] <\w+> .*?' + [regex]::Escape($pat)) {
    $t = (([int]$Matches[1] * 60 + [int]$Matches[2]) * 60 + [int]$Matches[3]) * 1000 + [int]$Matches[4]
    if ($null -ne $prev -and ($t - $prev) -ge $gap) { '{0,7} ms gap  {1}' -f ($t - $prev), $_ }
    $prev = $t
  }
}
```

**이상 줄 모아 보기**:

```powershell
Select-String -Path logs\*.log -Pattern '### (dis|re)?connected|### stats|Disconnected|Connected: |Security changed|No active transport|Event dropped|messages dropped|FAILED TO SEND|Device (suspended|resumed|reset detected|connected|configured|disconnected|error)|New connection params|interval [0-9]+ latency [0-9]+ timeout|scanning|<err>|<wrn>'
```

**로그 유실 점검**(CDC 링이 넘치면 글자가 조용히 사라지고, 줄 머리와 꼬리가 붙은 줄은 정상 줄로 보인다):

```powershell
# 1) 한 줄에 로그 머리가 둘 이상 (줄이 붙음)
Select-String -Path logs\*.log -Pattern '.+\[\d\d:\d\d:\d\d\.\d{3},\d{3}\] <[a-z]{3}> '
# 2) 값이 잘린 이벤트/센서 줄 (둘 다 결과가 0줄이어야 한다)
Select-String -Path logs\*.log -Pattern 'input event:' | Where-Object { $_.Line -notmatch 'value=-?\d+$' }
Select-String -Path logs\*.log -Pattern 'x/y:' | Where-Object { $_.Line -notmatch 'x/y: -?\d+/-?\d+$' }
```

센서 한 번 읽기(`x/y:` 한 줄)에는 `input event:` 두 줄(X, Y)이 대응한다. 멈춤은 둘을 함께 없애지만, 짝이 깨져 있으면
로그 유실이다. 위 점검이 모두 0이고 `messages dropped`가 없어야 H6을 배제한다.

## 6. 후속 실험, 복귀, 문제 해결

- **H1 A/B**: 오른쪽 반에 `charybdis_right_dbg_fastrest.uf2`를 굽고 4절 시나리오를 반복한다. REST 샘플 주기를 10 ms로
  줄인 빌드다(드라이버 허용 범위 안: 샘플 10~2550 ms, REST1 하향 >= 16 x 샘플, REST2 >= 128 x 샘플). 샘플 주기에서
  파생되는 REST1/REST2 유지 시간도 조금 달라진다. 멈춤이 사라지면 H1을 강하게 지지하고, 그대로면 H1(샘플
  주기)은 사실상 원인에서 빠진다. 배터리를 더 쓴다.
- **동글 상세 로그(H3/H4)**: 동글에 `charybdis_dongle_dbg_zmkdbg.uf2`를 굽고 부팅과 재연결을 60초 이하로 캡처한다.
  `[INPUT EVENT]`와 `New connection params`, `Disconnected: ... (reason)`가 나오지만 줄 수가 많다.
- **왼쪽 반 로그**: `build.yaml`의 주석 처리된 `charybdis_left_dbg`를 되살린다(왼쪽 반도 USB로 연결).
- **배터리 상태**: 오른쪽 반의 USB를 뽑고 동글 로그만 캡처해 동글 `input event:` 간격으로 판단한다. 디버그 펌웨어는
  USB를 뽑아도 소비 전력이 늘어난다(ZMK 문서의 Battery Life Impact). 테스트가 끝나면 바로 프로덕션 UF2로 되돌린다.
- **프로덕션 복귀**(빌드 `my-keymap@6ec0943`, 실행 36686662479):
  ```powershell
  gh run download 36686662479 --name firmware --dir firmware-prod
  ```
  `charybdis_dongle.uf2`를 동글에, `charybdis_right.uf2`를 오른쪽 반에 굽는다. 왼쪽 반과 `settings_reset`은
  건드리지 않는다. 지금 구워져 있는 펌웨어가 다른 실행에서 왔다면 그 실행 번호로 받는다. 아티팩트가 만료됐으면
  `gh workflow run build.yml --ref my-keymap`. 끝나면 `git push origin --delete debug-logging`.

| 증상 | 확인 |
|---|---|
| COM 포트가 안 생김 | 데이터 케이블인지, `_dbg` UF2를 구웠는지 |
| `Access is denied` | 다른 프로그램이 포트를 잡음. 닫으면 도구가 다시 연다 |
| 15초 뒤 "nothing was received" | 로그가 안 나오는 빌드이거나 다른 보드의 포트. `--list`의 SERIAL로 다시 확인 |
| COM 번호가 바뀜 | LOCATION을 알 수 있을 때만 따라간다. Windows에서는 대개 따라가지 않으니 도구를 다시 실행 |
| `messages dropped`가 계속 나옴 | 오른쪽의 `INPUT_EVENT_DUMP` 또는 `PMW3610_ALT_LOG_LEVEL_DBG`를 빼고 다시 빌드 |
| 동글 인식 불가 | `build.yaml`의 동글 `-DCONFIG_ZMK_STUDIO=n`을 확인. 그래도 안 되면 프로덕션 복귀 후 보고 |
| RAM 초과 | `USB_CDC_ACM_RINGBUF_SIZE`와 `LOG_BUFFER_SIZE`를 줄인다(예: 2048/8192) |
| `assigned but not honored` | 그 심볼을 `cmake-args`에서 뺀다 |

## 7. 검증 상태

확인함: `snippet: zmk-usb-logging` 한 개와 `-DCONFIG_ZMK_STUDIO=n` 조합의 일관성(정적 분석), 모든 `-DCONFIG_*` 심볼의
정의와 프롬프트(고정된 소스), `ZMK_LOGGING_MINIMAL` + `ZMK_LOG_LEVEL_WRN`이 ZMK 로그 수준을 2로 만듦(Kconfig 축소
복제본을 kconfiglib로), 도구의 가짜 pyserial 테스트 14개와 pyserial 3.5 + com0com 실측 일부.

확인하지 못함: 실제 빌드 통과와 동글 열거(첫 CI와 실기기에서), 센서 REST의 실제 감지 주기(데이터시트), 로그 처리량과
유실, 관찰자 효과(로그를 켜면 멈춤 빈도가 달라지는지는 프로덕션과 비교해야 함), 이 하드웨어에서의 UF2 업데이트가
페어링을 유지하는지. Zephyr는 ZMK가 브랜치 이름(`v4.1.0+zmk-fixes`)으로만 고정하므로(마지막 CI는 `10ba6d0c`)
캡처를 비교할 때 CI 로그의 `HEAD is now at` 줄로 같은 Zephyr인지 본다.
