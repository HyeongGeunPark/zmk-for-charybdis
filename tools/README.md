# capture_log.py: ZMK USB 로그를 Windows에서 파일로 저장

디버그 펌웨어(`docs/debug-logging.md`)의 USB 시리얼 포트를 읽어 포트마다 시각이 붙은 로그 파일로 저장한다.
여러 포트(동글 + 오른쪽 반)를 한 명령으로 받고, Enter를 누르면 모든 파일의 같은 시각에 `### MARK n`이 들어간다.
전체 절차와 로그 해석은 `docs/debug-logging.md`에 있다.

```powershell
py -m pip install pyserial                     # 한 번만
py tools\capture_log.py --list                 # 포트 목록 (* = ZMK/Zephyr로 보이는 포트)
py tools\capture_log.py --port COM<동글> --name dongle --port COM<오른쪽> --name right --mark --quiet
py tools\test_capture_log.py                   # 자체 테스트 (하드웨어, pyserial 불필요)
powershell -File tools\mark_window.ps1 -Mark 1 > mark1.txt   # 마크 전후 3초/1초 구간 추출
```

`COM<...>`는 자리 표시자다. 실제 번호는 `--list`의 SERIAL 열로 보드를 구분해 찾는다(동글과 오른쪽 반은
일련번호가 다르다).

- `--port`와 `--name`은 순서대로 짝이 된다. 파일은 `logs\<name>_YYYYmmdd_HHMMSS.log`(`--outdir`로 변경).
- 줄 형식: `PC시각 [보드 부팅 후 시각] <수준> 모듈: 내용`. `###` 줄은 도구가 쓴다(`connected`, `disconnected`,
  `reconnected`, `MARK n`, `port changed`, `stats`).
- `--mark`(`--grep-mark`): Enter = 모든 파일에 MARK, Enter 전에 쓴 글은 메모. Ctrl+C로 끝내면 flush하고 요약을 낸다.
- `--quiet`: 장치 줄을 콘솔에 되풀이하지 않는다(초당 수백 줄이라 마크 확인 메시지가 묻히고 PC에 부하를 준다).
  `MARK n inserted`와 15초 무입력 안내는 그대로 나온다. 포트를 처음 찾을 때만 빼고 쓴다.
- 요약 `### stats`의 `nonlog`(로그 형식이 아닌 줄), `partial`(잘린 줄), `drop_markers`/`dropped_messages`(펌웨어가 낸
  `--- N messages dropped ---`)가 0이 아니면 그 구간의 결론은 보류한다. 0이라고 유실이 없다는 뜻은 아니다
  (CDC 링이 넘치면 글자가 조용히 사라지고 줄 머리와 꼬리가 붙은 줄은 정상 줄로 세어진다). 문서 5절의 추가 점검을 한다.
- 콘솔 출력은 별도 스레드가 맡아 Windows 콘솔이 멈춰도(QuickEdit 선택 등) 포트 읽기는 멈추지 않는다.
- 포트가 사라지면(리셋, 재연결) 0.25초마다 다시 열고 `### disconnected`/`### reconnected`를 남긴다. 다른 COM 번호로
  돌아오면 USB 인터페이스 위치(LOCATION의 `:x.N`)까지 알 수 있을 때만 같은 기기를 따라간다(`--no-follow`로 끔).
  Windows에서는 LOCATION이 비는 경우가 많아, 그때는 따라가지 않으니 COM 번호가 바뀌면 도구를 다시 실행한다.
- 그 밖의 옵션: `--keep-ansi`, `--partial-timeout`, `--retry-interval`(`--help`).
  종료 코드: 0 정상, 2 사용법/포트 선택, 3 pyserial 없음, 4 로그 파일 생성 실패.
- COM 포트는 한 프로그램만 열 수 있다(PuTTY, 시리얼 모니터를 닫는다). 디버그 동글은 Studio를 끄고 로그용 CDC 포트
  하나만 열어 둔다. USB 전원이면 ZMK 딥슬립이 없다.

확인하지 못한 것: 실제 보드와의 동작, 동글의 실제 열거, Windows `usbser.sys`가 뽑힘 때 내는 예외의 정확한 문구.
가짜 pyserial 테스트 외에, 검증 과정에서 pyserial 3.5와 com0com 가상 포트 쌍으로 읽기, 잘린 줄, 사용 중 포트 재시도,
실제 Ctrl+C 종료를 확인했다.
