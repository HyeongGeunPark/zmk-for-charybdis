# 트랙볼 멈춤 진단: 상시 기록 시스템 계획 (dbgrec)

> 작성일: 2026-10-15<br>
> 상태: 계획이다(v3.1). 이번에 승인을 구하는 범위는 1단계(1a, 1b)다. 2단계부터는 1b 보고서가 가리키는 쪽만, 단계마다 다시 승인을 받은 뒤 진행한다.<br>
> 상세 명세(영문): `docs/dbgrec/spec.md` (v3.1). 바이트 배치, 소스 file:line 근거, 사실 번호(F-nn), 가정 번호(A-nn)가 모두 그 문서에 있다.<br>
> 이전 디버그 빌드: `debug-logging` @`0cfce87`, `docs/debug-logging.md`<br>
> 2026-11-09 변경: 이 문서와 dbgrec 작업은 `debug/dbgrec` 브랜치에만 둔다. 아래에서 `my-keymap` 한 브랜치에 둔다고 적은 부분(1.2절, 11.1절 등)은 이 결정으로 대체된다. 또 `my-keymap`의 ZMK 핀이 9ebbeff에서 4dd95d7로 올라가, 4단계 후보 `_fix3110`(ZMK 5b51501)이 프로덕션에 이미 들어갔다. 이후 단계를 진행할 때 기준 SHA를 다시 맞춘다.

이 문서는 다음을 정리한다.

- 무엇을 왜 만드는지
- 사용자가 무엇을 하는지
- 무엇이 확인되었고 무엇이 아직인지

`[추정]`이 붙은 수치는 나중에 CI나 실기기에서 잰 값으로 바꾼다.

## 1. 요약

### 1.1 이전 빌드의 문제

이전 디버그 빌드는 짧은 실험실 캡처용이었다.

- 로그를 남기려면 오른쪽 반을 USB 케이블로 PC에 묶어야 했다.
- 멈춤을 표시하려면 캡처 도구의 콘솔 창에서 Enter를 쳐야 했다.
- 디버그 동글에서는 ZMK Studio가 꺼졌다.
- 텍스트 로그가 오른쪽 반 기준 초당 약 35 KB였다. CDC 링이 넘치면 아무 표시 없이 버려졌다.
- 도구에 pyserial이 필요했는데 이 PC에는 설치된 적이 없다.

결국 이 빌드는 한 번도 쓰이지 않았다.

### 1.2 새 방식

새 방식에는 텍스트 로그가 없다. 동작은 다음과 같다.

- 동글이 트랙볼 입력이 지나가는 지점마다 이벤트 수, 이동량 합, 처리 지연을 100 ms 단위로 모아 RAM 링 버퍼에 남긴다.
- PC 에이전트가 1초마다 그 기록을 가져온다. 통로는 동글의 두 번째 USB HID 인터페이스(vendor collection, MI_03)다.
- 두 반은 무선·배터리 그대로 쓴다. Studio 포트(MI_00/COM33)도 그대로다.
- 멈춤은 키보드 조합으로 동글 타임라인에 직접 표시한다. 에이전트가 토스트로 확인을 띄우고, 60초 뒤 판정이 담긴 보고서를 자동으로 쓴다.
- 오른쪽 반 내부는 2단계에서 본다. 연결마다 handshake를 거친 뒤, 활동한 초마다 20 B 요약 하나와 이상 구간 레코드를 동글에 보낸다(쉴 때는 1분에 1개). 통로는 암호화된 연결에서만 열리는 자체 GATT 서비스다.
- 1~2단계 기록기는 로그 문자열, UART/CDC 출력, 실행 중 flash 쓰기를 쓰지 않는다. Studio의 CDC 포트는 프로덕션과 같다.
- 디버그 코드는 별도 브랜치가 아니라 `my-keymap`의 `dbgrec/`, `host/`, `.github/workflows/dbgrec.yml`에 둔다. 프로덕션 빌드에는 들어가지 않는다(11.1절).

### 1.3 사용자가 하는 일

| 언제 | 사용자가 하는 일 | 시스템이 하는 일 |
|---|---|---|
| 처음 한 번 | 동글을 꽂은 채 `py -3.14 host\install_dbgrec.py` | 로그온 자동 시작을 등록하고, 동글의 USB serial을 기록하고, supervisor와 에이전트를 띄운 뒤 `doctor` 결과를 보여 준다 |
| 1a를 시작할 때 | CI bundle zip을 받아 `py -m dbgrec rescue import <zip>`을 실행하고, 이어서 복구 훈련을 한다(5.1절) | 복구 이미지, ELF, 심볼을 보관한다. 아무것도 stage하지 않는다 |
| 단계를 시작할 때 | `py -m dbgrec flash <zip> dongle`(2단계는 `--target dongle_dbg2`, 그리고 케이블을 꽂고 `right`) 뒤 그 보드의 리셋을 두 번 누른다 | 감시기가 stage된 이미지를 굽고 ELF와 심볼을 보관한다. settings_reset을 하지 않으므로 페어링과 Studio 편집은 그대로다 |
| 평소 | 없다 | 에이전트가 1초마다 동글 기록을 가져오고 Raw Input을 센다 |
| 포인터가 멈췄을 때(1b부터) | POINTER(왼손 엄지)를 누른 채 R+T(왼손 검지)를 친다. R과 T를 모두 누를 때까지 POINTER를 누르고 있는다. SYMBOLS가 고착된 듯하면 오른손 새끼로 `[`+`'`를 친다(8.1절) | 약 1초 안에 토스트, 약 60초 뒤 보고서 |
| 포인터가 멈췄을 때(1a, 또는 조합을 쓸 수 없을 때) | Ctrl+Alt+Shift+M | 같은 토스트와 보고서. 시계 맞춤으로 동글 타임라인에 놓이므로 키보드 마크보다 덜 정확하다 |
| 원할 때 | 트레이 → "마지막 마크 메모 ▸"를 한 번 클릭한다 | 메모가 판정 규칙(C4, C5, C6)에 들어간다 |
| 관찰자 효과를 비교할 날 | `py -m dbgrec ctl mode off`, 끝나면 `py -m dbgrec ctl mode normal` | 측정을 끈 날을 기준선과 비교한다(3.3절) |
| 디버그 펌웨어가 이상할 때 | 동글 리셋을 두 번 누르고 손을 뗀다 | 약 20초 안에 프로덕션 설정 동글 이미지를 굽는다. 이 이미지는 stage했던 디버그 이미지와 같은 CI 실행에서 같은 커밋, 같은 Zephyr, 같은 컨테이너로 빌드한 것이다 |

디버그 기간에 하지 않을 것:

- Studio에서 레이어 순서를 바꾸거나 레이어를 지우지 않는다. 레이어 2·4·5·6의 16/17과 레이어 1의 23/35 바인딩도 바꾸지 않는다. 다른 바인딩 편집은 괜찮다(8.3절).
- 디버그 동글 이미지를 stage해 구운 뒤(복구가 켜진 동안) 동글을 손으로 구울 때는 트레이 "복구 일시중지 10분"이나 `py -m dbgrec rescue pause`를 먼저 한다. 그러지 않으면 감시기가 5초 뒤 복구 이미지를 굽는다(9.4절).
- 키보드가 10분쯤 제대로 안 돼도 괜찮은 날에만 새 단계를 시작한다.

### 1.4 단계

| 단계 | 굽는 보드 | 내용 | 알 수 있는 것 |
|---|---|---|---|
| **1a** | 없음 | PC 에이전트, 복구 감시기, 디버그 CI | PC/OS 쪽인지 장치 쪽인지, 레이어로 빠진 경우(휠), 프로덕션 기준선 |
| **1b** | 동글 | 동글 기록기, HID_1, 마크 조합, 고장 기록 | 동글 내부 정체·유실, USB/호스트, 레이어 고착, 동글 리셋, 4초 이상 링크 끊김 |
| 2 | 오른쪽 반, 동글(`dongle_dbg2`) | 오른쪽 최소 기록기, 동글 diag client | B2 루프 대 무선 대 센서, 오른쪽 리셋 |
| 2b | 동글 | shadow 구독, RSSI, CPI 시점 | 동글 유실의 정확한 수, 레이어 고착의 원인 |
| 3, 4 | 항목별 | 정밀 계측, 수정 후보 A/B | 단일 사건의 결정적 증거, 효과 있는 수정 |

첫 산출물은 1단계(1a와 1b)다. 2단계부터는 1단계 결과가 가리키는 쪽만 진행한다. 어느 단계에서도 ZMK나 Zephyr를 fork하지 않는다. 프로덕션 펌웨어, `config/`, 프로덕션 workflow는 바뀌지 않는다(선택 사항인 `paths-ignore` 하나만 예외, 11.1절).

B2 루프(C1)는 오른손 타이핑으로 오른쪽 `position_state_msgq`가 차고, 오른쪽 sysworkq가 약 100 ms 단위로 막히며, 센서 읽기와 notify가 함께 멈추는 현상이다(10.4절).

### 1.5 평소에 달라지는 것

- 로그온 때 `기록 중 · 동글 abc1234` 토스트가 한 번 뜬다. 알림 영역에 트레이 아이콘(녹색·노랑·빨강)이 생긴다. 처음에는 overflow 영역에 숨어 있으므로 고정해 둔다.
- Ctrl+Alt+Shift+M은 마크 단축키로 쓰인다(1a부터). 다른 앱과 겹치면 `config.json`에서 바꾼다.
- 1b부터 장치 관리자에 vendor HID(MI_03)가 하나 더 보인다. Studio 포트(COM33)와 키보드·마우스 장치는 그대로다. Studio의 behavior 목록에 "DEBUG mark (do not bind)"가 보이지만 바인딩되지 않는다.
- 평소 타이핑은 달라지지 않는다. Base 레이어에는 마크 combo가 없다. SCROLL이나 SNIPE가 POINTER 없이 고착된 동안에만 R/T가 최대 80 ms 늦어진다(8.2절).
- 동글 LED로는 아무것도 알리지 않는다.
- 마크마다 약 60초 뒤, 그리고 30분마다 `%LOCALAPPDATA%\dbgrec\reports\`에 보고서가 생긴다.
- PC 부담은 에이전트 RAM 약 30 MB, CPU 0.5% 미만, 디스크 하루 약 2~4 MB(최대 8 MB)다. 지난 날 파일을 압축하는 정리 프로세스가 하루 한 번 30초 이내로 메모리를 약 100 MB 더 쓴다 [추정].
- 2단계부터 오른쪽 반 배터리가 조금 더 빨리 닳는다. 목표는 추가 소모 2% 이하다.

### 1.6 문제가 생기면

| 증상 | 할 일 |
|---|---|
| 굽고 나서 키보드가 안 되거나 재부팅이 반복된다 | 동글 리셋을 두 번 누르고 20초 기다린다. 그동안 노트북 키보드와 터치패드를 쓴다 |
| Studio가 연결되지 않는다 | 같은 방법으로 프로덕션으로 되돌린다 |
| 1a 기준선보다 멈춤이 잦아진 것 같다 | `py -m dbgrec ctl mode off`로 이틀 지낸다. 그래도 잦으면 되돌린다 |
| 트레이가 빨강이다(새 crash 등) | `py -m dbgrec bundle --since 1d`로 묶어 전달한다 |
| 트레이 노랑 "마크 콤보 설정 불일치" | Studio에서 바꾼 레이어 순서, 레이어 삭제, 마크 위치의 바인딩을 되돌린다 |
| 트레이 노랑 "기록 펌웨어 없음" | 프로덕션 펌웨어가 구워져 있다. 기록을 이어 가려면 `flash`로 다시 stage하고 리셋을 두 번 누른다 |
| 토스트가 뜨지 않는다 | 에이전트가 죽었다는 뜻은 아니다. `py -m dbgrec doctor`로 확인한다 |
| 오른쪽 반이 이상하다(2단계) | 트레이 "오른쪽 복구 이미지 준비"를 누르고, 케이블을 꽂고, 오른쪽 리셋을 두 번 누른다 |
| 에이전트가 없는 PC에서 동글을 되돌려야 한다 | 동글 리셋을 두 번 눌러 `NICENANO` 드라이브를 열고, bundle zip의 `rescue/dongle.uf2`를 직접 복사한다 |
| 디버그 작업을 끝낸다 | 동글(2단계면 오른쪽도)을 위 방법으로 되돌리고 `py -3.14 host\install_dbgrec.py --uninstall`을 실행한다. 데이터까지 지우려면 `--purge`를 더한다 |

### 1.7 단계별 부담

| 단계 | 사용자가 할 일 | 기간 | 구현 규모 [추정] |
|---|---|---|---|
| 1a | 설치 1회, bundle 가져오기, 5.1절 하드웨어 확인(복구 훈련, 보드 식별, 프로세스 강제 종료, 하룻밤 절전, 최대 절전 포함) | 기준선 3일 이상 | Python 약 1,000줄, 테스트 150줄, workflow 150줄 |
| 1b | 동글 굽기, 5.2절 하드웨어 확인 11항목(selftest 포함), 멈출 때 마크, `mode off` 날 2일 이상 | 판정된 마크 멈춤 3건 또는 2주 | C 약 900줄, 설정 120줄, Python 약 400줄 |
| 2 | 오른쪽 복구 훈련(케이블), 오른쪽과 동글 굽기, 5.3절 하드웨어 확인 | 판정된 마크 멈춤 3건 또는 2주, 배터리 비교 3~5일 | 오른쪽 C 약 500줄, 동글 client 약 220줄, Python 약 300줄 |
| 2b, 3, 4 | 항목마다 정한다 | 항목마다 정한다 | 항목마다 정한다 |

'판정된 마크'는 R0(판정 불가)이 아닌 판정을 받은 마크다.

### 1.8 용어

이 문서가 영어로 남긴 말의 뜻이다. 식별자는 영어 그대로 쓴다.

| 용어 | 뜻 |
|---|---|
| 링(E 링, B 링) | 동글 RAM의 순환 버퍼. 가득 차면 가장 오래된 레코드를 지우고, PC가 읽기 전에 지워진 수를 센다(`lost_total`) |
| bin | 100 ms 동안의 수치를 모은 칸. B 링의 BINS 레코드 하나가 1초, 즉 bin 10개다 |
| S0~S6 | 트랙볼 입력이 센서에서 PC까지 가는 길의 관찰 지점(4.2절). S0~S2는 오른쪽, S3~S5는 동글, S6는 PC다 |
| bracket | 처리 앞뒤에 훅을 하나씩 걸어 그 사이 시간을 재는 방식(4.2절) |
| lane | 보고서 타임라인에서 지표 하나가 차지하는 줄. 건강 지표(health lane)는 sysworkq 지연·큐 최고 수위 같은 것이고, 문맥 lane은 레이어·USB·링크 상태다 |
| 최고 수위 | 구간 동안 큐에 가장 많이 쌓였던 항목 수(high-water mark). 큐 크기와 같으면 꽉 찼던 것이다 |
| Σ\|d\| | 이동량 절댓값의 합. Windows가 이벤트를 합쳐도 변하지 않으므로 지점 사이를 개수 대신 이 값으로 비교한다 |
| orphan-X | X 이벤트 뒤에 짝인 Y가 오지 않은 경우. 센서 읽기 1회는 X, Y 한 쌍이므로 Y를 어딘가에서 잃은 흔적이다. 동글 큐가 찬 때만 동글 쪽 유실로 본다 |
| KEYX | 앞뒤가 맞지 않는 키 이벤트. press나 release를 잃은 흔적이다(5.2절) |
| jump | 공백 뒤 재개될 때 쌓인 이동량이 한꺼번에 들어와 커서가 튀는 것 |
| watermark | 스레드가 스택을 가장 깊이 썼을 때 남은 여유 |
| stage | `py -m dbgrec flash`로 UF2를 `staged\` 폴더에 꺼내 두는 것. 그 보드를 부트로더에 넣으면(리셋 두 번) 감시기가 굽고, 구운 파일은 `flashed\`로 옮긴다 |
| 복구 이미지 | 디버그 이미지와 같은 CI 실행에서 같은 커밋으로 빌드한 프로덕션 설정 이미지. 감시기가 디버그 펌웨어를 되돌릴 때 굽는다 |
| 복구가 켜진 상태 | stage한 디버그 동글 이미지를 구운 뒤, 또는 `py -m dbgrec rescue drill` 뒤 10분 동안. 이때만 감시기가 동글에 복구 이미지를 자동으로 굽는다(9.4절) |
| USB serial | 칩마다 고유한 번호(FICR DEVICEID). 부트로더와 ZMK가 같은 값을 내므로 감시기가 보드를 구분하는 데 쓴다(9.4절) |
| supervisor, heartbeat | 에이전트를 띄우고 감시하는 감독 프로세스, 그리고 두 프로세스가 살아 있음을 알리려고 주기적으로 쓰는 파일(`run\*.hb`) |
| 안전 수준 | 부팅 직후 crash가 반복될 때 기록기가 스스로 기능을 줄이는 단계. NORMAL, SAFE, INERT(6.4절) |
| `mode off` | 측정을 끄고 BOOT, LINK, USB, BATT, MARK, MARKCFG, CFG 기록과 crash 기록, HID_1만 남기는 상태. 기록기 자체가 멈춤 빈도를 바꾸는지(관찰자 효과) 비교하는 날에 쓴다(3.3절) |
| gate | 두 뜻이다. CI에서는 빌드를 통과시키는 자동 검사(CI 검사), 오른쪽 송신에서는 보내도 되는 조건(송신 조건, 5.3절)이다 |
| pump | 오른쪽 반의 sysworkq에서 조건이 맞을 때 레코드를 한 건씩 내보내는 송신 작업 |
| handshake, 무장 | 연결마다 동글이 CMD HELLO를 보내야 오른쪽이 송신을 시작한다(무장). 연결이 끊기면 송신을 멈춘다(무장 해제)(6.2절) |
| shadow 구독 | ZMK가 이미 구독한 오른쪽 특성에 동글 기록기가 따로 거는 두 번째 구독. 동글 도착(S3)을 직접 센다(2b) |
| hand-off | notify 버퍼가 호스트에서 BLE 컨트롤러로 넘어가는 시점 |
| 하한 포락선 | (도착 시각 − 보낸 시각) 값들의 아래쪽 끝을 이은 선. 가장 덜 늦게 도착한 레코드가 두 시계의 실제 차이에 가장 가깝다 |
| boot nonce | 부팅마다 새로 뽑는 난수. 서로 다른 부팅의 레코드를 구분한다 |
| pevq, inq, posq, sysq | `peripheral_event_msgq`(동글, 5칸), `input_msgq`(양쪽, 16칸), `position_state_msgq`(오른쪽, 10칸), sysworkq의 줄임말 |

## 2. 기존 디버그 빌드 점검 결과

### 2.1 무엇이었나

브랜치는 `debug-logging` @`0cfce87`(2026-09-30)이다. `config/`는 `my-keymap`과 같고, 로그는 snippet `zmk-usb-logging`(USB CDC ACM 시리얼) 하나로 내보냈다. 동글용 `charybdis_dongle_dbg`(Studio 끔)와 `charybdis_dongle_dbg_zmkdbg`, 오른쪽용 `charybdis_right_dbg`와 `charybdis_right_dbg_fastrest`(REST 샘플 주기 10 ms) 이미지, 그리고 캡처 도구 `tools/capture_log.py`(pyserial)와 `tools/mark_window.ps1`이 있었다. 가짜 pyserial 테스트 14개는 다시 돌려 보니 모두 통과했다. 산출물과 도구의 세부는 그 브랜치의 `docs/debug-logging.md`에 있다.

CI 로그 기준 RAM 증가는 오른쪽 약 53 KB(로그 버퍼 16 KB, CDC 링 두 개 32 KB, 스택), 동글 약 18 KB였다.

### 2.2 상시 사용에 맞지 않았던 이유 (영향 순)

| 문제 | 결과 | 새 방식 |
|---|---|---|
| 오른쪽 반을 케이블로 PC에 연결해야 했다 | 배터리로 쓰면 처음 16 KB 뒤 로그가 모두 사라졌다. 케이블을 꽂으면 VBUS 전원과 충전이 브라운아웃을 가리고 RF 환경도 바뀌었다 | 케이블 없음. 오른쪽은 2단계에서 무선으로 요약만 보낸다 |
| 마크가 캡처 도구 콘솔의 Enter였다 | 다른 앱에 포커스가 있으면 Enter가 그 앱으로 갔고, Alt-Tab만큼(수 초) 늦었다 | 키보드 조합이 동글 타임라인에 바로 남는다(8절) |
| 도구를 손으로 띄워야 했다 | pyserial이 이 PC에 없었고, COM 번호를 매번 쳐야 했다. 세 보드의 VID:PID가 같아(`1D50:615E`) 자동 선택도 못 했다. 파일 회전과 크기 제한이 없어 계속 굴리면 시간당 200 MB 넘게 쌓였다 | 로그온 자동 시작, 표준 라이브러리만 사용, USB serial로 장치 식별(9절) |
| 펌웨어를 바꿔 구워야 했고 Studio가 꺼졌다 | 몇 주 운용과 맞지 않았다 | 동글 이미지 하나, Studio 유지 |
| 텍스트 로그가 많고 유실이 조용했다 | 최대로 굴릴 때 오른쪽 약 34.8 KB/s, 동글 약 25.9 KB/s인데 CDC 링 여유는 0.3~0.5초였다. 넘침 경고는 컴파일되지 않았고, 중간이 잘려 다음 줄과 붙은 줄도 정상 줄처럼 보였다 | 텍스트 없이 수치만 남기고, 모든 구간의 유실 수를 센다(7.5절) |
| 시각이 약했다 | 두 보드 시계는 서로 무관했고(최대 약 100 ppm), 호스트 시각은 27~100 ms 단위라 BLE 지연을 잴 수 없었다 | 동글 uptime을 기준 시계로 PC가 맞춘다(7.4절) |
| 분석이 수작업이었다 | 마크마다 PowerShell과 판정표를 손으로 적용했고, `mark_window.ps1`은 날짜를 무시해 세션을 섞었다 | 마크마다 자동 보고서와 판정(9.7절, 10절) |
| 아예 볼 수 없는 원인이 있었다 | 2.4절 | 2.4절 |

### 2.3 이어받는 것

- H1~H6 가설표와 "처음 어긋나는 지점이 원인 구간"이라는 읽기 원칙. 새 판정 규칙(10절의 R0~R7)이 이 원칙을 자동화한다.
- 센서 읽기 1회에 이벤트 2개가 짝지어진다는 검사. 동글의 orphan-X 검출(X 뒤에 Y가 없으면 유실)로 바뀐다. 이 유실은 오른쪽 입력 큐, 오른쪽 notify, 동글 큐 어디서든 생길 수 있으므로, 동글 큐 수위와 함께 볼 때만 동글 쪽 유실로 본다.
- `_fastrest` A/B 발상. 4단계의 fast-rest 실험으로 이어진다.
- `capture_log.py`에서 쓸모가 확인된 구현 방식. 에이전트가 같은 방식을 쓴다.
  - 재연결 루프
  - (VID, PID, serial, interface)로 장치를 식별하는 방식
  - 막히지 않는 큐
  - 15초 무수신 진단
- 가짜 pyserial 테스트 틀. FakeHid 테스트 틀로 바꿔 쓴다.
- `_dbg` 아티팩트 이름, `config/`를 바꾸지 않는 원칙.
- 소스로 확인된 사실:
  - `ZMK_SLEEP`이 꺼져 있다.
  - IDLE이 센서를 재우지 않는다.
  - 오른쪽 입력 스레드가 `bt_gatt_notify`를 직접 부르며, ATT 버퍼가 없으면 무기한 기다린다.
  - 동글의 split 입력은 `K_NO_WAIT`로 들어간다.

### 2.4 가설 목록의 빈틈

표의 C1~C11은 새 계획의 원인 번호(10.4절), S0~S6은 입력 경로의 관찰 지점(4.2절), R0~R7은 판정 규칙(10.3절)이다. pevq, KEYX 같은 줄임말은 1.8절 '용어'에 있다.

| 빈틈 | 왜 안 보였나 | 새 계획에서 보는 곳 |
|---|---|---|
| 보드 리셋/fault/assert | 리셋 원인을 남기지 않았다. 기본 fatal handler는 IRQ를 잠근 채 영구 정지하므로 fault dump가 CDC 링에 갇힌다 | C9, 1b/2 고장 기록 |
| 스택 넘침 | 스택 가드도 watermark도 없다 | C10 |
| sysworkq 정체 | 센서 읽기와 BLE 송신이 같은 큐인데 지연을 재지 않았다 | 양쪽 health lane |
| notify 막힘 시간 | `input event:` 줄이 notify **이전**에 찍혔다 | S1/S2 bracket (2단계) |
| 동글 큐 유실 | 5칸 `peripheral_event_msgq`의 유실은 표시가 없다 | pevq 최고 수위, orphan-X, KEYX (1b) |
| USB suspend 중 유실 | suspend 중 리포트는 wakeup만 요청하고 0을 반환한다 | C8, R4 |
| 레이어 고착 | 레이어 상태를 남기지 않았다 | C4, 100 ms 레이어 비트 |
| CPI 변경 중 SPI 경합 | `&dpi`가 BT RX에서 page register를 바꾸는 중에 burst read가 끼어들 수 있다 | C6 (2b/3b) |
| 재연결 시 CCC 저장 | 재연결 직후의 settings 쓰기가 오른쪽 sysworkq를 멈춘다 | C11 (2단계) |
| 동글 radio 경합 | 연결 안 된 프로필의 광고, 반이 끊겼을 때의 스캔 | C7 문맥 |

## 3. 설계 원칙

모든 단계가 지키는 규칙이다. 어느 단계도 다른 이득을 위해 이 규칙을 어기지 않는다.

1. **케이블 없음.** 기록하는 동안 두 반은 배터리·무선 그대로다.
2. **Studio 유지.** 동글의 CDC 포트(MI_00/COM33), keymap 저장, behavior 목록이 그대로다.
3. **PC가 끌어온다.** 동글은 PC를 기다리지 않는다. PC가 없는 동안은 동글 RAM 링이 버틴다.
4. **마크는 동글 타임라인에 남긴다.** 키보드 조합이 주 수단이고 PC 단축키는 보조다.
5. **에이전트는 저절로 살아난다.** 로그온 때 자동으로 시작한다. 다음 상황 뒤에도 다시 붙는다.
   - 절전과 최대 절전
   - 동글 뽑기와 동글 리셋
   - 탐색기 재시작
   - 에이전트 자신의 crash
6. **보고서는 자동이다.** 마크마다, 그리고 30분마다 만든다.
7. **유실은 숫자로 센다.** 모든 구간에서 잃은 레코드 수를 센다. "기록할 것이 없었음"과 "잃었음"을 구분한다.
8. **고장 나면 기록하고 리셋한다.** 프로덕션은 fault가 나면 영구 정지한다. 디버그 빌드는 기록을 남기고 리셋한다. 어느 안전 수준에서도 영구 정지는 없다.

### 3.1 타이밍 규칙

- **LL prepare 275 µs.** BLE 링크 계층은 tick 후 약 275 µs 안에 prepare를 끝내야 한다. 넘으면 `LL_ASSERT`로 멈춘다.
  - ISR 안의 작업은 5 µs 이하로 제한한다.
  - spinlock으로 감싼 복사는 114 B 이하(약 2 µs)로 제한한다.
  - 1~2단계 기록기는 로그, UART/CDC 출력, shell을 쓰지 않는다. Studio의 CDC ACM(MI_00)만 프로덕션 그대로 있다.
- **sysworkq.** 오른쪽 반의 sysworkq는 센서 읽기, BLE 송신 pump, CCC 저장을 겸한다. 동글의 sysworkq는 split 이벤트 큐(pevq) 처리, ZMK listener, 마크 behavior, `disconnected` 콜백, HCI 송신을 돈다. 두 보드 모두 다음을 지킨다.
  - 기록기는 sysworkq에서 O(1) 작업만 하고 기다리지 않는다.
  - 오른쪽 송신은 `K_NO_WAIT`로 한 번에 한 건만 한다.
- **HCI 명령은 쓰지 않는다.**
  - `BT_BUF_CMD_TX_COUNT=1`이라, 낮은 우선순위 스레드가 HCI 명령을 내면 동글 sysworkq가 10초 막히고 `BT_ASSERT`로 이어질 수 있다(F7).
  - RSSI는 HCI 대신 2b의 `ll_rssi_get` 변형으로만 읽는다.
- **ATT 요청은 동글 전체에서 한 번에 하나만 둔다.** ZMK의 discovery 이어가기는 `K_NO_WAIT` 할당이 실패하면 조용히 끝나기 때문이다(F25, 2단계).
- **실행 중 flash 쓰기는 없다.**
  - 기록기의 flash 입출력은 부팅 초기(`POST_KERNEL 99`, `bt_enable` 전)와 fault 처리 중(리셋 직전)에만 일어난다.
  - 디버그 펌웨어 때문에 생기는 1회성 settings 쓰기는 6.4절에 모두 적었다.

### 3.2 개인 정보 허용 목록

기록하는 것:
- 카운터, 지속 시간, 큐 깊이, |d| 합
- 링크·USB·전원·잠금 상태, 리셋 원인, 배터리
- 레이어 번호(활동 중 100 ms 단위 비트)
- 마크와 메모
- 반별 초당 키 수, 유실 키 이벤트 수(위치는 없음)
- crash와 스택 레코드의 thread·code 주소

기록하지 않는 것:
- keycode, 키 위치, 키마다의 시각
- 포인터 이동량을 뺀 HID 리포트 내용
- 창 제목, 로그 문자열, BLE 주소

KEYX 검사에 쓰는 '눌린 키 집합'과 '본 적 있는 키 집합'(5.2절)은 동글 RAM에만 있고 밖으로 나가지 않는다. `bundle`로 내보낼 때는 boot nonce와 USB serial을 가린다.

### 3.3 관찰자 효과 통제

관찰자 효과는 기록기 자체가 타이밍을 바꿔 멈춤 빈도가 달라지는 것이다. 다음으로 막고, 남는 영향은 잰다.

- **프로덕션과 같게 두는 값.** 스택 크기, 우선순위, 큐 길이, 연결 파라미터, `BT_BUF_*`, `BT_ATT_TX_COUNT`, USB 설정이다. CI가 같은 CI 실행의 프로덕션(복구) 빌드와 값을 비교하고, 다르면 실패한다. 이 값 하나를 일부러 바꾸는 변형(4단계 `_wq4096`, `_q16`, RSSI 변형, MPU 변형)은 그 항목을 `build-dbg.yaml`의 `allow:`에 적어야 한다.
- **일부러 바꾸는 값.** 목록으로 고정하고 모든 보고서 머리에 찍는다.
  - `INIT_STACKS`, `THREAD_MONITOR`, `BT_CTLR_ASSERT_HANDLER`
  - 동글 `USB_HID_DEVICE_COUNT=2`
  - 오른쪽 `NET_BUF_POOL_USAGE`(2단계)
  - code partition 12 KB 축소
  - RSSI 변형의 `BT_CTLR_CONN_RSSI`(2b만)
- **기준선.** 1a에서 프로덕션 펌웨어로 잰다.
  - 활동 시간당 마크 수
  - 움직이는 중 150 ms 이상 공백의 수(호스트 조건이 맞을 때만 센다, 10.2절)
  - Raw Input 속도
- **`mode off` 날.** 모든 단계에 둔다. 사용자가 `py -m dbgrec ctl mode off`로 켜고, 끝나면 `py -m dbgrec ctl mode normal`로 되돌린다. 이날은 측정(입력 bracket, tick, probe, 키 수, bin, 스택 검사, 2단계 client와 오른쪽 요약)이 꺼진다. BOOT, LINK, USB, BATT, MARK, MARKCFG, CFG 기록과 crash 기록, HID_1은 그대로 남는다.
- **펌웨어 구분.** `flashlog.jsonl`이 각 데이터 행에 당시의 동글·오른쪽 빌드(build_id와 CI 실행 번호)를 붙인다. 서로 다른 펌웨어의 비율을 섞지 않는다.

## 4. 전체 구조

### 4.1 그림

그림은 왼쪽부터 오른쪽 반(2단계), 동글(1b, 기준 시계), PC 순이다. `[S0]`~`[S6]`은 4.2절의 관찰 지점이고, `-->`는 데이터가 가는 방향이다. 왼쪽 반은 모든 단계에서 프로덕션 펌웨어이며, 동글이 받는 키 이벤트와 LINK 기록으로만 보인다. 마지막 줄은 마크가 combo에서 토스트까지 가는 순서다.

```text
RIGHT HALF (stage 2)                  DONGLE (stage 1b, master clock)                 PC
PMW3610 IRQ P0.06 -> [S0 isr count]   BT RX WQ: ZMK notify cb -> pevq(5)              Raw Input WM_INPUT [S6]
sysworkq: burst read -> input_msgq    sysworkq -> input_msgq(16) -> input thread:       hidden window, INPUTSINK
input thread: [S1] split notify [S2]    [S4] input_handler_0 [S5] --USB HID_0 MI_02-->
tick 20 ms (active only)              tick 20 ms: sysworkq lateness, ISR gap, queues    agent (pythonw, supervised)
4 KB TX FIFO, crash page              listeners: key counts, KEYX, USB, link, battery     device thread: HID_1 MI_03
   |                                  rings: E 16 KB (events), B 64 KB (bins)             STATUS 1 Hz, CHUNK pulls
   | zzz_dbgrec_svc notify (20 B)     crash page (flash)                                 writer: day files
   +--- after CMD HELLO ------------> diag client (stage 2) -> E/B --HID_1 128 B feature-->  report subprocess
   <-- CMD: HELLO, MODE, SELFTEST, REQ_CRASH ----
LEFT HALF: production firmware in every stage (seen through its key events and LINK records)
MARK: combo -> dbg_mark (central) -> MARK record -> STATUS.mark_count -> agent toast
```

### 4.2 관찰 지점 S0~S6

| 지점 | 위치 | 의미 | 관찰 방법 | 도입 단계 |
|---|---|---|---|---|
| S0 | 오른쪽 | PMW3610 MOTION 인터럽트(burst read 1회당 1번) | P0.06에 두 번째 `gpio_add_callback` | 2 |
| S1 | 오른쪽 | 입력 스레드가 센서 이벤트를 받음 | `dbgrec_in_a` input callback | 2 |
| S2 | 오른쪽 | `bt_gatt_notify` 반환 | `split_input_handler_0_zz` input callback | 2 |
| S3 | 동글 | BT RX에 알림 도착 | shadow 구독 | 2b |
| S4 | 동글 | 입력 스레드, listener 진입 | `dbgrec_in_a` input callback | 1b |
| S5 | 동글 | listener, processor, HID 전송 끝 | `input_handler_0_zz` input callback | 1b |
| S6 | PC | MI_02 Col03의 Raw Input 리포트 | 에이전트 `WM_INPUT` | 1a |

input callback은 이름순으로 실행된다. 그래서 `dbgrec_in_a`는 ZMK 처리기보다 먼저, `..._zz`는 나중에 돈다. 두 훅이 ZMK 처리 앞뒤에서 시각을 찍으므로, ZMK 코드를 고치지 않고도 그 사이 처리 시간을 잴 수 있다. 이 문서는 이 방식을 bracket이라 부른다.

### 4.3 누가 무엇을 어디에 두나

| 보드 | 저장 | PC까지 | PC가 없을 때 버티는 시간 |
|---|---|---|---|
| 동글 | E 링 16 KB(변화가 있을 때만 쓰는 사건), B 링 64 KB(활동한 초마다 BINS 1개), crash page | HID_1 feature report | E는 며칠, B는 활동 약 10분 |
| 오른쪽 (2) | 4 KB TX FIFO, crash page | `zzz_dbgrec_svc` notify → 동글 → HID_1 | 활동 요약 약 3분 |
| 왼쪽 | 없음 | — | — |
| PC | `%LOCALAPPDATA%\dbgrec\` | 로컬만 | — |

### 4.4 마크의 흐름

1. 사용자가 POINTER를 누른 채 R+T를 친다.
2. 동글의 combo가 `dbg_mark` behavior를 부르고, 동글이 E 링에 MARK를 쓴다. MARK에는 다음이 들어간다.
   - 레이어, USB 상태, 연결된 반의 수
   - 마지막 트랙볼 입력 이후 경과 시간, 마지막 왼쪽·오른쪽 키 이후 경과 시간
   - sysworkq 지연, 큐 깊이
3. 에이전트가 다음 1 Hz STATUS에서 `mark_count`가 바뀐 것을 보고 토스트를 띄운다. 약 1초 걸린다.
4. 60초 뒤 보고서 하위 프로세스가 `reports\mark-<n>.md/.html/.csv`를 쓴다.

PC가 꺼져 있거나 에이전트가 없어도 MARK는 동글에 남는다. 보고서는 에이전트가 따라잡을 때 생긴다.

## 5. 단계별 계획

공통 규칙:

- 각 단계는 작게 나눈다. 단계 하나만으로도 쓸모가 있고, 실기기 확인으로 끝나며, 다음 단계로 갈지 정하는 종료 조건이 있다.
- 동글은 한 동작으로 되돌린다. 동글 리셋을 두 번 누르면 복구 감시기가 프로덕션을 굽는다(복구가 켜진 상태일 때, 9.4절). 오른쪽 반(2단계)은 복구 이미지를 stage하고 케이블을 꽂은 뒤 리셋을 두 번 누른다.
- 키보드가 10분쯤 제대로 안 돼도 괜찮은 날에만 새 단계를 시작한다.
- 노트북 자체 키보드와 터치패드는 언제나 예비 수단이다.

### 5.1 1a단계: PC 안전망과 기준선

내용:
- supervisor, 복구 감시기, `flash` 도구. 1a는 CI bundle `dbgrec-<sha8>` zip을 받아 `py -m dbgrec rescue import <zip>`을 실행하는 것으로 시작한다. 이 명령은 복구 이미지를 `rescue\<sha8>\`에, ELF와 심볼을 `fw\<build_id>-r<run>\<target>\`에 보관하고 `flashlog.jsonl`에 `imported` 항목을 남긴다. 아무것도 stage하지 않는다.
- 캡처 에이전트. 하는 일은 다음과 같다.
  - Raw Input S6를 100 ms 단위로 집계한다.
  - PC 단축키 마크와 원클릭 메모를 받는다.
  - 전원과 잠금 사건을 기록한다.
- 마크별 자동 보고서, `doctor`, `bundle`.
- 디버그 CI workflow: 같은 커밋의 복구 이미지, 호스트 테스트, keymap 검사. 디버그 이미지는 1b부터 빌드한다.
- 펌웨어는 굽지 않는다. 프로덕션 그대로 쓴다.

알 수 있는 것:
- 마크한 순간 PC가 포인터 입력을 계속 받고 있었는지. 받고 있었다면 장치가 아니라 인지나 앱 쪽 문제다.
- 호스트 조건(잠금 해제, input desktop Default, 관리자 창 아님, loop lag 깨끗)이 맞는데 S6가 끊겼는지. 그렇다면 장치나 USB 쪽이다(10.2절).
- x/y 대신 휠이 들어왔는지. 그렇다면 레이어로 빠진 경우다(C4).
- 프로덕션 펌웨어의 기준선: 활동 시간당 마크 수와 공백 수.

규모 [추정]: Python 약 1,000줄, 테스트 150줄, workflow 150줄.

하드웨어 확인(사용자가 실기기에서 한다. 각 항목의 앞 문장은 사용자가 할 동작이고, '~해야 한다', '~이다'로 끝나는 문장은 합격 기준이다. 합격 기준의 값을 어디서 읽는지(`status`, `doctor`, 보고서, CI summary)는 구현할 때 항목마다 정해 적는다):

0. **가져오기.** `py -m dbgrec rescue import <zip>`을 실행한다. `doctor`의 복구 이미지 항목이 OK이고, 아무것도 stage되지 않아야 한다.
1. **복구 훈련.** `py -m dbgrec rescue drill`로 복구를 10분 동안 켠다. 아무것도 stage하지 않은 채 동글 리셋을 두 번 누르고 손을 뗀다. 20초 안에 키보드와 포인터가 돌아오고, `flashlog.jsonl`에 rescue 복사가 남아야 한다(동글 serial 장치가 다시 잡혀야 성공으로 기록된다).
2. 오른쪽 반을 케이블로 부트로더에 넣고 아무것도 stage하지 않는다. 감시기가 굽지 **않아야** 한다.
   - 오른쪽 반을 케이블로 연결해 켜 둔 채(충전 중) `rescue drill` 뒤 동글 리셋을 두 번 누른다. 동글로 인식해 복구해야 한다.
   - 동글을 뽑고, 동글 이미지만 stage한 채 오른쪽 반을 부트로더에 넣는다. 동글 이미지를 굽지 않아야 한다.
   - 복구가 꺼진 상태에서 동글 리셋을 두 번 누른다. 아무것도 굽지 않아야 한다.
3. 굴리는 동안 Raw Input이 MI_02 Col03 장치에서만 오는지 본다(이름의 대소문자는 무시). 백그라운드 수신 속도와 이동량 합(Σ|d|)을 적어 둔다. Windows가 이벤트를 얼마나 합치는지 재는 것이다(A-50). 관리자 권한 작업 관리자를 앞에 둔 채 30초 굴려 WM_INPUT이 계속 오는지도 적는다(A-56).
4. 어떤 앱에 포커스가 있어도 단축키를 치면 1초 안에 토스트가 떠야 한다. 설치 때 단축키 충돌이 없어야 한다.
5. 프로세스 감시를 시험한다.
   - 에이전트를 죽이면 5초 안에 돌아오고 트레이가 다시 보인다.
   - supervisor를 죽이면 에이전트가 60초 안에 되살린다. 그 뒤에도 에이전트는 하나뿐이다(같은 PID).
   - 탐색기를 재시작하면 트레이 아이콘이 돌아온다.
6. S3 절전 하룻밤, S4 최대 절전 한 번을 거친다. 다음 날 녹색이고, 각 프로세스가 하나씩만 있고, 오래된 heartbeat가 없어야 한다. 60초 넘게 잠들었다 깨어난 뒤 에이전트 재시작 기록이 없어야 한다.
7. 잠금 화면과 UAC 프롬프트를 띄운다. 잠금 전환과 desktop 전환이 기록되어야 한다.
8. 개발용 플래그로 250 ms 정지를 넣는다. heartbeat 공백이 기록되어야 하고, lag 랩어라운드 단위 테스트가 통과해야 한다.
9. `doctor`가 모두 OK다. CI에서 복구 이미지가 빌드되고 호스트 테스트와 keymap 검사가 통과한다. 프로덕션 workflow도 그대로 빌드된다.

종료 조건: 프로덕션 펌웨어로 복구 훈련을 통과하고, 기준선을 3일 이상 모은다.

### 5.2 1b단계: 동글 기록기

내용:
- S4/S5 입력 bracket을 100 ms bin으로 집계한다.
- 건강 지표(health lane):
  - sysworkq 지연
  - timer ISR 공백
  - 큐 최고 수위(`peripheral_event_msgq` 5칸, `input_msgq` 16칸)
  - orphan-X
  - listener+HID 처리 시간
- 문맥: 레이어(id), USB 상태, endpoint, BLE 프로필 open/connected, 연결된 반, 배터리.
- 반별 초당 키 수와 유실 키 이벤트(KEYX) 검출.
- 마크: 레이어로 제한한 combo 두 개.
- fault와 LL assert를 기록하고 리셋한다. 스택 watermark를 잰다.
- HID_1 vendor 인터페이스(128 B feature report 3종).
- PC 쪽 판정 규칙 R0~R7.

1b는 무선 트래픽을 하나도 더하지 않는다.

KEYX는 키 하나하나를 기록하지 않고 앞뒤가 맞지 않는 키 이벤트를 센다.
- 마크 combo 위치(16, 17, 23, 35)는 제외한다.
- 반마다 "눌린 키 집합"과 "본 적 있는 키 집합"을 RAM에만 둔다.
- 이미 눌린 키가 또 눌리면 앞의 release를 잃은 것이다. 키나 레이어가 고착되는 원인이 된다.
- 지금 눌려 있지 않은데 이번 연결에서 본 적 있는 키의 release가 오면, 짧은 탭의 press를 잃은 것이다.
- 한 번도 보지 못한 키의 release는 정상으로 본다. 재연결이나 동글 부팅을 걸쳐 키를 누르고 있던 경우다.
- 어느 반이든 연결되면 '본 적 있는 키 집합'을 비운다. 연결 콜백(BT RX)은 epoch 번호만 원자적으로 올리고, 실제로 비우는 일은 sysworkq의 listener가 한다. BLE 호스트 연결은 해당하지 않는다. `mode`가 바뀔 때는 두 집합을 모두 비운다. `off` 동안에는 집합을 갱신하지 않기 때문이다.
- 기록기 listener는 ZMK의 combo와 keymap listener 뒤에서 돈다. combo가 붙잡았다 풀어 준 이벤트는 한 번만 보이고, 발동한 마크 조합의 키 이벤트는 보이지 않는다(마크 위치는 어차피 제외한다). keymap에서 오류를 낸 behavior의 이벤트(예: 실패한 `&bt`)도 보이지 않는다. 이 순서는 CI가 검사한다(11.3절).

알 수 있는 것:
- 동글 내부 정체나 유실(C3), 호스트/USB(C8), 레이어(C4), 동글 리셋과 crash(C9/C10).
- 4초 이상 링크 끊김 또는 오른쪽 리셋. 둘의 구분은 2단계에서 한다.
- radio 경합 문맥(C7), 멈춤이 오른손 타이핑 직후였는지(C1 개연성).
- 위 어디에도 들지 않는 경우가 '상류 무음'이다. 동글의 지표가 모두 정상인데 S4(동글 입력)가 끊긴 경우로, 원인이 동글보다 앞, 즉 오른쪽 반이나 무선 구간에 있다는 뜻이다. 동글 큐가 차지 않았는데 생긴 orphan-X도 상류 쪽 유실로 본다. 이것이 나오면 2단계로 간다.

규모 [추정]: C 약 900줄, Kconfig/DT/CMake 120줄, Python 약 400줄 추가.

하드웨어 확인(동작과 합격 기준의 구분은 5.1절과 같다):
1. `py -m dbgrec flash <zip> dongle`로 stage하고 동글 리셋을 두 번 누른다. 키보드가 동작하고, Studio가 연결되어 keymap을 읽어야 한다. `Get-PnpDevice`로 다음을 확인한다(A-01).
   - MI_00이 여전히 COM33이다.
   - MI_02의 COL01~03이 그대로다.
   - 새 MI_03 vendor HID가 있다.
2. 트레이가 녹색이다.
   - STATUS의 build_id가 stage한 zip과 같다.
   - BOOT의 리셋 원인이 그럴듯하다.
   - 첫 부팅의 local-ID settings 쓰기가 CPU 공백으로 한 번 보인다.
3. 에이전트가 관리자 권한 없이 MI_03을 연다.
   - STATUS GET 1000회의 p95가 1 ms 이하다.
   - CTRL SET이 `last_ctrl_seq`로 확인된다.
   - 선택: USBPcap으로 SET_REPORT의 wLength가 128인지 본다(A-46).
4. 60초 동안 빠르게 굴린다.
   - Base나 POINTER에서(L1/L4/L5가 꺼진 bin) S4 Σ|d|와 S6 Σ|d|의 차이가 1% 이내다. BINS에는 S5 Σ|d|가 없다. 입력 processor는 SYMBOLS, SCROLL, SNIPE에만 걸려 있다.
   - sysq 지연 최대가 5 ms 미만이다.
   - orphan이 0이다.
   - S6 속도가 1a 기준선과 같은 범위다.
5. 두 조합 모두 2초 안에 토스트가 뜨고 src가 맞다. Base에서 R, T, [, '를 빠르게 쳐도 마크가 생기지 않는다.
6. POINTER를 누른 채 SCROLL을 12초 누르고 굴린다. 보고서에 L4 12초와 S6 휠이 나와야 한다(C4).
7. 오른쪽 반을 다섯 번 껐다 켠다. 끈 뒤 약 4초에 LINK disc 0x08이 나오고, 재연결되고, 트랙볼이 정상이어야 한다. 왼쪽 반도 같다.
8. selftest를 실행한다.
   - `oops`, `llassert`, `llassert_isr`, `fault_isr`를 각각 5회 한다. 일부는 굴리는 중에, 한 번은 Studio 저장 중에 한다.
   - 매번 3초 안에 키보드가 돌아와야 한다.
   - slot이 유효하고 함수+오프셋과 thread로 해석되어야 한다.
   - `early`를 2회 하면 STATUS level이 SAFE가 된다. 60초 뒤 STATUS의 현재 GPREGRET2 값에서 조기 crash 수가 0이 되고, selftest `reboot` 뒤에는 NORMAL로 돌아와야 한다.
   - 리셋을 한 번 누르면 GPREGRET2가 0이 되어야 한다(A-22r).
   - 복구 동작이 여전히 통해야 한다.
9. 뽑았다 꽂기, S3 하룻밤, 최대 절전 한 번을 거친다. 설명되지 않는 유실이 없어야 한다. 최대 절전 뒤의 POR은 정상으로 표시되어야 한다(A-20).
10. 30분 섞어 쓴 뒤 스택 여유가 모두 256 B 이상이어야 한다. 대상은 sysworkq, input, BT RX, usbd_workq, dbgrec이다.
11. 계속 관찰한다(합격 조건은 아니다). 3일 이상 활동 시간당 마크 수를 1a와 비교한다. `mode off` 날을 최소 2일 둔다.

종료 조건: 판정된 마크 멈춤 3건, **또는** 2주.

결과별 다음 단계:

| 1b 판정 | 다음 |
|---|---|
| 상류 무음 | 2단계. 대부분 직전에 오른손 타이핑이 있었다면 `_fix3110` 오른쪽 변형을 먼저 |
| 동글 내부 | 2b(정확한 S3−S4) 또는 4단계 `_wq4096`/`_q16` |
| 호스트/USB | 허브 대신 PC 직결 A/B (Q14) |
| 레이어 | 2b 키 상태 비교 |
| 동글 리셋 | crash 해석. C10이면 3단계 MPU 변형 |
| 이상 없음 | 앱이나 인지 쪽 |

### 5.3 2단계: 오른쪽 최소 기록기

전제: 1b 판정이 상류를 가리키고, 오른쪽 복구 훈련을 통과했다.

내용(오른쪽):
- 계측 항목:
  - S0 ISR 수, S1/S2 notify 시간
  - sysworkq 지연, MOTION 핀 고착
  - `input_msgq`/`position_state_msgq` 최고 수위
  - `att_pool` 여유, 키 수
- 보내는 레코드:
  - 활동한 초마다 20 B 요약(SUM_R) 하나
  - 이상 구간마다 ANOM_R 하나
  - 쉬는 동안 1분마다 HB_R
- 보낸 레코드는 완료 콜백에서 seq로 확인한 것만 지운다. FIFO(4 KB)가 차면 SUM_R/HB_R부터 버리고 `tx_lost`로 센다. 보낼 것이 없으면 pump는 깨어나지 않는다.
- 전송 통로는 자체 GATT 서비스 `zzz_dbgrec_svc`의 notify다. 암호화된 연결에서만 읽을 수 있다(READ_ENCRYPT). 오른쪽은 연결마다 동글의 CMD HELLO를 받은 뒤에만 보낸다(handshake, 6.2절).
- 다음 조건(송신 조건, gate)이 모두 맞을 때만 `K_NO_WAIT`로 한 건 보낸다.
  - 입력 큐가 비어 있다.
  - notify 중이 아니다.
  - `position_state_msgq`가 비어 있다. split notify 스레드가 이미 꺼낸 키 notify는 다음 ATT 버퍼 조건으로만 보호된다.
  - ATT 버퍼가 2개 이상 남아 있다.
  - 직전 전송 뒤 50 ms가 지났다.

내용(동글): diag client(`DBGREC_CLIENT=y`). 보안 연결(L2 이상) 10초 뒤부터, 동글 쪽 활동(S4 이벤트, 키 이벤트)이 1초 이상 없을 때만 서비스를 찾고 구독한다. 요청마다 이 조건을 다시 확인하고, 동글 전체에서 ATT 요청은 한 번에 하나만 둔다. 구독 뒤 CMD HELLO를 보내고 5초 안에 HELLO_R가 오지 않으면 연결당 최대 3번 다시 보낸다(오른쪽은 반복 HELLO에 HELLO_R와 BOOT_R만 다시 보낸다). 세 번 모두 실패하면 DIAG `no_hello`를 남긴다.

알 수 있는 것: C1(B2 루프) 대 C2(무선) 대 C5(센서) 대 C11(재연결 CCC 저장), 오른쪽 리셋과 crash.

규모 [추정]: 오른쪽 C 약 500줄, 동글 client 약 220줄, Python 약 300줄.

하드웨어 확인(동작과 합격 기준의 구분은 5.1절과 같다):
1. 오른쪽 복구 훈련: `py -m dbgrec flash <zip> right --rescue`로 프로덕션 오른쪽 이미지를 stage하고, 케이블을 꽂고, 리셋을 두 번 누른다. 처음에는 `py -m dbgrec learn right`나 트레이 확인으로 오른쪽 serial을 기록한다.
2. `py -m dbgrec flash <zip> right`와 `py -m dbgrec flash <zip> dongle --target dongle_dbg2`로 stage하고, 오른쪽은 케이블을 꽂아, 각 보드의 리셋을 두 번 누른다. 케이블을 뺀 뒤 재페어링 없이 트랙볼과 오른쪽 키가 동작해야 한다. 1회성 쓰기는 6.4절대로 일어나야 한다.
3. 볼이 멈춘 뒤 약 15초 안에 DIAG가 `live`가 되어야 한다. 오른쪽 전원을 10번 껐다 켜도 매번 HELLO_R가 오고 트랙볼이 동작해야 한다. 같은 연결에서 HELLO를 3번 보낸 뒤(`py -m dbgrec diag hello`) 동글을 리셋해도 오른쪽이 5초 안에 다시 연결되어야 한다(HELLO 직후 약 20 ms에 리셋하는 경우도 확인).
4. 굴리는 동안 SUM_R가 약 초당 1개 온다. 입력 큐가 차 있거나 notify 중일 때 보내지 않았음을 `gate_blocked`로 확인한다.
5. **B2 유발.** 30초 동안 굴리면서 오른손으로 빠르게 타이핑한다. posq 최고 수위 10, 약 100 ms 단위의 sysworkq 지연, notify 50 ms 이상의 ANOM_R이 나와야 한다. 이때 멈춤이 나면 C1로 판정되어야 한다.
6. **RF 유발.** 오른쪽 반을 가리거나 잠깐 멀어진다. sysworkq는 건강한데 notify가 막힌 ANOM_R이 나와야 한다(C2). 범위 밖으로 나가면 양쪽에 0x08이 나와야 한다.
7. `py -m dbgrec selftest right oops --i-know`를 실행한다. 재연결 뒤 CRASH_R가 전달되고 트랙볼이 3초 안에 돌아와야 한다.
8. 30분 뒤 오른쪽 스택 여유가 모두 256 B 이상이어야 한다. 대상은 input 1024, sysworkq 2048, BT RX 2200, split notify 756, dbgrec 1024, 인터럽트 스택 2048이다(A-55).
9. 3~5일 동안 오른쪽 배터리 감소 기울기가 1b 대비 약 2% 이내여야 한다. `mode off` A/B 날을 둔다.

종료 조건: 판정된 마크 멈춤 3건, 또는 2주. 그 뒤 해당하는 3단계 항목이나 4단계 변형으로 간다.

### 5.4 2b·3·4단계: 답할 질문이 생겼을 때만

각 항목은 답할 질문이 정해졌을 때만 만든다.

| 단계 | 항목 | 답하는 질문 |
|---|---|---|
| 2b | shadow 구독(S3) | 동글이 받은 알림 중 몇 개를 잃었나(정확한 C3), 놓친 release의 증명 |
| 2b | 키 상태 비교(D-KEYDESYNC, D-STUCKLAYER) | 레이어 고착의 원인 |
| 2b | RSSI 변형 `dongle_dbg_rssi` | C2의 신호 세기 근거 |
| 2b | CPI_STEP | `&dpi` 직후의 멈춤인가(C6) |
| 2b | ACL credit, 판정 토스트 | 무선 혼잡, 즉시 피드백 |
| 3 | 오른쪽 pin/upload, wrap pack(`--wrap`), PMW3610 진단 패치, WRN 로그 카운터, MPU 스택 가드 변형, HTML 타임라인 | 단일 사건의 결정적 증거 |
| 4 | `_fix3110`, `_q16`, `_wq4096`, `_llfix`, `_llstats`, fast-rest | 어떤 수정이 활동 시간당 멈춤을 줄이나 |

**2b의 shadow 구독.** ZMK가 이미 구독한 오른쪽 특성에 동글 기록기가 구독을 하나 더 걸어, 동글에 도착한 알림(S3)을 직접 센다. ZMK의 구독을 방해하지 않도록 세 가지를 지킨다. ZMK의 구독이 먼저 걸렸는지는 CCC 값이 아니라 SENT 플래그로 확인하고(F1), 데이터 콜백에서 `BT_GATT_ITER_STOP`을 돌려주지 않으며, `bt_gatt_unsubscribe`를 부르지 않는다. 2단계 client가 일주일쯤 문제없이 돈 뒤에만 시작한다. 근거는 영문 명세 §10.1에 있다.

**4단계 fast-rest.** 오른쪽 센서의 REST 샘플 주기를 실행 중에 바꾸는 A/B다.
- 센서 전류가 조금 는다(Q9).
- 드라이버가 downshift 시간을 컴파일 시점의 샘플 주기에 맞춰 두었으므로 downshift 값도 함께 고쳐 써야 한다.
- `dpi_cyc`의 CPI 쓰기와 겹치지 않게 순서를 정해 실행한다.

**4단계 변형 이름.**
- `_fix3110`: ZMK 커밋 5b51501을 cherry-pick한 오른쪽 이미지
- `_q16`: 동글 `peripheral_event_msgq`를 5칸에서 16칸으로 늘린 이미지(`CONFIG_ZMK_SPLIT_BLE_CENTRAL_POSITION_QUEUE_SIZE`)
- `_wq4096`: sysworkq 스택을 2048에서 4096으로 늘린 이미지(`CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE`)
- `_llfix`: Zephyr LL 수정 커밋 355648a, cd0c5fc, d04563f를 적용한 이미지
- `_llstats`: 약 40줄짜리 LL 카운터 패치를 넣은 이미지

`_q16`과 `_wq4096`은 3.3절 '프로덕션과 같게 두는 값'을 일부러 바꾸므로, 그 항목을 `build-dbg.yaml`의 `allow:`에 적어 CI 비교에서 예외로 둔다. RSSI 변형(`BT_CTLR_CONN_RSSI`)과 3단계 MPU 변형도 같다.

## 6. 보드별 구성

### 6.1 동글 (1b, 2단계에서 client 추가)

| 목적 | 훅 | 실행 문맥 |
|---|---|---|
| S4 | `INPUT_CALLBACK_DEFINE_NAMED(DEVICE_DT_GET(DT_NODELABEL(trackball_split)), dbgrec_in_pre, NULL, dbgrec_in_a)` | input thread |
| S5 | `INPUT_CALLBACK_DEFINE_NAMED(…, dbgrec_in_post, NULL, input_handler_0_zz)` | input thread |
| 큐 깊이 | `extern struct k_msgq peripheral_event_msgq`, `input_msgq` | 20 ms `k_timer` ISR |
| sysworkq 지연 | `k_work_submit(&probe_work)` 후 경과 시간 | tick, sysworkq |
| 키 | `ZMK_LISTENER(dbgrec_keys)` + `zmk_position_state_changed` (항상 BUBBLE) | sysworkq |
| 반 구분 | 컴파일 시점 위치 마스크, 실행 중 slot→반 학습(SRCMAP) | sysworkq |
| 링크 | `BT_CONN_CB_DEFINE(dbgrec_conn)` | BT RX WQ, `disconnected`만 sysworkq |
| 문맥 | `zmk_usb_conn_state_changed`, `zmk_endpoint_changed`, `zmk_ble_active_profile_changed`, `zmk_peripheral_battery_state_changed`, bin마다 `zmk_keymap_layer_state()` 등 poll | sysworkq, dbgrec thread |
| 마크 | `dbg_mark` behavior(`BEHAVIOR_LOCALITY_CENTRAL`, parameter metadata 없음), combo 2개 | sysworkq |
| 마크 설정 점검 | `zmk_keymap_layer_index_to_id()`, `zmk_behavior_get_binding()` | dbgrec thread, 60초마다 |
| HID_1 | `SYS_INIT(dbgrec_hid1_init, APPLICATION, 90)`. 모든 안전 수준에서 무조건 등록 | usbd_workq(협조형 −1, 1 KB 스택) |
| 고장 | `k_sys_fatal_error_handler`, `bt_ctlr_assert_handle` | fault 문맥 |
| 부팅 | `SYS_INIT(dbgrec_early, POST_KERNEL, 99)` | `bt_enable` 전 |
| 스택 | `k_thread_foreach_unlocked()` + `k_thread_stack_space_get()` | dbgrec thread(우선순위 14) |
| diag client (2) | `bt_gatt_discover`, `bt_gatt_subscribe`(VOLATILE은 `atomic_set_bit`으로), `bt_gatt_write_without_response_cb` | dbgrec thread, BT RX |

tick 지연(ISR 공백)은 만료 함수 안에서 `k_cycle_get_32() − k_uptime_ticks()`로 잰다. 만료 함수 안의 uptime은 예정 시각이라 `k_uptime_get()`만 쓰면 항상 0이 된다. probe의 제출 시각도 cycle 값으로 찍는다. 오른쪽 tick도 같다.

설정:

| 항목 | 값 |
|---|---|
| snippet | `-S studio-rpc-usb-uart -S dbgrec-common -S dbgrec-dongle` |
| 공통 | `CONFIG_DBGREC=y`, `CONFIG_BT_CTLR_ASSERT_HANDLER=y`, `CONFIG_INIT_STACKS=y`, `CONFIG_THREAD_MONITOR=y` |
| 동글 | `CONFIG_USB_HID_DEVICE_COUNT=2`(프로덕션은 1), `CONFIG_DBGREC_HID1=y` |
| 링, tick | `DBGREC_ERING_KB=16`, `DBGREC_BRING_KB=64`, `DBGREC_TICK_MS=20`, `DBGREC_BINQ=32` |
| 스레드 | `DBGREC_THREAD_PRIO=14`, 스택 1280 |
| 2단계 | `-DCONFIG_DBGREC_CLIENT=y` (`dongle_dbg2`) |
| 그대로 | `CONFIG_USB_REQUEST_BUFFER_SIZE=128`, 모든 스택·큐·우선순위 |
| partition | `code_partition` 0x26000+0xC3000(12 KB 축소), `dbgrec_partition` 0xE9000+0x3000, `storage_partition` 그대로 |

**HID_1 리포트를 128 B로 정한 이유(F4).**
- Windows는 feature SET을 collection의 FeatureReportByteLength까지 채워 보낸다.
- Zephyr는 wLength가 `CONFIG_USB_REQUEST_BUFFER_SIZE`(128)를 넘으면 stall한다.
- 그래서 세 리포트를 모두 ID 포함 정확히 128 B로 만들었다. USB 설정은 프로덕션 값 그대로 둔다.

**HID_1의 인터페이스 번호(F6).**
- CDC ACM이 정확히 하나일 때 HID_1은 interface 3(MI_03), EP 0x84가 된다. 기존 interface와 endpoint 번호는 움직이지 않는다.
- CI가 `zephyr,cdc-acm-uart` 노드가 하나뿐인지 검사한다.
- `USB_HID_DEVICE_COUNT=2`인데 HID_1을 등록하지 않으면 MI_03이 깨진 채 열거된다. 그래서 어느 안전 수준에서도 등록은 무조건 한다.

### 6.2 오른쪽 반 (2단계)

| 목적 | 훅 | 실행 문맥 |
|---|---|---|
| S0 | `gpio_init_callback` + `gpio_add_callback` (P0.06). 드라이버 초기화(POST_KERNEL 90) 뒤인 POST_KERNEL 99에 등록하므로 드라이버 콜백보다 먼저 실행된다. 핀 설정은 건드리지 않는다 | GPIO ISR, 1 µs 이하(tick을 시작할 때 한 번 약 5~10 µs) |
| S1 | `INPUT_CALLBACK_DEFINE_NAMED(trackball, …, dbgrec_in_a)` | input thread |
| S2 | `…, split_input_handler_0_zz` | input thread |
| tick | 20 ms `k_timer`, 활동 중에만. ISR·키·명령으로 시작한다. 5초 동안 ISR·키가 없고, MOTION이 비활성이고, notify 중이 아니고, 큐가 비어 있고, 열린 이상 구간이 없을 때만 멈춘다 | ISR |
| 큐 | `extern input_msgq`, `position_state_msgq` | tick |
| ATT 여유 | `STRUCT_SECTION_FOREACH(net_buf_pool, p)`로 `"att_pool"`을 찾아 `avail_count`를 읽는다 | tick |
| 키 | `zmk_position_state_changed` listener. 수만 센다 | sysworkq |
| 링크 | `BT_CONN_CB_DEFINE` → LINK_R. 다음 handshake까지 보관 | BT RX, sysworkq |
| 서비스 | `BT_GATT_SERVICE_DEFINE(zzz_dbgrec_svc, …)`: TLM notify(READ_ENCRYPT) + CMD write-without-response | BT RX(명령), sysworkq(pump) |
| 고장, 부팅, 스택 | 동글과 같은 방식, 자체 crash page | — |

설정: snippet `-S dbgrec-common -S dbgrec-right`, `CONFIG_DBGREC_ATT_POOL=y`(`NET_BUF_POOL_USAGE`를 선택한다), `DBGREC_TXFIFO_KB=4`, 스레드 우선순위 14, 스택 1024.

**서비스 이름이 `zzz_`로 시작하는 이유.** static 서비스는 이름순으로 배치된다. 그래서 이 서비스는 ZMK의 `split_svc`와 `bas` 뒤에 붙는다. ZMK의 핸들과 bond에 저장된 CCC가 그대로 유지된다(A-07, CI 심볼 검사).

**handshake가 필요한 이유(F3).**
- 오른쪽은 bond된 central의 CCC를 저장해 두었다가 재연결 때 복원한다.
- 그래서 동글이 아직 다시 구독하지 않았는데도 오른쪽은 구독된 줄 알고 보낸다.
- 동글 host는 맞는 구독이 없는 알림을 버린다.
- 그래서 오른쪽은 연결마다 동글의 CMD HELLO를 받은 뒤에만 송신을 시작하고(무장), 연결이 끊기면 바로 멈춘다(무장 해제).
- 연결 참조(`bt_conn_ref`)는 무장할 때 하나만 잡고, `disconnected` 콜백에서만 놓는다. 명령 처리기(BT RX)는 참조를 잡지 않고 연결 번호(epoch)만 남긴다. pump는 그 번호가 지금 연결과 같을 때만 무장한다.
- 같은 연결에서 HELLO가 다시 오면 참조를 더 잡지 않고 HELLO_R와 BOOT_R만 다시 보낸다.
- 오른쪽의 연결 슬롯은 하나뿐이다(`BT_MAX_CONN=1`). 참조가 새거나 두 번 풀리면 리셋할 때까지 다시 연결되지 않는다.

### 6.3 왼쪽 반

- 모든 단계에서 프로덕션 펌웨어(복구 이미지와 같은 빌드)다. dbgrec 모듈이 들어가지 않으므로 기록기 코드가 없다.
- 동글이 왼쪽의 키 이벤트(초당 수), LINK 기록, 배터리로 관찰한다.
- 멈춤 중에 왼쪽 키가 들어오면 동글 radio는 살아 있다는 뜻이다.

### 6.4 고장 기록과 안전 수준 (동글, 오른쪽 공통)

**crash page.** `dbgrec_partition`(0xE9000, 12 KB) 중 첫 4 KB(0xE9000~0xE9FFF)를 64 B slot 64개로 쓴다. 나머지 0xEA000~0xEBFFF 8 KB는 어느 단계에서도 쓰지 않는 예비 공간이다(중간안의 ping-pong page와 부팅 로그 자리였다). 나중에 code partition을 다시 옮기지 않으려고 남겨 둔다.
- 부팅 초기에 빈 slot을 찾아 둔다.
- 다 찼을 때만 이 시점에 지운다. 약 85~90 ms 걸리고, radio가 켜지기 전이다.

**fault 처리 순서(F10).**
1. IRQ를 잠근다.
2. 재진입 latch를 확인한다.
3. GPREGRET2에 고장 종류와 조기 crash 수를 쓴다. 부팅 30초 안의 crash면 수를 1 올리고, 그 뒤의 crash면 0으로 되돌린다. slot을 쓸 때만 bit 7을 켠다.
4. 다음 조건이 모두 맞을 때만 slot에 64 B를 쓴다. CRC는 마지막에 쓴다.
   - 안전 수준이 NORMAL이나 SAFE다(INERT가 아니다).
   - 부팅 코드가 준비 표시를 남겼다.
   - 주소가 partition 안이다.
   - 대상 16 word가 모두 지워진 상태다.
5. `sys_reboot(SYS_REBOOT_WARM)`으로 리셋한다. 어느 경우에도 멈추거나 반환하지 않는다.

**부팅(F9).** `NRF_POWER->RESETREAS` 원값을 저장한 뒤 지운다. hwinfo가 해석한 플래그는 쓰지 않는다.

| 수준 | 조건 | 기록기 |
|---|---|---|
| NORMAL | 부팅 뒤 30초 안에 난 crash(조기 crash)가 연달아 1번 이하 | 전부 |
| SAFE | 연속 조기 crash 2~4번 | HID_1(STATUS와 crash page)만. slot은 이미 지워진 것에만 기록 |
| INERT | 연속 조기 crash 5번 이상 | HID_1 STATUS만(MI_03이 깨지지 않게). flash 쓰기 없음 |

- 60초 동안 문제가 없으면 GPREGRET2의 조기 crash 수를 지운다. 이 일은 SAFE와 INERT에서도 한다(기록기 상태가 필요 없는 일회성 work). 수준 자체는 다음 부팅 때 바뀐다. STATUS에는 부팅 때의 값과 현재 GPREGRET2 값이 함께 들어 있다.
- 30초가 지난 뒤의 crash는 조기 crash 수를 0으로 되돌린다.
- 훅은 컴파일 때 등록되므로 SAFE와 INERT에서는 각 훅이 수준을 보고 바로 돌아간다. 마크 조합은 어느 수준에서나 R/T를 붙잡는다. SAFE와 INERT에서는 MARK 레코드 없이 `mark_count`만 올려 토스트는 뜨게 한다.
- 오른쪽 반에는 HID_1이 없다. 오른쪽 SAFE에서는 자체 서비스, 명령 처리, handshake, pump만 돌고 HELLO_R, BOOT_R, CRASH_R만 보낸다. INERT에서는 HELLO 뒤 HELLO_R와 BOOT_R만 보내고 flash는 건드리지 않는다. BOOT_R의 level로 동글과 트레이가 오른쪽 수준을 안다.
- 리셋을 한 번 누르면 GPREGRET2가 지워져 NORMAL로 돌아간다.
- 두 번 누르면 부트로더로 들어가고, 복구 감시기가 프로덕션을 굽는다.

디버그 펌웨어 때문에 생기는 1회성 flash 쓰기:

| 보드 | 언제 | 무엇 |
|---|---|---|
| 동글 | 첫 디버그 부팅 | `dbg_mark`의 behavior local-ID settings 항목 |
| 동글/오른쪽 | 부팅 때 crash page가 다 찼을 때 | 4 KB 지우기 1회(radio 전) |
| 오른쪽 | 첫 디버그 부팅, 그리고 롤백 뒤 첫 프로덕션 부팅 | `bt/hash` 1회. 새 서비스 때문에 GATT DB hash가 바뀌어서, 부팅 중 `settings_load` 안에서 쓴다. CF(Client Features) 항목은 Client Supported Features를 쓴 peer에만 있어 여기서는 생기지 않는다 |
| 오른쪽 | 첫 TLM 구독 | TLM 특성의 CCC 항목 |

롤백 뒤 동글에 남는 local-ID 항목과 오른쪽에 남는 TLM CCC 항목은 무시되며 해롭지 않다. 보고서는 바로 이 부팅들에서만 CPU 공백을 예상하고 그렇게 표시한다.

## 7. 기록 형식 요약

바이트 배치는 영문 명세 §8과 §9.2에 있다. 펌웨어 `rec.h`의 `_Static_assert`와 Python `schema.py`의 상수를 CI가 비교한다.

### 7.1 동글 링

| 링 | 크기 | 내용 | 보존 |
|---|---|---|---|
| E (space 0) | 16 KB | 변화가 있을 때만 쓰는 사건: BOOT, LINK, MARK, USB, BATT, STACK, CFG, KEYX, MARKCFG, SRCMAP, AGENT, SELFTEST, (2) RELAY_E, DIAG, (2b) ZMKSUB | 며칠 |
| B (space 1) | 64 KB | 활동한 초마다 BINS 하나(108 B), (2) RELAY_S, (2b) SHADOW | 활동 약 10분 |
| crash (space 2) | flash 4 KB | 64 B slot 64개 | 지울 때까지 |

**레코드.** 머리 8 B(길이, 종류와 출처, seq16, 동글 uptime ms) 뒤에 내용이 온다. 전체가 114 B 이하라 CHUNK 하나에 들어간다.

**BINS.** 1초를 100 ms bin 10개(각 9 B)로 담는다.
- bin마다 담는 것:
  - S4 이벤트 수, Σ|d|, 최대 공백
  - S5 리포트 수, listener+HID 최대 시간
  - sysworkq 최대 지연, 큐 최고 수위(입력 큐는 0~16을 그대로 담는다. 16은 가득 차서 버려지는 상태다)
  - 레이어 비트(L1/L2/L4/L5/L6), 연결된 반 수, USB suspend
- 초 머리에 담는 것: 왼쪽·오른쪽 키 수, ISR 공백 최대, orphan 수, KEYX 수, 플래그.

**활동한 초.** 그 초나 앞 2초에 다음 중 하나가 있던 초다.
- S4 이벤트, 키, S5 리포트
- 20 ms 이상의 지연
- 문맥 변화

쉬는 초에는 아무것도 쓰지 않는다. 링 seq가 연속이므로 쉰 것과 잃은 것이 구분된다.

**시간 값.** 1바이트 `enc_ms8`로 담는다. 0~254 ms는 2 ms 단위, 그 위는 16 ms 단위로 2288 ms까지다.

### 7.2 HID_1 리포트

| ID | 이름 | 방향 | 내용 |
|---|---|---|---|
| 1 | STATUS | GET | 매직 "DBR3", 안전 수준, build_id와 CI 실행 번호, mode, 플래그, boot_nonce, RESETREAS 원값, 부팅 때와 현재의 GPREGRET2, 64비트 uptime, 링별 head/oldest/read seq, `lost_total`, `mark_count`, 레이어, 연결된 반 |
| 2 | CTRL | SET | SEEK, MODE, SELFTEST(매직 필요), SLOTMAP, AGENT, (2) RIGHT_CMD |
| 3 | CHUNK | GET | 링 읽기 커서부터 통째 레코드 최대 114 B, `first_seq`, `lost_before` |

USB 문맥(usbd_workq)에서는 O(1) 작업만 한다.
- SEEK는 현재 커서나 직전 chunk의 시작만 받는다. 그 밖의 값이 오면 가장 오래된 곳으로 간다.
- USB 문맥에서 링을 훑는 일은 없다.

### 7.3 오른쪽 레코드 (2단계)

머리 7 B와 내용 13 B 이하를 합쳐 notify 하나가 20 B 이하다. ATT MTU를 교환하지 않으므로 27 B ACL 조각 하나에 들어가야 한다.

| 종류 | 언제 |
|---|---|
| HELLO_R, BOOT_R | 매 handshake 직후 |
| CRASH_R | handshake 뒤 최신 유효 slot 2개까지, 그리고 요청할 때 |
| LINK_R | 링크 사건. 송신이 멈춘 동안 생긴 것은 보관했다가 다음 handshake 뒤에 보낸다 |
| SUM_R | 활동한 초마다. 100 ms bin별 ISR/S2 유무 마스크, notify·sysworkq·ISR 공백 최대, 큐 최고 수위(입력 큐 16칸이 가득 찼는지는 별도 비트), 핀 고착, 키 수, 재개 때의 jump |
| ANOM_R | 이상 구간이 끝날 때 하나(notify ≥50 ms, sysworkq ≥50 ms, 핀 ≥50 ms, S2 없는 ISR ≥150 ms 등). 초당 5개, 분당 60개 이하 |
| HB_R | 쉬는 동안 60초마다(64비트 uptime 상위, 배터리, `tx_lost`) |
| STACK_R, CMD_ACK | handshake 뒤와 30분마다, 명령마다 |

펌웨어가 스스로 판정하는 것은 ANOM_R의 복합 조건 하나뿐이다. 나머지 임계값은 모두 Python에 있다.

### 7.4 시각 맞추기

- **동글 uptime이 기준 시계다.**
  - STATUS에 get_report 안에서 잡은 64비트 uptime과 cycle 값이 들어 있다.
  - 에이전트는 GET 앞뒤를 QPC로 감싼다. RTT 1 ms 이하인 표본으로 부팅마다 직선을 맞춘다. 오차는 ±0.3 ms [추정]이다.
- **오른쪽 → 동글(A-27).**
  - relay마다 동글 도착 시각을 찍고 오른쪽의 `t_ms`도 함께 둔다.
  - PC는 10분마다 (도착 시각 − 오른쪽 시각)의 하한 포락선을 잡고, 드리프트(100 ppm 이하)를 직선으로 맞춘다.
  - 송신 조건 때문에 늦게 보내진 레코드는 포락선 위에 놓이므로 걸러진다.
- **랩어라운드.** 레코드는 32비트 ms라 49.7일마다 되돌아간다. STATUS uptime64와 HB_R/BOOT_R의 상위 비트가 기준점이 된다.
- **PC(F21).** `GetMessageTime`은 32비트로 되돌아간다. 그래서 lag를 `(GetTickCount() − GetMessageTime()) & 0xFFFFFFFF`로 계산하고, 2^31 이상은 0으로 본다.

### 7.5 유실 계산

| 구간 | 유실이 보이는 곳 |
|---|---|
| 동글 링 | CHUNK `lost_before`, STATUS `lost_total`, `bins_lost` |
| crash page | `crash_page_erases` |
| 오른쪽 FIFO | HB_R `tx_lost`와 seq 공백. 끊기기 직전 컨트롤러에 넘어간 레코드는 사라지고 seq 공백으로만 보인다. 드물게 생기는 중복은 직전 HELLO_R의 boot_nonce와 seq로 제거 |
| PC 파일 | 블록 CRC. 끝이 잘린 마지막 블록은 잘라 내고 센다 |
| Raw Input | Windows가 이벤트를 합치는 것은 유실이 아니다(공백과 Σ\|d\|로 비교) |
| 에이전트 부재 | AGENT 레코드(gap_s)와 PC 전원 기록 |

## 8. 마크 방법과 피드백

### 8.1 조합

| 상황 | 조합 | 손가락 |
|---|---|---|
| 평소 | **POINTER** 누른 채 **R+T** | POINTER 왼손 엄지, R·T 왼손 검지 |
| SYMBOLS가 고착된 듯할 때 | **`[`**(위치 23) + **`'`**(위치 35) | 오른손 새끼, 바깥 열의 2·3번째 줄 |
| 키보드 조합이 불편하거나 안 될 때 | **Ctrl+Alt+Shift+M** (PC 단축키) | Ctrl 왼손 새끼, Shift 오른손 새끼, Alt 왼손 엄지, M 오른손 검지 |

규칙:
- R과 T를 모두 누를 때까지 POINTER를 누르고 있는다(둘 다 뗄 때까지 누르고 있어도 된다). R을 누른 뒤 T를 누르기 전에 POINTER를 놓으면, 붙잡혀 있던 R은 아직 POINTER 레이어에서 처리되어 아무것도 입력하지 않는다. 그러나 그 뒤에 누른 T는 Base에서 처리되어 "t"가 입력된다.
- SYMBOLS가 고착되었을 때는 POINTER 키를 쓰지 않는다. SYMBOLS 레이어에서 그 키는 RAlt라 한/영이 바뀐다.
- PC 단축키 마크(HOSTMARK)는 시계 맞춤으로 동글 타임라인에 놓인다. 키보드 마크보다 덜 정확하다.

### 8.2 레이어별 동작

combo는 가장 높은 활성 레이어의 **index**로 걸러진다. 레이어 순서는 Base…Extra = 0…6이다.

| 레이어 | 효과 |
|---|---|
| Base (0) | combo가 없다. R/T/[/'에 지연이 없다 |
| SYMBOLS (1) | `dbg_mark_sym`. 23/35가 `&none`이라 어긋난 조합은 아무것도 입력하지 않는다 |
| POINTER (2) | `dbg_mark_ptr`. 16/17이 `&none`이다 |
| DANGER (3) | 일부러 제외했다. 17이 `&bootloader`다 |
| SCROLL/SNIPE (4/5) | `dbg_mark_ptr`. POINTER를 누르고 있으면 16/17은 POINTER의 `&none`으로 떨어진다. 아래 주의 참고 |
| EXTRA (6) | `dbg_mark_ptr`. `&none`이다 |

주의: POINTER 없이 SCROLL/SNIPE만 고착되면 R/T가 Base로 떨어진다.
- R/T 입력이 최대 80 ms 늦어진다.
- 빠르게 친 "rt"는 마크가 되고 두 글자가 사라진다.
- 이 일은 그 레이어가 고착된 동안에만 생긴다. 고착 자체가 C4 멈춤이다.

### 8.3 Studio와의 관계

- `dbg_mark` behavior에는 parameter metadata가 없다. 그래서 Studio에서 이 behavior를 키에 바인딩할 수 없다(F12). 실수로 바인딩되거나 롤백 뒤 죽은 키가 될 일이 없다. Studio의 behavior 목록에는 매개변수 없는 behavior "DEBUG mark (do not bind)"로 보인다(소스로 확인, A-37). 골라도 바인딩이 거부되므로 무해하다.
- combo는 레이어 index로 동작한다. 그런데 Studio에서 레이어 순서를 바꾸거나 지우면 index→id 순서만 저장된다(`LAYER_REORDERING=y`). 그러면 combo가 조용히 다른 레이어를 가리킨다(F11).
- 그래서 동글이 부팅 5초 뒤와 이후 60초마다 다음을 device 포인터로 확인한다.
  - index→id 대응이 그대로인지
  - 16/17, 23/35의 바인딩이 기대한 `none`/`transparent`인지
- 어긋나면 다음이 일어난다.
  - STATUS `mark_cfg_ok=0`
  - MARKCFG 기록
  - 트레이 노랑 "마크 콤보 설정 불일치: Studio 레이어 순서/바인딩 확인"
- 디버그 기간에는 Studio에서 레이어 순서를 바꾸거나 레이어를 지우지 않는다. 다른 바인딩 편집은 괜찮지만, 레이어 2·4·5·6의 16/17과 레이어 1의 23/35는 바꾸지 않는다(바꾸면 트레이가 노랑으로 경고한다).
- 마크 combo의 번호(src)는 combo 순서에 달려 있다. `dbg_mark_ptr`와 `dbg_mark_sym`이 `/combos`의 첫 두 자식이어야 하고 키 하나짜리 combo가 없어야 한다. CI가 확인한다(11.3절).

### 8.4 피드백

- **토스트(약 1초 안).** `마크 #12 기록됨 · Pointer 레이어 · 트랙볼 입력 0.84 s 전 중단`
- **보고서.** 약 60초 뒤 `reports\mark-12.md`, `.html`, `.csv`가 생긴다.
- **메모.** 트레이 → "마지막 마크 메모 ▸"에서 한 번 클릭한다. 예: "키도 멈춤", "공을 굴리던 중", "&dpi 누름". 메모는 판정 규칙(C4, C5, C6)에 들어간다. CLI로는 `py -m dbgrec note <n> <tag>`다.
- **마크 취소.** 잘못 친 마크는 `py -m dbgrec unmark <n>`으로 지운다.
- **LED 피드백은 없다.** 확인은 토스트와 트레이로 한다.
- **판정 토스트는 2b부터다.** 판정 규칙을 실제 마크 3건 이상으로 확인한 뒤에 켠다.

## 9. PC 에이전트

Python 3.14 표준 라이브러리만 쓴다. pyserial과 hidapi는 필요 없다.

### 9.1 프로세스

| 프로세스 | 시작 | 하는 일 |
|---|---|---|
| supervisor `dbgrec_supervisor.pyw` | HKCU `…\CurrentVersion\Run` (로그온) | 아래 목록 |
| 에이전트 `pythonw -m dbgrec agent` | supervisor | 수집만 한다. 이름 있는 mutex `Local\dbgrec-agent`로 하나만 실행된다. UI 스레드 타이머가 1초마다 `run\agent.hb`(pid, 생성 시각, 순번)를 쓴다. supervisor heartbeat의 순번이 자기 실행 시간으로 30초 동안 늘지 않으면, 생성 시각을 확인한 핸들로 멈춘 supervisor를 끝내고 다시 띄운다. supervisor mutex가 없을 때도 다시 띄운다 |
| 보고서 하위 프로세스 | 에이전트(마크 60초 뒤), supervisor(30분마다) | 해석, 판정, 보고서 |
| 정리 하위 프로세스 `pythonw -m dbgrec maintain` | supervisor(30분마다, BELOW_NORMAL) | 지난 날 파일 압축, 오래된 항목 정리(9.5절) |
| CLI `py -m dbgrec …` | 사용자 | named pipe `\\.\pipe\dbgrec-<user>`로 에이전트에 요청한다. 파이프가 없으면(FileNotFoundError) 에이전트가 없는 것이고, 그때만 HID_1을 직접 연다. 파이프가 5초 안에 답하지 않으면 에이전트가 멈춘 것으로 알리고 HID_1은 열지 않는다 |

하위 프로세스(보고서, 정리)는 모두 `pythonw.exe`로 띄우거나 `CREATE_NO_WINDOW`로 띄운다. 그래서 콘솔 창이 깜박이지 않는다. 장치 확인은 PowerShell(이 PC에서 호출당 약 1.6초) 대신 cfgmgr32를 ctypes로 부른다(0.05 ms).

supervisor가 하는 일:
- 이름 있는 mutex `Local\dbgrec-supervisor`로 하나만 실행되게 한다. mutex는 프로세스가 끝나면 바로 풀린다. 잠금 파일은 강제 종료 뒤 잠깐 남을 수 있어 쓰지 않는다.
- 에이전트를 띄우기 전에 이미 도는 에이전트가 있으면 그것을 이어받는다. `run\agent.pid`의 PID와 생성 시각이 맞을 때만 이어받는다.
- 에이전트가 죽으면 1/2/5/30 s 간격으로 다시 띄운다. mutex 때문에 바로 끝난 에이전트는 crash로 세지 않는다.
- heartbeat 순번이 supervisor 자신의 실행 시간으로 30초 넘게 멈춘 에이전트만 죽이고 다시 띄운다. 루프 간격이 5초를 넘으면(절전, 최대 절전, 굶주림) 판정을 처음부터 다시 하고 60초 동안 죽이지 않는다. 파일 수정 시각은 쓰지 않는다. 깨어난 직후 멀쩡한 에이전트를 죽이지 않기 위해서다.
- 죽일 때는 띄울 때 받은(또는 이어받을 때 연) 핸들을 쓴다. PID만으로는 죽이지 않는다.
- 복구 감시기를 돌린다.
- 30분마다 `report --auto`와 `maintain`을 BELOW_NORMAL 우선순위로 실행한다.
- 5초마다 `run\supervisor.hb`(순번 포함)를 쓴다.

Task Scheduler는 쓰지 않는다. 시험해 보니 작업이 BELOW_NORMAL 우선순위로 들어가고, 작업 디렉터리가 없으며, 강제 종료는 재시작 대상이 아니었다(F23).

### 9.2 설치

`py -3.14 host\install_dbgrec.py`가 다음을 한다.
1. 패키지를 `%LOCALAPPDATA%\dbgrec\app\dbgrec\`에, `dbgrec_supervisor.pyw`를 `%LOCALAPPDATA%\dbgrec\app\`에 복사한다.
2. user site-packages에 `.pth`를 써서 어느 디렉터리에서든 `py -m dbgrec`이 되게 한다. user site 폴더가 없으면 만든다(이 PC에는 아직 없다).
3. `config.json`을 쓴다. 단축키, 복구 on/off, slot map, 동글 serial(설치 때 HID_0에서 읽는다. 그래서 설치할 때 동글이 꽂혀 있어야 한다)과 나중에 배우는 반 serial이 들어간다.
4. HKCU Run 값 `dbgrec`(REG_SZ, 관리자 권한 불필요)에 환경 변수를 펼친 절대 경로 명령줄을 넣는다. REG_SZ는 `%LOCALAPPDATA%`를 펼치지 않기 때문이다. `…\Explorer\StartupApproved\Run`에 꺼진 항목이 있으면 지운다. 로그온 뒤 탐색기가 기본 지연(약 10초) 뒤에 NORMAL 우선순위로 실행한다. 이 PC에서 Run으로 뜬 프로세스는 job 밖에 있었고 NORMAL이었다.
5. supervisor를 띄우고, 15초 안에 에이전트 heartbeat가 나오는지 기다린 뒤 `doctor` 결과를 출력한다.

`--uninstall`은 모두 되돌린다. 데이터는 `--purge`를 줄 때만 지운다.

### 9.3 장치 찾기와 수집

**HID_1 찾기.** COM 번호나 MI 번호로 찾지 않는다. 순서는 다음과 같다.
1. SetupDi로 HID interface 중 경로에 `vid_1d50&pid_615e`가 있는 것을 고른다(대소문자 무시).
2. `HidP_GetCaps`로 UsagePage 0xFFDB, Usage 1, FeatureReportByteLength 128인지 확인한다.
3. `HidD_GetSerialNumberString`으로 serial을 읽어, 설치 때 기록한 동글 serial과 같은지 확인한다. 다르면 기록만 하고 쓰지 않는다.

**수집.**
- STATUS는 1 Hz로 읽는다. `mark_count`가 바뀐 뒤 5초 동안과 밀린 기록을 따라잡는 동안은 4 Hz로 읽는다.
- CHUNK는 `more`가 꺼질 때까지 읽는다.
- 중복은 (boot_nonce, space, seq)로 제거한다.
- CLI 파이프 서버는 장치 스레드가 아니라 별도 스레드에서 돈다. `accept()`가 시간 제한 없이 막히기 때문이다. 요청은 JSON으로 주고받고(pickle은 쓰지 않는다), HID 작업은 장치 스레드에 넘긴다. 파이프를 이미 다른 에이전트가 열고 있으면 이 에이전트는 끝난다.

**오류 처리.**
- `OSError`가 나면 핸들을 닫고 1/2/5 s 뒤 다시 찾는다.
- 절전에 들어갈 때 닫고, 깨어나면 2초 뒤 연다.
- 새 boot_nonce를 보면 SLOTMAP과 mode를 다시 보낸다.

**Raw Input S6.**
- 숨은 창에 `RIDEV_INPUTSINK | RIDEV_DEVNOTIFY`로 마우스를 등록한다. 장치 이름이 `vid_1d50&pid_615e&mi_02&col03`인 것만 센다.
- 100 ms bin마다 수, Σ|dx|, Σ|dy|, 휠, 최대 공백, loop lag를 남긴다.
- Windows는 백그라운드 Raw Input을 합치거나 초당 약 125개로 제한할 수 있다(이 PC는 10.0.26300). 그래서 개수가 아니라 processor가 없는 레이어의 S4 Σ|d|와 공백으로 비교한다(F20).
- 잠금 화면과 UAC 중에는 Raw Input이 멈춘다. 그 구간은 판정에서 뺀다(F24).
- 관리자 권한 창(작업 관리자 등)이 앞에 있을 때도 멈출 수 있다. 아직 확인하지 못했다(A-56). 1 Hz로 앞 창의 권한 수준을 기록하고, 멈춘다면 그 구간도 뺀다. 1a 판정(S6 공백 → 장치나 USB)과 1a 기준선의 공백 수에도 잠금 해제, input desktop Default, 관리자 창 아님, loop lag 깨끗을 똑같이 조건으로 건다. 조건이 맞지 않으면 '판정 불가'로 적는다.

**그 밖의 수집.**
- `WM_POWERBROADCAST`: 절전과 재개
- `WTSRegisterSessionNotification`: 잠금. 변화만 알려 주므로 시작할 때와 깨어날 때 `WTSQuerySessionInformationW`로 현재 잠금 상태를 읽는다. 등록이 RPC_S_INVALID_BINDING으로 실패하면 다시 시도한다.
- 1 Hz input desktop 확인(`OpenInputDesktop` 뒤 매번 `CloseDesktop`)
- 1 Hz 앞 창 권한 확인(입력 hook이 아니다)
- `TaskbarCreated`: 탐색기 재시작 뒤 트레이 재등록
- `RegisterHotKey`: 단축키

입력 hook은 쓰지 않는다. 이 노트북은 하이브리드 CPU라 NORMAL 우선순위와 HighQoS(전력 throttling 해제)로 돌린다. HighQoS로도 배터리일 때의 최대 프로세서 상태 30%(이 PC의 균형 조정 구성표) 제한은 풀리지 않는다. 작업 관리자의 효율 모드가 이 설정을 덮어쓸 수 있다. 그래서 에이전트가 60초마다 우선순위와 QoS를 확인해 다시 설정하고, 바뀌면 기록한다.

### 9.4 복구 감시기와 flash 도구

**`py -m dbgrec flash <zip> <dongle|right|left> [--target <name>] [--rescue]`**
1. MANIFEST를 확인한다.
2. 해당 보드의 UF2를 `staged\<board>.uf2`로 꺼낸다. 그 보드의 디버그 타깃이 zip에 둘 이상이면(예: `dongle_dbg`, `dongle_dbg2`) `--target`이 필요하고, 없으면 거부한다. `--rescue`는 디버그 이미지 대신 프로덕션 복구 이미지를 stage한다.
3. ELF(`zmk.elf`), map(`zmk.map`), `symbols.json`, `.config`, DTS(`zephyr.dts`)를 `fw\<build_id>-r<run>\<target>\`에 보관한다. run은 CI 실행 번호이고 펌웨어 STATUS에도 들어간다. 같은 커밋을 다시 빌드하면 Zephyr나 컨테이너가 달라질 수 있어서 build_id만으로는 ELF를 구분할 수 없기 때문이다. 같은 키에 다른 ELF가 오면 보관을 거부한다. 같은 CI 실행의 복구 이미지는 `rescue\<sha8>\`에 보관한다.
4. `flashlog.jsonl`에 기록하고 한국어 안내를 출력한다. 안내에는 30분 안에 그 보드의 리셋을 두 번 누르라는 말이 들어간다. 30분이 지난 stage 파일은 감시기가 쓰지 않는다.

복구 이미지가 없는 zip은 거부한다.

**`py -m dbgrec rescue import <zip>`.** MANIFEST를 확인하고, 복구 이미지를 `rescue\<sha8>\`에, ELF와 심볼을 `fw\<build_id>-r<run>\<target>\`에 보관한 뒤 `flashlog.jsonl`에 `imported` 항목을 남긴다. 아무것도 stage하지 않는다. 1a는 이 명령으로 시작하고, '최신 flashlog 커밋'에는 이 항목도 들어간다.

**보드 식별.** 세 보드는 같은 nice!nano 부트로더를 쓴다. 그래서 드라이브 이름, `INFO_UF2.TXT`(Board-ID `nRF52840-nicenano`), 볼륨 일련번호로는 보드를 구분할 수 없다. 반도 케이블을 꽂으면 동글과 같은 `1D50:615E`로 잡힌다(이 PC의 장치 기록에서 확인). 대신 USB serial은 칩 고유값(FICR DEVICEID)이고, 부트로더와 ZMK가 같은 문자열을 낸다. 이 PC에서 동글은 두 모드 모두 `71FB7A39AFC7297C`였다(F29). 설치 때 동글 serial을 기록한다. 반의 serial은 그 반만 케이블로 연결해 켠 채 `py -m dbgrec learn right|left`로 한 번 배운다.

**복구 감시기(1초마다).** nice!nano 부트로더 드라이브가 새로 나타나면 cfgmgr32로 지금 연결된 부트로더 장치(`USB\VID_239A&PID_00B3\<serial>`)를 읽는다. 드라이브와 부트로더 장치가 각각 정확히 하나일 때만 다음을 한다.
- **serial이 동글 것일 때.** 30분 안에 stage한 동글 이미지가 있으면 그것을 굽는다. 없으면 복구가 켜진 상태일 때만 최신 flashlog 커밋의 복구 이미지를 굽는다. 마지막으로 구운 동글 펌웨어가 stage한 디버그 빌드이고 그 뒤 복구나 프로덕션을 굽지 않았거나, 10분 안에 `py -m dbgrec rescue drill`을 실행했으면 복구가 켜진 상태다. 꺼져 있으면 손으로 굽는 중으로 보고 토스트만 띄운다.
- **serial이 배운 오른쪽이나 왼쪽 것일 때.** 그 반의 이미지가 stage되어 있을 때만 굽는다.
- **모르는 serial일 때.** 굽지 않는다. 반 이미지가 하나만 stage되어 있으면 트레이나 `py -m dbgrec rescue confirm right`로 묻고, 확인되면 serial을 배운다.
- 동글이 있는지는 VID/PID가 아니라 동글 serial 장치(`USB\VID_1D50&PID_615E\<동글 serial>`)로 판단한다.
- 부트로더 드라이브나 장치가 둘 이상이면 아무것도 하지 않고 토스트를 띄운다.
- 복사 전에 5초 기다린다. 손으로 구울 때는 트레이 "복구 일시중지 10분"이나 `py -m dbgrec rescue pause`로 취소한다.
- 구운 stage 파일은 `flashed\`로 옮긴다. 그래서 그다음에 리셋을 두 번 누르면 복구 이미지가 구워진다.
- 복사가 성공했는지는 20초 안에 그 serial의 일반 장치(`USB\VID_1D50&PID_615E\<serial>`)가 다시 잡히는지로 판단한다. 닫을 때 난 OSError만으로는 실패로 보지 않는다.

**공통.**
- settings_reset은 쓰지 않는다. 페어링과 Studio 편집이 유지된다.
- 오른쪽 복구: 트레이 "오른쪽 복구 이미지 준비" 또는 `py -m dbgrec flash <zip> right --rescue`를 실행한다. 그다음 케이블을 꽂고 리셋을 두 번 누른다. 오른쪽 serial을 아직 배우지 않았으면 감시기가 먼저 확인을 묻는다.

### 9.5 저장과 디스크 예산

**위치.** `%LOCALAPPDATA%\dbgrec\`이다(OneDrive 밖).
- 데이터: `data\YYYY\MM\DD.dbr`(+`.zst`)
- 폴더: `reports\`, `fw\`, `rescue\`, `staged\`, `flashed\`, `run\`, `log\`
- 파일: `flashlog.jsonl`, `marks.jsonl`, `notes.jsonl`, `boots.jsonl`

**블록 형식.**
- 32 B 머리(CRC 포함) 뒤에 frame들이 온다.
- 10초 또는 64 KB마다 fsync한다. 시작할 때 끝이 잘린 마지막 블록을 잘라 낸다.
- 원본 frame을 그대로 두므로, 해석기를 고치면 과거 데이터도 다시 분석된다.

**STATUS 저장.** uptime/cycle과 세 공간의 head/oldest/read seq 외의 값이 바뀌었을 때, 또는 최근 10초 안에서 RTT가 가장 작은 표본일 때만 저장한다. seq 진행은 CHUNK의 first_seq, 레코드 수, lost_before로 복원한다.

**압축.** 에이전트 안에서는 하지 않는다. supervisor가 30분마다 띄우는 정리 하위 프로세스(BELOW_NORMAL)가 아직 압축되지 않은 지난 날 파일을 압축한다.
- 전원이 연결되어 있으면 레벨 19, 배터리면 레벨 9로 압축한다.
- 이 PC에서 30 MB를 레벨 19로 압축하는 데 CPU 9.5초와 메모리 약 100 MB가 들었다. 레벨 9는 0.4초였고 파일이 15% 컸다. 배터리일 때는 최대 프로세서 상태가 30%로 묶여 있어 더 오래 걸린다.
- `.zst`를 풀어 확인한 뒤에만 `.dbr`을 지운다. 보고서가 파일을 열고 있으면 나중에 다시 시도한다.
- 절전 중에 끝난 날도 다음 실행에서 압축한다.

**예산 [추정].**
- 활동 1초에 CHUNK 약 131 B와 RAWBIN 약 149 B가 쌓이고, STATUS는 10초에 한 번(약 14 B/s) 저장된다. 그래서 활동 1시간에 압축 전 약 1.06 MB다. STATUS 저장 규칙에서 seq를 빼지 않으면 활동 중 STATUS가 매초 저장되어 시간당 약 1.5 MB가 된다. 쉬는 동안은 초당 약 13 B다.
- 하루 활동 8시간이면 압축 뒤 **하루 약 2~4 MB**, 최악 약 8 MB다.
- 상한은 데이터 365일이고, 4 GB는 안전장치다. 오래된 날부터 지운다. 자동 후보 보고서(마크 보고서 제외)는 90일이 지나면 지우고, fw 보관본은 최신 5개와 마크가 참조하는 것만 남긴다. 마크 보고서, rescue, flashlog, 메모는 지우지 않는다. `doctor`가 각 크기를 보여 준다.
- 1a/1b에서 일주일 실측한 값으로 바꾼다(A-26).
- 이 노트북은 며칠씩 켜져 있고, 배터리일 때는 3시간 뒤 최대 절전에 들어가면서 USB 전원이 끊긴다(F22). 그래서 예산은 하루 24시간 깨어 있는 날을 기준으로 잡았다.

### 9.6 트레이, doctor, bundle

트레이 아이콘 색의 뜻과 할 일:

| 색 | 조건 | 할 일 |
|---|---|---|
| 녹색 | HID_1을 5초 안에 읽었고, Raw Input 장치가 있고, 확인하지 않은 빨강 조건이 없다. 2단계에서는 연결 중 2분 안에 오른쪽 SUM_R나 HB_R가 왔다 | 없음 |
| 노랑 | 다음 중 하나: Raw Input은 보이는데 HID_1이 없음("기록 펌웨어 없음": 습관대로 프로덕션을 구운 경우), 동글 없음, 오른쪽 반이 연결되어 있는데 diag가 10분 넘게 `live`가 아님(2단계), `mark_cfg_ok=0`, 보관된 최신 빌드보다 오래된 빌드, 디스크 상한 80% 초과, 오른쪽 배터리 20% 미만(2단계) | 툴팁 문구를 보고 1.6절 '문제가 생기면'을 따른다 |
| 빨강 | 다음 중 하나: 기준 이상의 유실, 새 crash, 안전 수준 SAFE/INERT(동글, 또는 오른쪽 BOOT_R의 level), 에이전트 오류 수 증가, 디스크 상한 도달 | `py -m dbgrec bundle --since 1d`로 묶어 전달한다. 확인한 빨강을 지우는 방법(트레이 메뉴 열기 등)은 구현할 때 정해 여기와 명세 §11.6에 적는다 |

툴팁 예: `마지막 데이터 1 s 전 · 동글 abc1234 · 3h12m · 오늘 마크 2`. 로그온 때 한 번 `기록 중 · 동글 abc1234` 토스트를 띄운다.

토스트는 뜨지 않을 수도 있다.
- 방해 금지 모드에서는 알림 센터로 간다.
- 새 트레이 아이콘은 overflow 영역에서 시작하므로 고정해 둔다.
- 토스트가 없다고 에이전트가 죽은 것은 아니다. `doctor`와 heartbeat로 판단한다.

**`doctor`가 확인하는 것.**
- 두 heartbeat, Run 값(예상 명령줄과 같은지, 설정 > 앱 > 시작 프로그램이나 작업 관리자에서 꺼지지 않았는지), pythonw.exe 경로
- HID_1과 그 serial, 그리고 build_id·run 대 flashlog
- Raw Input 장치, 복구 이미지, 단축키, 트레이
- 에이전트의 우선순위와 QoS, 전원별 최대 프로세서 상태
- 마지막 데이터 시각, 오류 수, 디스크(지우지 않는 항목별 크기 포함)

**`bundle --mark N | --since 3d`.** 다음을 zip 하나로 묶는다. serial과 nonce는 가린다.
- 해당 구간의 원본 frame, 해석한 CSV, report.md
- flashlog, build_id별 `symbols.json`, 에이전트 로그
- Windows 빌드와 허브 정보

바이너리 없이도 AI 세션이 이어서 분석할 수 있게 만든다.

### 9.7 보고서

**이상 구간 찾기.** 마크 구간 [마크 −30 s, +2 s]에서 다음 중 하나를 찾는다.
- 움직임 뒤에 온 150 ms 이상의 S6/S4 공백
- 레이어로 빠진 구간
- 메모 "키도 멈춤"

없으면 "쉬다가 첫 움직임" 또는 "파이프라인 이상 없음"으로 적는다.

**처음 어긋나는 지점.** 자기 수치가 구간 직전 기준의 10% 미만으로 떨어졌는데 바로 앞 지점은 50% 이상을 유지하는 지점 중 가장 이른 것이다.

**원인별 판정.** 원인마다 CONFIRMED / LIKELY / POSSIBLE / RULED OUT / NO DATA 중 하나와 숫자 근거 줄을 붙인다.

**마크 보고서의 내용.**
- 판정 상자
- [−10 s, +5 s]의 100 ms 지점별 표(S0~S6)와 문맥 lane
- 메모, 전원·잠금 상태
- 펌웨어와 관찰자 변경
- 데이터 품질

**`index.md/.html`.**
- 마크와 자동 후보 표, 날짜별 수
- 활동 시간당 마크 수 대 1a 기준선(펌웨어별, mode별)
- 건강 지표: 에이전트 가동률, HID_1 연결률, 유실, 원인별 부팅, 스택 최솟값, 오른쪽 배터리

**자동 후보(마크 없이 찾는 것).** 하루 20건까지 만든다. 마크는 제한이 없다.
- 움직이는 중의 300 ms 이상 공백이 10초 안에 jump와 함께 재개된 경우
- R4 조건의 300 ms 이상 공백
- KEYX
- BOOT/crash
- 사용자·로컬 원인이 아닌 LINK 끊김

### 9.8 CLI

```text
py -m dbgrec status | doctor | mark ["memo"] | note <n> <tag> | unmark <n>
py -m dbgrec report [--mark N | --since 7d | --auto] | bundle (--mark N | --since 3d) | maintain
py -m dbgrec flash <zip> <dongle|right|left> [--target <name>] [--rescue]
py -m dbgrec rescue (import <zip> | drill | confirm <right|left> | pause | resume | status)
py -m dbgrec learn <right|left>
py -m dbgrec ctl mode <off|normal> [--board right] | diag hello
py -m dbgrec selftest <dongle|right> <kind> --i-know
```

- `rescue import`는 bundle의 복구 이미지를 stage 없이 보관한다. `rescue drill`은 동글 복구를 10분 동안 켠다. `rescue confirm`은 모르는 serial에 대한 감시기의 질문에 답한다.
- `learn`은 그 반만 케이블로 연결해 켠 채 반의 USB serial을 기록한다.
- `diag hello`는 2단계 시험용이다. CTRL RIGHT_CMD로 CMD HELLO를 보낸다.
- `selftest`에는 `--i-know`가 필요하다.

## 10. 원인별 판정표

### 10.1 이전 가설과의 대응

| 이전 | 내용 | 새 항목 |
|---|---|---|
| H1 | 센서 rest 지연 | C5a, C5b |
| H2 | 오른쪽 송신 정체 | C1, C2(4초 미만) |
| H3 | 링크 끊김 | C2(4초 이상), C9 |
| H4 | 무선 구간 지연 | C2, C7 |
| H5 | 동글 내부/USB | C3, C4, C8 |
| H6 | 로그의 왜곡 | R0, `mode off`, 기준선 |
| 없음 | — | C6 CPI 경합, C10 스택 넘침, C11 재연결 CCC 저장 |

### 10.2 1a 판정 규칙 (S6만 본다)

| 발견 | 판정 |
|---|---|
| 마크 구간 내내 S6가 끊기지 않음 | "포인터 입력은 PC에 도착함(인지/앱)" |
| 세션 잠금 해제, input desktop Default, 앞 창이 관리자 권한 창이 아님, loop lag 깨끗인 동안의 S6 공백 | "장치 또는 USB" |
| 위 호스트 조건 중 하나라도 맞지 않는 동안의 S6 공백 | "판정 불가(호스트가 보지 못함)" |
| x/y 대신 휠 | "레이어로 빠짐(C4)" |

모든 결과에 메모와 전원·잠금 상태를 붙인다.

### 10.3 1b 판정 규칙 (위에서부터 처음 맞는 것)

| 규칙 | 조건 | 판정 |
|---|---|---|
| R0 품질 | 유실·overrun·`bins_lost`가 구간을 덮음, 에이전트가 구간을 다 덮지 못함, 시계 잔차 >20 ms, mode off, 안전 수준 ≠ NORMAL | "판정 불가 (H6)"와 이유 |
| R1 동글 리셋 | [시작 −2 s, 끝] 안의 새 boot_nonce | C9/C10 동글. crash slot을 해석해 붙인다. 최대 절전 재개 직후의 POR은 정상이다 |
| R2 링크 | 한 반의 LINK 끊김·재연결이 [시작 −5 s, 끝] 안 | "4초 이상 링크 끊김 **또는** 오른쪽 리셋(2단계에서 구분)" |
| R3 레이어 | S4가 흐르는데 L1/L4/L5가 구간 내내 켜짐, 또는 S4는 x/y인데 S6가 휠 | C4. 앞이나 구간 안에 KEYX lost release가 있으면 "release 유실(C3 키 유실)", 없으면 "키를 누르고 있었거나 불명" |
| R4 호스트/USB | S5 리포트는 흐르는데 S6가 150 ms 이상 조용함. 그리고 USB endpoint, USB configured, 세션 잠금 해제, input desktop Default, 앞 창이 관리자 권한 창이 아님(1a 3번 확인에서 필요 없다고 나오기 전까지), loop lag 깨끗(heartbeat 공백 <150 ms, WM_INPUT lag <50 ms) | C8-host |
| R5 동글 내부 | S4 공백이 sysq 지연 ≥40 ms, pevq 최고 수위 5, inq 최고 수위 ≥14(16이면 가득 참), ISR 공백 ≥20 ms 중 하나와 겹침, 또는 구간 안에 KEYX가 있음, 또는 같은 bin이나 직전 bin에 pevq 5나 입력 큐 16(가득 참)이 함께 있는 orphan. 동글 큐가 차지 않았는데 생긴 orphan은 오른쪽 입력 큐나 notify에서 Y를 잃은 것이므로 '상류 유실'로 적고 C3로 판정하지 않는다 | C3 또는 동글 정체. 해당 lane을 근거로 적는다 |
| R6 상류 무음 | 움직이는 중 S4 공백 ≥150 ms이고 동글 lane이 모두 깨끗 | "상류: 오른쪽 반 또는 링크" |
| R7 이상 없음 | S4와 S6가 끊기지 않음 | "파이프라인은 움직임을 전달함(인지/앱)" |

R2 보충: 끊김 이유가 0x08(시간 초과)이면 마지막 도착 약 4초 뒤에 끊긴다.

R4 보충: 다음 경우는 C8-device로 판정한다.
- USB가 suspended이거나 미구성 상태다.
- 공백을 덮는 `lst_max`가 30 ms 이상이다(HID 전송 timeout).

R6에는 다음 주석을 붙인다.
- 시작 직전 2초의 오른손 키: C1 개연성
- 공백 중 오른쪽 키 도착: 오른쪽 링크가 살아 있다. RF가 아니라 오른쪽 입력 경로나 센서 쪽이다.
- 공백 중 왼쪽 키 도착: 동글 radio가 살아 있다.
- 프로필 open·미연결(광고 중), 연결된 반 2개 미만(스캔 중): C7 문맥
- 오른쪽 배터리

PC 전원 사건은 `WM_POWERBROADCAST`가 기본이다. 에이전트가 없던 구간은 System 로그의 Power-Troubleshooter Id 1로 채운다. Kernel-Power 107의 TimeCreated는 깨어난 시각으로 쓰지 않는다.

### 10.4 원인별 특징과 배제 조건

| 원인 (이전 H) | 특징 | 배제 조건 | 필요한 단계 |
|---|---|---|---|
| C1 B2 루프 (H2) | 1b: R6이고 직전 2초에 오른손 키. 2: posq 최고 수위 10, 약 100 ms 단위 sysworkq 지연, MOTION 핀 고착, att=0에서 notify 막힘, 재개 때 jump | 직전 오른손 키 없음, 오른쪽 sysworkq 건강, posq 여유 | 1b 힌트, 2 유력, 3a 결정(posq put −EAGAIN), 4 `_fix3110` A/B |
| C2 RF 4초 미만 (H2/H4) | 2: sysworkq와 posq는 건강한데 notify 막힘(att=0), 오른쪽 키도 조용, 왼쪽은 살아 있음 | 공백 중 오른쪽 키 도착, notify 막힘 없음 | 2, 2b RSSI 보조 |
| C2 RF 4초 이상 (H3) | LINK 끊김 0x08과 재연결, 오른쪽 BOOT 없음 | 구간에 LINK 끊김 없음 | 1b(오른쪽 리셋과의 구분은 2) |
| C3 동글 유실 (H5) | 1b: S4 공백 중 pevq 5 / inq ≥14 / sysworkq 지연, 동글 큐가 찬 때의 orphan-X, KEYX. 2b: 정확한 S3−S4, `pevq_pred_loss` | 동글 lane이 모두 깨끗함, (2b) S3−S4 = 0 | 1b 유력, 2b 확정, 3a 결정 |
| C4 레이어 고착 (H5) | L1/L4/L5가 구간 내내 켜짐, S6 휠. 원인은 KEYX lost release(1b) 또는 D-STUCKLAYER(2b) | 구간 동안 레이어 비트 꺼짐, S6가 x/y | 1b |
| C5a REST 깨어남 (H1) | 쉬다가 첫 움직임에서 공백, 처음 100 ms의 ISR이 적음 | 공백 직전에 움직임이 있었음 | 2, 4 fast-rest A/B |
| C5b 센서 무응답 (H1) | 메모 "공을 굴리던 중"인데 isr_n=0, 핀 비활성, 하류 건강 | 공백 중 ISR 있음 | 2, 3b 결정 |
| C6 CPI SPI 경합 | 메모 "&dpi" 또는 2b CPI_STEP가 시작 1초 이내, 이어서 Σ\|d\|≈0인 ISR 폭주 | 시작 앞뒤에 `&dpi` 없음 | 2b, 3b 결정 |
| C7 radio 경합 / LL 수정 누락 (H4) | 프로필 open·미연결(광고)이나 연결된 반 2개 미만(스캔)일 때 빈도가 높음, 두 링크가 함께 멈춤, LL assert 파일이 lll*/ull* | 빈도가 광고·스캔 상태와 무관, 공백 중 왼쪽 키 도착 | 1b 문맥, 3a/4 결정 |
| C8 USB/호스트 (H5) | R4 | S6가 끊기지 않음, 또는 S5도 멈춤 | 1a/1b |
| C9 리셋/fault/assert (H3) | 새 nonce, RESETREAS 원값(SREQ+crash slot, LOCKUP, DOG, PIN, 0이면 POR/BOR), slot 해석 | 구간에 새 nonce 없음 | 1b 동글, 2 오른쪽 |
| C10 스택 넘침 | watermark가 0을 향해 줄어듦, 스택 한계 근처 thread에서 crash | 스택 여유가 256 B 이상으로 유지됨 | 1b/2, 3 MPU 변형 결정 |
| C11 재연결 CCC 저장 | 오른쪽 HELLO/security 0.5~2초 뒤 시작, 오른쪽 CPU 공백 약 7 ms(flash page 지우기가 끼면 약 85~90 ms) | 직전에 재연결 없음 | 2, 3a 결정 |
| H6 데이터 유실 / 관찰자 | R0, 기준선 대비 `mode off` A/B | 유실 0, mode off 날과 비율이 같음 | 모든 단계 |

2단계에서 링크 쪽 지표(att, hand-off 지연)가 첫 번째 90 ms 이상 sysworkq 지연보다 **먼저** 나빠졌다면 "링크가 시작했고 C1이 키웠다"로 적는다.

## 11. 빌드와 CI

### 11.1 무엇이 그대로인가

- `config/`, `build.yaml`, `.github/workflows/build.yml`은 바뀌지 않는다(선택 사항인 `paths-ignore` 하나만 예외).
- 프로덕션 reusable workflow는 `zephyr/module.yml`이 저장소 루트에 있을 때만 모듈을 더한다. 기록기는 `dbgrec/zephyr/module.yml`에 두므로 프로덕션 빌드에 들어가지 않는다. `dbgrec.yml`은 저장소 루트에 `zephyr/module.yml`이 생기면 실패한다.
- 프로덕션 workflow의 `paths-ignore`에는 `README.md`와 `docs/**`만 있다. 그래서 `dbgrec/**`나 `host/**`만 바꾼 push에도 프로덕션 빌드가 돈다. 결과 펌웨어는 같고 Actions 시간만 든다. 기본은 `build.yml`을 그대로 두는 것이다. 저장소가 비공개이고 Actions 시간이 모자라면(Q12) `push`와 `pull_request` 양쪽의 `paths-ignore`에 `dbgrec/**`, `host/**`, `.github/workflows/dbgrec.yml`을 더한다. 프로덕션 workflow에 허용하는 변경은 이것 하나뿐이다.
- 브랜치는 `my-keymap` 하나다. 디버그와 프로덕션은 workflow, 모듈 위치, snippet으로 나뉜다. `_dbg` 아티팩트 이름은 유지한다.

### 11.2 저장소 배치

```text
dbgrec/zephyr/module.yml        module (not at the repo root)
dbgrec/{CMakeLists.txt,Kconfig} include/dbgrec/{rec.h,proto.h}
dbgrec/src/                     core, crash, stacks, hooks_input, keys, conn, zmk_state, markcfg,
                                usb_hid1, behavior_dbg_mark (dongle), client (dongle, 2),
                                svc_right, sensor_right (right, 2), wrap/ (3a)
dbgrec/snippets/                dbgrec-common, dbgrec-dongle, dbgrec-right
dbgrec/patches/                 stage 3b/4 only
dbgrec/ci/                      gates_single.py, gates_compare.py, keymap_check.py, protected.txt
dbgrec/build-dbg.yaml
.github/workflows/dbgrec.yml
host/dbgrec/                    supervisor, agent, decoder, rules, reports, rescue, tests
host/install_dbgrec.py, host/README.ko.md
```

`dbgrec-common` snippet을 따로 둔 이유: `snippet.yml` 하나는 conf 하나와 overlay 하나만 덧붙일 수 있기 때문이다(F14).

### 11.3 `.github/workflows/dbgrec.yml`

실행 조건:
- `my-keymap`에 push되었고, 바뀐 경로가 `config/**`, `build.yaml`, `dbgrec/**`, `host/**`, workflow 파일 중 하나일 때.
- `workflow_dispatch`로 손으로 돌릴 때.

keymap을 수정해도 디버그 이미지와 복구 이미지가 같은 커밋으로 다시 빌드된다. 같은 브랜치에서 새 push가 오면 진행 중인 실행을 취소한다(`concurrency`). west 모듈은 프로덕션처럼 `actions/cache`로 재사용한다.

| job | 하는 일 |
|---|---|
| `host_tests` | Windows runner, `actions/setup-python` 3.14. 단위 테스트(FakeHid, 해석기, 원인별 합성 스트림, 시계 맞춤, 끝이 잘린 블록, lag 랩, 복구 결정표). 명령은 `python -m unittest discover -s host/dbgrec/tests -t host`다. 호스트 코드는 3.14 전용(`compression.zstd`)이고 Windows ctypes를 쓰므로 runner나 컨테이너의 Python 3.12로는 돌지 않는다. `-t host`가 없으면 `dbgrec`라는 이름이 루트의 펌웨어 폴더 `dbgrec/`로 잡힌다 |
| `prep` | `keymap_check.py`, `rec.h`와 `schema.py` 상수 비교, 컨테이너 digest 고정, matrix 생성(YAML은 `yq`로 JSON으로 바꾼다) |
| `build` | `host_tests`와 `prep`이 통과해야 돈다. digest로 고정한 컨테이너, `bash -eo pipefail`. `west init/update`, `west-list.txt`, (3b/4) 패치 적용, `west build`, `gates_single.py`(컨테이너의 Python 3.12와 그 안에 이미 있는 pyelftools·PyYAML만 쓴다. pip 설치는 하지 않는다), 업로드 |
| `gates` | build matrix가 모두 끝난 뒤 돈다. 항목별 artifact(`t-<이름>`, 이름은 실행 안에서 겹치면 안 된다)를 항목별 폴더로 받는다. 모든 `west-list.txt`가 같은지 확인하고, Zephyr SHA가 10ba6d0이 아니면 경고한다. `gates_compare.py`: 보호 대상 설정을 같은 CI 실행의 복구 빌드와 비교한다. 변형이 일부러 바꾸는 값(예: `_wq4096`의 sysworkq 스택, `_q16`의 큐, RSSI 변형, MPU 변형)은 `build-dbg.yaml`의 `allow:`에 적힌 것만 허용하고 summary와 MANIFEST에 적는다. RAM/flash 차이를 step summary에 적는다 |
| `bundle` | `gates`가 통과해야만 돈다(`needs: [prep, gates]`). 사용자가 받는 zip 하나 `dbgrec-<sha8>`. zip 파일을 올리지 않고 폴더를 올린다(GitHub가 zip으로 내려 준다) |

`keymap_check.py`가 확인하는 것:
- 입력은 `config/charybdis.keymap`, `charybdis_layout.dtsi`, `charybdis_right.overlay` 세 파일이다. 전처리기는 쓰지 않는다(prep에는 ZMK 소스가 없다). 주석을 먼저 지운다. keymap에는 주석 처리된 `utility_layer`가 통째로 있어서, 지우지 않으면 레이어 번호가 밀린다. 바인딩은 `&` 단위로 나눈다. 반 구분은 `RC(r,c)`의 열이 오른쪽 overlay의 `col-offset`(6) 이상이면 오른쪽이다.
- 레이어 순서가 Base…Extra = 0…6이다.
- 16/17이 레이어 2와 6에서 `&none`, 4와 5에서 `&trans`다.
- 23/35가 레이어 1에서 `&none`이다.
- 행렬 변환의 반 구분이 기록기의 마스크와 같다.
- combos 노드가 `/combos` 하나뿐이다.

이 검사가 실패하면 workflow가 멈춘다. 새는 마크 조합은 빌드되지 않는다. 같은 검사를 동글 빌드의 `zephyr.dts`(매크로가 모두 풀린 최종 결과)에서 `gates_single.py`가 한 번 더 한다.

`gates_single.py`가 확인하는 것:
- `.config`의 필수·금지·수치 값. 복구 항목에는 `CONFIG_DBGREC`가 없어야 한다.
- DTS 파티션: 모든 항목 `storage_partition` 0xEC000/0x8000. 디버그 항목 `code_partition` 0x26000/0xC3000, `dbgrec_partition` 0xE9000/0x3000. 복구 항목 `code_partition` 0x26000/0xC6000, `dbgrec_partition` 없음.
- DTS 노드: 동글 항목은 `zephyr,cdc-acm-uart` 정확히 하나. (동글 디버그 항목만) `zmk,combos` 정확히 하나. 그 첫 두 자식이 `dbg_mark_ptr`, `dbg_mark_sym`이고 키 하나짜리 combo가 없다. 마크의 src 번호가 combo 순서에 달려 있기 때문이다.
- 소스 grep: `behavior_dbg_mark.c`에 parameter metadata가 없다. 잠그는 `k_thread_foreach(`가 없다.
- ELF:
  - 입력 파일은 `build/zephyr/zmk.elf`와 `zmk.map`이다. ZMK가 `CONFIG_KERNEL_BIN_NAME="zmk"`로 정하므로 `zephyr.elf`는 없다. `zephyr_pre0.elf`는 중간 링크 단계라 심볼에 쓰면 안 된다.
  - `symbols.json`을 만든다(pyelftools, Thumb 비트 제거).
  - RAM 여유가 동글 40 KB 이상, 오른쪽 60 KB 이상이다.
  - 오른쪽 `zzz_dbgrec_svc`가 `split_svc`와 `bas` 뒤에 놓인다.
- `.event_subscription`(`zmk.map`)에서 기록기의 `zmk_position_state_changed` 구독이 `combo.c.obj`와 `keymap.c.obj`보다 뒤에 있어야 한다. 모듈 라이브러리는 `app` 뒤에 링크되므로 원래 그렇게 된다. 앞에 오면 combo가 다시 올린 이벤트를 두 번 보게 되어 KEYX 오탐이 생기므로 빌드를 실패시킨다.

금지 Kconfig:
- `LOG`(1~2단계), `LOG_MODE_IMMEDIATE`, 모든 LOG backend
- `SHELL`, `ASSERT`, `SYMTAB`
- `HW_STACK_PROTECTION`(3단계 변형만 예외)
- `ZMK_USB_LOGGING`, `INPUT_EVENT_DUMP`
- `ENABLE_HID_INT_OUT_EP`, `USB_HID_BOOT_PROTOCOL`, `ZMK_USB_BOOT`
- `USB_DEVICE_SOF`, `USB_DEVICE_INITIALIZE_AT_BOOT`
- `BT_CTLR_CONN_RSSI`(RSSI 변형만 예외)

빌드 항목(`dbgrec/build-dbg.yaml`). 파일 맨 위의 `stage:` 값 이하인 디버그 항목만 matrix에 넣는다(1a에서는 복구 항목만 빌드된다). 디버그 항목은 같은 `build.yaml` 항목에서 board·shield·snippet·cmake-args를 가져오고 dbgrec snippet과 인자만 더한다.

| 항목 | 단계 | 차이 |
|---|---|---|
| `dongle_dbg` | 1b | 동글 + `studio-rpc-usb-uart dbgrec-common dbgrec-dongle` |
| `right_dbg` | 2 | 오른쪽 + `dbgrec-common dbgrec-right` |
| `dongle_dbg2` | 2 | `dongle_dbg` + `CONFIG_DBGREC_CLIENT=y` |
| `dongle_dbg2b`, `dongle_dbg_rssi` | 2b | shadow·CPI_STEP·ACL credit(실패하면 ACL credit 없이 다시 빌드), RSSI(`allow: BT_CTLR_CONN_RSSI`) |
| `*_mpu`, `*_wrap`, `right_sensor` | 3, 3a, 3b | MPU 스택 가드(`allow`), `--wrap`, PMW3610 진단 패치 |
| `right_fix3110`, `dongle_q16`, `*_wq4096`, `*_llfix`, `*_llstats` | 4 | 수정 후보(5.4절). `_q16`, `_wq4096`은 바꾸는 값을 `allow:`에 적는다. Zephyr는 얕은 clone(브랜치 머리)이라 `_llfix` 커밋은 `--depth=2`로 먼저 받아 온 뒤 cherry-pick한다. `west-list.txt`의 Zephyr SHA가 시험한 것과 다르면 실패한다 |
| 복구 `dongle`, `left`, `right` | 항상 | `build.yaml`에서 artifact-name이 charybdis_dongle/left/right인 항목만 쓴다(settings_reset 제외, 하나라도 없으면 실패). board, shield, snippet, cmake-args를 그대로 쓰고 모듈과 dbgrec 인자는 넣지 않는다. 저장소 루트에 `zephyr/module.yml`이 있으면 실패한다. 인자는 프로덕션 workflow와 같지만 빌드 폴더, 컨테이너 digest, west 받기가 따로라서 그 artifact와 바이트까지 같다고 보장하지는 않는다 |

빌드에는 `CONFIG_DBGREC_BUILD_ID`(커밋 앞 8자리)와 `CONFIG_DBGREC_BUILD_RUN`(CI 실행 번호×100+재시도 번호)이 들어간다.

bundle zip의 내용:
- 이 `stage`에서 빌드한 모든 디버그 타깃
- `rescue/{dongle,left,right}.uf2`
- 타깃별 ELF(`zmk.elf`), map(`zmk.map`), `symbols.json`
- `west-list.txt`(모든 항목에서 같음을 확인한 것), `build-id.txt`(build_id와 run), `container-digest.txt`, `MANIFEST.json`(타깃 목록, UF2와 `zmk.elf`의 SHA-256, 허용한 차이)

보존 기간은 90일이다. `flash` 도구가 ELF와 심볼을 로컬에 보관하므로 release job은 두지 않는다.

### 11.4 롤백

- **동글.** 리셋을 두 번 누르면 감시기가, stage했던 디버그 이미지와 같은 CI 실행에서 빌드한 프로덕션 설정 이미지를 굽는다.
- **오른쪽.** 복구 이미지를 stage하고, 케이블을 꽂고, 리셋을 두 번 누른다.
- settings_reset은 필요 없다. 페어링과 Studio 편집이 유지된다.
- 롤백 뒤 오른쪽의 첫 프로덕션 부팅에서 `bt/hash` 쓰기가 한 번 일어난다. 남은 항목은 무시된다(6.4절).
- 디버그 작업을 저장소에서 통째로 걷어내려면 `dbgrec/`, `host/`, `.github/workflows/dbgrec.yml`을 지우면 된다. PC 쪽은 `py -3.14 host\install_dbgrec.py --uninstall`이다.

## 12. 비용과 위험

### 12.1 비용 [추정, CI와 실기기 값으로 바꾼다]

| 항목 | 동글 | 오른쪽 (2단계) | 왼쪽 |
|---|---|---|---|
| Flash | +12~25 KB (268 → 약 290 KB / 780 KB) | +10~20 KB (197 → 약 215 KB) | 0 |
| RAM | 약 83 KB(E 16, B 64, 버퍼, 스레드). 지금 여유 약 180 KB에서 빠지므로 약 100 KB가 남는다. CI는 40 KB 이상 남기를 요구 | 약 6 KB. 지금 여유 약 218 KB에서 빠진다 | 0 |
| CPU | 0.3% 미만 | 움직이는 중 약 0.2%, 쉴 때 거의 0 | 0 |
| 무선 | 1b: 0. 2단계: 연결마다 4~5 round trip(각 최대 약 232 ms) | 아래 목록 | 0 |
| 배터리 | USB 전원 | 목표 2% 이하. tick은 활동 중에만 | 0 |
| PC | 에이전트 RAM 약 30 MB(정리 하위 프로세스가 하루 한 번 30초 이내로 약 100 MB 더 쓴다), CPU 0.5% 미만, 디스크 하루 약 2~4 MB(최대 8 MB) | | |

구현 규모는 1.7절 '단계별 부담' 표에 있다.

오른쪽 무선 비용(2단계):
- 활동 중 약 초당 1 PDU다. 트랙볼 약 250 PDU/s의 약 0.4%다.
- 쉴 때는 1분에 1개다.
- 송신 조건이 맞지 않으면 0이다.
- ATT 버퍼 3개 중 최대 1개만 쓴다.

### 12.2 위험과 대응

| 위험 | 대응 |
|---|---|
| 기록기가 타이밍을 바꿔 멈춤이 사라짐(Heisenbug) | 훅 5 µs 이하. 프로덕션 스택·큐·연결 파라미터를 CI로 강제. HCI·로그·실행 중 flash 쓰기 없음. 조건이 맞을 때만 한 건씩 보내는 오른쪽 송신(pump). 1a 기준선 대비 `mode off` 날. 기록기를 켰을 때만 멈춤이 사라진다면 그것 자체가 증거다 |
| 디버그 펌웨어가 동글을 망가뜨림 | 첫 flash 전에 훈련하는 한 동작 복구, 안전 수준 SAFE/INERT, 기록된 리셋 |
| 복구 감시기가 엉뚱한 보드를 구움 | USB serial로만 보드를 구분(F29). 복구는 디버그 이미지를 stage해 구운 뒤나 훈련 때만 켜짐. 모르는 serial은 확인을 받음 |
| HID_1이 interface 번호를 바꾸거나 Studio를 혼란시킴 | CDC 하나일 때의 순서를 소스로 확인, CI 검사, 1b의 첫 확인 항목, usage page와 serial로 장치 찾기 |
| fault handler가 엉뚱한 flash에 씀 | slot 준비 표시, 주소 범위, 지워짐 확인, 재진입 latch |
| 기록기로 인한 부팅 반복 | 조기 crash 2번에 SAFE, 5번에 INERT, 리셋 한 번으로 해제, 복구 동작 |
| diag 구독이 ZMK를 방해함(2/2b) | client는 자기 서비스만 다룬다. 한 번에 ATT 요청 하나, 요청마다 유휴 조건(idle gate) 재확인, `atomic_set_bit`으로 VOLATILE, unsubscribe 없음. shadow는 2b에서 SENT 확인과 함께만 |
| 오른쪽 연결 참조가 새어 다시 연결되지 않음(2) | 참조는 무장할 때 하나만 잡고 `disconnected`에서만 놓는다. 반복 HELLO는 참조를 더 잡지 않는다. 2단계 3번에서 시험한다 |
| Studio 레이어 순서 변경이 combo를 옮김 | 60초 index/id 점검, 트레이 노랑, README |
| Windows Raw Input 합치기나 잠금 화면이 가짜 호스트 공백을 만듦 | Σ\|d\|와 공백 기준, 잠금·desktop·endpoint·lag 조건(R4) |
| 에이전트가 조용히 죽음 | 이름 있는 mutex로 하나만 실행, 에이전트 이어받기, 실행 시간 기준의 heartbeat 순번(깨어난 직후 죽이지 않음), Run 키, `doctor`, 트레이 상태 |
| 디스크 증가 | STATUS 줄이기, 블록 형식, 정리 하위 프로세스의 zstd(전원 연결 시 19, 배터리 9), 365일 상한과 4 GB 안전장치, 오래된 후보 보고서·fw 보관본 정리, 실측 |
| CI 아티팩트 만료 | `flash`와 `rescue import`가 ELF와 심볼을 build_id·run별로 로컬 보관 |
| 패치가 적용되지 않음(3b/4) | ZMK·드라이버는 SHA로 고정되어 있다. Zephyr는 브랜치를 따라가므로, Zephyr 패치(`_llfix`)는 `west-list.txt`의 Zephyr SHA가 시험한 것과 같을 때만 적용하고 다르면 CI가 실패한다 |
| 디버그 이미지와 복구 이미지가 다른 트리에서 빌드됨 | 모든 빌드 항목의 `west-list.txt`가 같지 않으면 `gates`가 실패. build_id와 run으로 바이너리를 구분 |
| keymap 수정이 마크 전제를 깸 | CI keymap 검사가 디버그 빌드를 실패시킴 |

## 13. 결정이 필요한 것

설계는 답이 없어도 동작한다. 답은 우선순위를 정한다. 번호는 영문 명세와 맞췄다.

답이 필요한 시점:
- 1a 시작 전: Q1, Q2, Q12
- 1b 시작 전: Q3, Q4, Q5, Q6, Q11(레이어 비트)
- 해당 단계 전: Q7(3b/4), Q8(3a), Q9(4), Q11(`&dpi` 시각, 2b), Q13(2), Q14(C8이 나왔을 때), Q15(수정 후보가 나왔을 때)

- **Q1.** 멈춤은 어떤 모습인가?
  - 키도 함께 멈추는가?
  - 얼마나 가는가(1초 훨씬 미만, 1~4초, 4초 초과)?
  - 굴리는 도중인가, 쉬다가 처음 굴릴 때인가?
  - 재개될 때 커서가 튀는가?
  - 오른손 타이핑, `&dpi`, SYMBOLS/SCROLL, 배터리와 관련이 있는가?

  기본: 모른다고 가정하고 모두 기록한다.
- **Q2.** HKCU Run 키 자동 시작, supervisor, 트레이 아이콘을 받아들이는가? 노트북을 며칠씩 켜 두는지, 덮개를 닫고 쓰는지, 노트북 자체 키보드를 쓰는지도 알려 달라. 기본: 수락. 디스크 예산은 하루 24시간 깨어 있는 날 기준이다.
- **Q3.** 마크 조합(POINTER+R+T, `[`+`'`)과 단축키 Ctrl+Alt+Shift+M(오른쪽 Shift)이 편한가? 기본: 명세대로 한다. 단축키는 `config.json`에서 바꿀 수 있다.
- **Q4.** 왼쪽 반을 모든 단계에서 프로덕션으로 둬도 되는가? 쓸 때 항상 켜 두는가? 기본: 프로덕션이고, 항상 켜져 있다고 가정한다.
- **Q5.** Studio로 동글에 keymap을 저장한 적이 있는가? 특히 레이어 순서 변경이나 삭제가 있었는가? 디버그 기간 동안 레이어 순서 변경과 삭제를 하지 않을 수 있는가? 기본: 이력은 모른다고 가정한다. 60초 점검이 어긋남을 잡는다.
- **Q6.** 동글에 BLE 호스트 프로필이 페어링·연결되어 있는가, 아니면 USB만 쓰는가? 기본: USB만 쓴다고 가정한다. 활성 프로필이 연결되어 있지 않으면 동글이 계속 광고하므로, 그 상태를 C7 문맥으로 기록한다.
- **Q7.** 3b/4단계에서 workflow가 적용하는 패치 파일(`dbgrec/patches/`)을 써도 되는가? 기본: 된다. fork는 만들지 않는다.
- **Q8.** 3a단계 wrap pack(디버그 빌드에서만 GNU ld `--wrap`으로 몇몇 함수를 가로채는 것)을 써도 되는가? 기본: 답할 질문이 정해졌을 때만 쓴다.
- **Q9.** 4단계 fast-rest A/B(fast인 날 센서 전류가 조금 는다)를 해도 되는가? 기본: 하지 않는다. 요청할 때만 켠다.
- **Q11.** 개인 정보: 활동 중 100 ms 레이어 비트, 그리고 2b에서 `&dpi`를 누른 시각(방향만)을 기록해도 되는가? 기본: 둘 다 허용으로 가정한다. 거부하면 레이어 비트를 빼고 C4는 S6 휠과 메모로만 판정한다.
- **Q12.** 저장소가 공개인가, 비공개인가? 기본: 90일 아티팩트와 로컬 보관만 쓴다. prerelease는 만들지 않는다. 비공개이고 Actions 시간이 모자라면 프로덕션 workflow에 `paths-ignore`를 더할 수 있다(11.1절).
- **Q13.** 오른쪽 배터리 추가 소모는 어디까지 허용하는가? 기본: 2% 이하.
- **Q14.** C8이 나오면 며칠 동안 허브 대신 PC 포트에 직접 꽂아 볼 수 있는가? 기본: 그렇다.
- **Q15.** 수정 후보는 보고서 권고대로 프로덕션에 올리는가, 건별로 정하는가? 기본: 건별. 보고서는 근거만 제시한다.

## 14. 검증 대장

### 14.1 확인함: 고정된 소스

ZMK @9ebbeff, Zephyr fork 10ba6d0, 드라이버 @44b4a76, `my-keymap` 기준이다. 근거는 영문 명세 §1과 §20에 있다. 단, ZMK의 west.yml은 Zephyr를 브랜치 `v4.1.0+zmk-fixes`(clone-depth 1)로 가리킨다. 그래서 Zephyr는 고정되어 있지 않다. 10ba6d0은 2026-10-01에 CI가 받은 커밋이다. CI는 모든 빌드 항목의 `west-list.txt`가 같은지 확인하고, Zephyr SHA가 10ba6d0이 아니면 경고한다.

- **ZMK 구독(F1).** ZMK의 split central 구독은 사실상 VOLATILE이다. `atomic_set(…NO_RESUB)`이 1, 즉 VOLATILE 비트를 저장하기 때문이다. CCC 읽기는 ZMK가 구독했다는 증거가 되지 못한다.
- **USB(F4, F5, F6).**
  - Windows는 feature SET을 128 B로 채워 보내고, Zephyr의 검사는 `wLength > 128`이다.
  - HID 콜백은 usbd_workq(협조형 −1, 1 KB 스택)에서 돈다.
  - CDC가 하나일 때 HID_1은 interface 3, EP 0x84다.
- **HCI(F7).** `BT_BUF_CMD_TX_COUNT=1`에서 HCI 명령을 쓰면 동글 sysworkq가 교착될 수 있다.
- **리셋 레지스터(F8, F9).**
  - GPREGRET2는 soft reset과 lockup을 넘어 남고, 핀 리셋·watchdog·브라운아웃·POR에 지워진다.
  - RESETREAS는 앱이 지울 때까지 누적된다.
- **fault(F10).**
  - fatal handler가 반환하면 그 thread만 abort되고 시스템은 계속 돈다.
  - LL_ASSERT도 handler 반환 뒤 계속된다.
  - nvmc의 주소 확인은 컴파일에서 빠져 있다.
- **keymap(F11, F12, F13).**
  - combo는 레이어 index로 거른다.
  - metadata가 없는 behavior는 Studio에서 바인딩할 수 없다.
  - Studio가 불러온 바인딩의 `behavior_dev`는 NULL일 수 있다.
- **빌드(F14, F15, F16).**
  - snippet 하나는 conf와 overlay를 하나씩만 덧붙인다.
  - 컨테이너의 기본 shell은 dash이고 `nm`이 PATH에 없다.
  - 동글 ELF에는 항상 "keycode" 문자열이 있다.
- **BT 문맥(F17, F18, F19).**
  - `connected`/`security_changed`는 BT RX WQ, `disconnected`는 sysworkq에서 돈다.
  - notify 완료 콜백은 ATT 버퍼가 해제될 때 불린다.
  - 이벤트의 source는 bond slot 번호이지 왼쪽/오른쪽이 아니다.
- **기타(F25, F26, F27).**
  - ATT TX 수는 동글 10, 반 3이다. discovery 이어가기는 `K_NO_WAIT`로 할당하고 실패하면 조용히 끝난다.
  - 새 GATT 서비스는 DB hash를 바꾼다(첫 부팅과 롤백 뒤 첫 부팅에 `bt/hash` 1회 쓰기).
  - 프로덕션에서 `THREAD_NAME`이 꺼져 있다.
- **소스로 확인한 가정(A-nn).** A-07과 A-21은 실기기 확인이 따로 남아 있다(14.4절).
  - A-04: `att_pool`을 이름으로 찾을 수 있다.
  - A-06: sysworkq에서 부르는 `bt_gatt_notify_cb`는 기다리지 않는다.
  - A-07: `zzz_` 이름이 순서를 보장한다.
  - A-08: 드라이버 뒤(POST_KERNEL 99)에 등록한 두 번째 GPIO 콜백이 드라이버 콜백보다 먼저 돈다.
  - A-12: `POST_KERNEL 99`가 `bt_enable`보다 먼저다.
  - A-14: MPU 스택 가드와 FPU_SHARING의 영향(3단계 변형에만 해당한다).
  - A-17: Studio는 combo를 편집하지 못한다.
  - A-21: 조건부로, 앱이 지운 뒤 RESETREAS가 0이면 POR/BOR이다.
  - A-32: timer ISR에서 읽어도 안전한 값들.
  - A-33: HID 콜백 문맥.
  - A-37: Studio 목록에 `dbg_mark`가 보이지만 바인딩은 거부된다.
  - A-45: slot source.
  - A-53: `sys_rand32_get()`은 xoshiro128이고, 첫 호출 때 nRF RNG(`zephyr,entropy = &rng`, PRE_KERNEL_1에서 초기화)에서 128비트 시드를 받는다. 그래서 `POST_KERNEL 99`에서도 실제 엔트로피다. 첫 호출은 1~2 ms 기다릴 수 있다. CI는 `.config`에서 `XOSHIRO_RANDOM_GENERATOR=y`만 확인한다.

### 14.2 확인함: 이 PC

- Raw Input 장치 이름은 `Col03`이다. API마다 대소문자가 다르다(F28).
- Windows 빌드는 10.0.26300이다. 백그라운드 Raw Input이 합쳐지거나 제한될 수 있다(F20).
- `GetMessageTime`은 32비트로 되돌아간다(F21).
- 이 노트북의 전원 동작: 배터리일 때 3시간 뒤 최대 절전, Fast Startup 켜짐(F22).
- Task Scheduler XML이 BELOW_NORMAL 우선순위로 해석된다(F23).
- 세 보드는 부트로더와 ZMK에서 같은 USB serial(FICR DEVICEID)을 낸다. 동글은 두 모드 모두 `71FB7A39AFC7297C`였다. 반도 케이블을 꽂으면 `1D50:615E`로 잡히고, 세 부트로더는 드라이브만으로 구분되지 않는다(F29).
- named pipe: 없는 파이프에 접속하면 바로 FileNotFoundError, 같은 이름의 두 번째 서버는 PermissionError다. `accept()`는 시간 제한 없이 막힌다.
- 레벨 19 zstd는 30 MB에 CPU 9.5초, 메모리 약 100 MB가 들었다. 배터리일 때 최대 프로세서 상태는 30%다.
- HighQoS 설정은 적용되고, 숨은 창의 100 ms 타이머는 105~116 ms에 왔다. Run으로 뜬 프로세스는 NORMAL 우선순위이고 job 밖이다.
- Python 3.14.6에 `compression.zstd`가 있다. pyserial과 hidapi는 설치되어 있지 않다. user site 폴더는 아직 없다.
- STATUS GET 지연(p95 1 ms 이하)은 HID_1이 생긴 뒤 1b 3번(A-46)에서 잰다.

### 14.3 확인하지 못함: CI에서 확인할 것

| 항목 | 내용 | 방법 | 시점 |
|---|---|---|---|
| A-03 | `ZMK_EXTRA_MODULES`로 snippet_root가 풀리고 모듈이 빌드됨 | `.config`에 `CONFIG_DBGREC=y`, DTS에 `dbgrec_partition@e9000`. 실패하면 `-DSNIPPET_ROOT` | 1b 첫 CI(`dongle_dbg`) |
| A-16 | RAM/flash 예산(동글 약 83 KB, 40 KB 이상 남음, 오른쪽 약 6 KB) | gates job의 차이 | 1b 첫 CI(`dongle_dbg`), 2 CI |
| A-05 | `acl_pkts`가 내부 헤더로 컴파일됨 | `=y` 빌드, 실패하면 `=n`으로 다시 하고 표시 | 2b CI |
| A-48 | `ll_rssi_get`이 모듈에서 컴파일·링크됨. `ll.h`는 자체 include가 없으므로 원형을 직접 선언한다 | `dongle_dbg_rssi` 빌드 | 2b CI |
| A-35 | `--wrap`이 ZMK 호출 지점을 실제로 바꿈 | build.log의 `-Wl,-y` 추적, 부팅 `wrap_ok=1` | 3a |
| A-31, A-41 | 로그 backend 형식 해석, 정확한 형식 문자열 개인 정보 검사 | 가짜 패키지 단위 테스트, `.rodata` 검사 | 3 |
| A-36 | PMW3610 패치와 4단계 cherry-pick이 적용됨(ZMK·드라이버는 고정 SHA, Zephyr는 그때의 브랜치 머리) | 변형별 빌드 | 3b, 4 |

### 14.4 확인하지 못함: 실기기에서 확인할 것

| 항목 | 내용 | 시점 |
|---|---|---|
| A-01 | Windows에서 HID_1이 MI_03으로 열거되고 MI_00(COM33), MI_02가 그대로이며 Studio가 연결됨 | 1b 1번 |
| A-46 | 관리자 권한 없이 vendor collection을 열고, 128 B GET/SET이 동작함 | 1b 3번 |
| A-11 | fault와 LL assert 문맥(thread, ISR)에서의 NVMC slot 쓰기가 믿을 만함 | 1b 8번, 오른쪽은 2단계 |
| A-22r | GPREGRET2가 `sys_reboot`를 넘어 남고 핀 리셋에 지워짐. 60초 뒤 조기 crash 수가 지워지고 다음 부팅에서 NORMAL이 됨 | 1b 8번 |
| A-13 | UF2 다시 굽기가 0xE9000~0xEBFFF를 건드리지 않음, 부트로더 버전 | 1b |
| A-20 | S3에서 동글 전원이 유지되고 S4에서 끊김(재개 뒤 POR) | 1b 9번 |
| A-21 | (소스로는 확인, 14.1) 앱이 지운 뒤 RESETREAS 0이 이 보드에서 POR/BOR을 뜻하는지 실기기에서 다시 본다 | 1b, 2 |
| A-52 | 평소 사용에서 KEYX 오탐이 거의 0 | 1b 계속 |
| A-49 | Run 키와 상호 감시가 강제 종료·S3/S4·탐색기 재시작 뒤에도 에이전트를 정확히 하나 유지함(이어받기와 깨어난 뒤 규칙 포함) | 1a 5~6번 |
| A-54 | USB serial로 보드를 구분함(부트로더와 앱의 serial이 같음을 이 PC에서 세 보드 모두 확인). 1a 2번의 추가 시험만 남음 | 1a 2번 |
| A-56 | 관리자 권한 창이 앞에 있어도 WM_INPUT이 계속 옴(문서에 없음). 확인 전까지 R4와 1a 판정에 조건으로 둔다 | 1a 3번 |
| A-50, A-19 | 백그라운드 Raw Input 합치기 정도, Raw Input이 MI_02 Col03 장치에서만 옴 | 1a 3번, 1b 4번 |
| A-43 | ctypes 에이전트의 몇 주 단위 안정성, lag 계산 | 1a 시작부터 7일 연속 운용(1b로 넘어가도 이어서 센다) |
| A-26 | 디스크 사용량(하루 2~4 MB, 최대 8 MB) | 1a/1b 일주일 |
| A-07, A-44 | (소스로는 확인) `right_dbg` 뒤 재페어링 불필요, 1회성 쓰기가 정해진 부팅에서만 일어남(롤백 포함)을 실기기에서 다시 본다 | 2단계 2번 |
| A-51 | handshake가 유휴 조건 안에서 끝나고 오른쪽 재부팅마다 다시 무장됨. 반복 HELLO가 연결 참조를 더 잡지 않음 | 2단계 3번 |
| A-27 | 오른쪽→동글 시계 하한 포락선 잔차 p95 10 ms 이하 | 2단계 |
| A-55 | 2단계 훅을 넣고도 input 1024, sysworkq 2048(pump와 완료 콜백 포함), BT RX 2200, split notify 756, dbgrec 1024, 인터럽트 스택 2048의 여유가 256 B 이상 | 2단계 8번 |
| 오른쪽 배터리 | 추가 소모 2% 이하 | 2단계 9번 |
| A-10 | 2단계 diag client의 ATT 사용이 ZMK를 굶기지 않음(굴리는 중 재연결 뒤에도 ZMK 구독 유지, 2b SENT 확인으로 재확인) | 2단계, 2b |
| A-09 | shadow 구독이 반에 CCC를 쓰지 않음, 반마다 10회 순환에서 ZMKSUB `order_ok` | 2b |
| A-30, A-42 | pevq 예측 유실이 실제 S3−S4와 맞음, UNKNOWN 상태 처리로 D-STUCKLAYER 오탐이 없음 | 2b |
| A-38r, A-48 | `ll_rssi_get`이 thread에서 컴파일되고 그럴듯한 값을 읽음. `BT_CTLR_CONN_RSSI`는 관찰자 변경으로 보고서 머리에 찍는다 | 2b |
| A-24 | PMW3610이 쉬는 중에도 REST 샘플 주기 변경을 따름, downshift 연동 | 4 |

### 14.5 설계 중간안에서 바뀌거나 빠진 것

설계는 세 번 고쳤다(v3). 중간안(v2)의 주장 중 소스 검증에서 반박된 것은 대체했고, MVP 범위를 줄이면서 몇 가지 기능을 뺐다.

**대체한 것(REPLACED).**
- HID_1 SET 64 B → 세 리포트 모두 128 B
- CCC 읽기로 ZMK 구독 확인 → SENT 플래그
- 부팅 때 이름·바인딩 점검 → 60초마다 index/id와 device 포인터 점검
- HCI RSSI → `ll_rssi_get` 변형
- GPREGRET2가 핀 리셋을 넘어 남는다는 가정 → flash slot을 기준으로 삼음
- 컨테이너의 `nm` → pyelftools
- 이전 lag 계산 → 32비트 랩에 안전한 계산

**뺀 것(DROPPED).**
- 장치 안의 SYMTAB, ping-pong crash page, 부팅 로그, CRASH_TAIL bin
- EV_MSC 지연 probe, 센서 준비 probe
- Task Scheduler
- Studio DTR 플래그, 레이어 이름 점검, Studio 오바인딩 점검
- absent 모드와 side buffer, 동글 pin, mark table, ACK 프로토콜, 동글로 보내는 HOST_MARK
- DWT 훅 비용 측정, 장치 안 검출기와 실행 중 임계값(오른쪽 ANOM_R 하나 제외), mode 외의 실행 중 설정 키
- LED 피드백, 왼쪽 반 경량 기록기, release job
- SQLite 색인, 리포트별 Raw Input 링

가정(A-nn)별 상태는 영문 명세 §20에 있다.

**v3.1 변경.** 두 번째 소스 검증(동글, 오른쪽, PC, CI)과 두 번의 교정 검토를 반영했다. 영문 명세 §21에 같은 목록이 있다.
- 동글: MARK 16 B, LINK 13 B로 크기 수정. BOOT에 `build_run`, STATUS에 현재 GPREGRET2와 `build_run`을 더함. bin의 입력 큐 수위를 0~16으로(16 = 가득 참) 넓히고 bin별 orphan 비트를 뺌.
- orphan-X는 오른쪽 드라이버에서 S4 사이 어디서든 생긴 Y 유실로 다시 정의했다. 동글 큐가 찬 때만 C3(동글 유실)로 판정한다.
- KEYX: 연결 콜백은 epoch만 올리고(동글이 central인 연결만), listener가 집합을 비운다. mode가 바뀌면 두 집합을 모두 비운다. listener가 combo·keymap 뒤에 있는지는 CI 검사가 됐다.
- 마크 조합: POINTER를 R과 T 사이에 놓으면 "r"이 아니라 "t"가 새는 것으로 고쳤다. 규칙은 'R과 T를 모두 누를 때까지 POINTER 유지'다. 마크 combo가 `/combos`의 첫 두 자식인지 CI가 확인한다.
- 안전 수준: 늦은 crash는 조기 crash 수를 0으로 되돌리고, 60초 뒤 지우기는 모든 수준에서 일회성 work가 한다. 훅은 수준을 보고 돌아가며, SAFE/INERT의 마크는 `mark_count`만 올린다. 오른쪽 반의 SAFE/INERT 동작을 정했다.
- tick 지연은 `k_cycle_get_32() − k_uptime_ticks()`로 잰다. 0xEA000~0xEBFFF는 쓰지 않는 예비 공간으로 적었다. A-37, A-53은 소스로 확인했다.
- 오른쪽: handshake의 연결 참조를 하나로 제한하고 `disconnected`에서만 놓는다. 반복 HELLO, 완료 콜백의 seq 확인, FIFO 버림 순서, HELLO 재전송, tick 멈춤 조건, S0 등록 시점, `inq_full` 비트, F26(CF 항목 없음)을 고쳤다. 스택 확인 대상에 dbgrec과 인터럽트 스택을 더했다(A-55).
- PC: 복구 감시기는 USB serial로만 보드를 구분하고(F29), 디버그 이미지를 stage해 구운 뒤나 훈련 때만 복구를 굽는다. `rescue import`, `rescue drill`, `rescue confirm`, `learn`, `diag hello`, `maintain`을 더했다. supervisor와 에이전트는 이름 있는 mutex, 이어받기, 실행 시간 기준 heartbeat를 쓴다. CLI 파이프 서버를 별도 스레드로 옮겼다. 관리자 창 조건(A-56)을 1a 판정과 R4에 더했다. 압축은 정리 하위 프로세스로 옮겼고, 디스크 예산과 상한을 다시 계산했다. Run 값, HighQoS, 세션 상태 읽기, `CloseDesktop`, `CREATE_NO_WINDOW`를 고쳤다. S4–S6 비교는 processor 없는 레이어의 S4 Σ|d|로 한다. `flash --target`과 `fw\<build_id>-r<run>\` 보관을 더했다.
- CI: `paths-ignore`만 프로덕션 workflow의 선택 변경으로 두었다. `host_tests` job(Windows, Python 3.14), `yq`, keymap 검사 방식, `stage:` 키, `allow:` 목록, 복구 항목 생성 규칙, 항목별 DTS 검사, `zmk.elf`/`zmk.map` 이름, 겹치지 않는 업로드 이름, `west-list.txt` 일치 검사, `gates` 뒤의 `bundle`을 정했다. Zephyr가 떠다니는 브랜치라는 점을 반영했고 `DBGREC_BUILD_RUN`을 더했다. 1a CI는 복구 이미지, 호스트 테스트, keymap 검사만 한다.
- 문서: 1절에 사용자 할 일, 평소에 달라지는 것, 문제가 생기면, 단계별 부담, 용어를 더했다. 2.1~2.2를 표로 줄였다. S0~S6은 '지점', NORMAL/SAFE/INERT는 '안전 수준'으로 부른다. 10.2절(1a 판정 규칙)을 새로 넣어 기존 10.2, 10.3이 10.3, 10.4가 되었다. Q10을 지우고(번호는 다시 매기지 않음) 질문을 답이 필요한 시점별로 묶었다.
