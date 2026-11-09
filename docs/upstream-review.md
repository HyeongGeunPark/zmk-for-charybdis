# 원본 저장소 검토 기록

> 원본: [Vzhao-L/zmk-for-charybdis](https://github.com/Vzhao-L/zmk-for-charybdis)
> (키보드 제작자의 저장소, 기본 branch `main-20250226`)<br>
> 마지막 검토: 2026-11-09

`my-keymap`은 원본 `main-20250226`의 `3fde551`에서 갈라졌다. 이후 ZMK line,
트랙볼 드라이버, 동글 구성이 모두 바뀌어 원본을 merge하지 않는다. 대신 원본의
변경을 읽고 필요한 것만 별도 커밋으로 옮기며, 어디까지 읽었는지를 이 문서에
남긴다. 그래서 GitHub의 "N commits behind" 표시와
`git log my-keymap..upstream/main-20250226`은 검토 후에도 0이 되지 않는다.
검토 범위의 기준은 아래 표의 커밋이다.

## 다음 검토 방법

원본은 remote로 등록하지 않고 URL로 받는다.

```bash
git fetch https://github.com/Vzhao-L/zmk-for-charybdis.git "+refs/heads/*:refs/remotes/upstream/*"
```

1. 아래 표의 branch마다 `git log <검토한 커밋>..upstream/<branch>`로 새 커밋만
   본다. 커밋 메시지가 대부분 "Update ..."이므로 `-p`로 내용을 봐야 한다.
2. 표에 없는 branch는 새로 생긴 것이다. `git merge-base my-keymap upstream/<branch>`가
   `3fde551`이면 이 키보드 계열이므로 자세히 본다.
3. 검토가 끝나면 표의 커밋과 날짜, 결정 목록을 갱신한다.

## 검토한 커밋

### 이 키보드 계열 (`3fde551`에서 갈라짐)

| Branch | 검토한 커밋 | 커밋 날짜 | 내용 |
| --- | --- | --- | --- |
| `main-20250226` | `45ee4ba` | 2026-10-25 | 엔코더 스크롤 튜닝, 디바운스 설정 삭제 |
| `main-badjeff` | `d61a9b3` | 2026-09-28 | badjeff PMW3610 드라이버(`zmk-0.3`) 이관, 엔코더 튜닝 |
| `main-wake` | `ee25db2` | 2026-09-15 | kscan `wakeup-source`, deep sleep 1분 |
| `scylla-20260904` | `0a80976` | 2026-09-05 | Scylla 기종 배열과 키맵 |
| `FK` | `6c595ea` | 2026-08-30 | F-CUBE 기종, 트랙볼과 RGB 끔 |

### 다른 기종 또는 더 오래된 기준

내 구성과 겹치는 것이 없어 결정 없이 커밋만 기록한다.

| Branch | 검토한 커밋 | 커밋 날짜 | 갈라진 지점 |
| --- | --- | --- | --- |
| `Cygnus-35A` | `050b536` | 2026-10-20 | `270e1df` |
| `charybdis-Nano35-MOD` | `e488bb8` | 2026-10-13 | `3e2f9ee` |
| `Cygnus-36` | `8f4199e` | 2026-10-11 | `270e1df` |
| `Cygnus-46` | `d474721` | 2026-10-02 | `270e1df` |
| `Charybdis-mini36-Mod` | `b88b9b3` | 2026-09-25 | `3e2f9ee` |
| `charybdis-RL-Nano35MOD` | `0a3fa22` | 2026-09-13 | `3e2f9ee` |
| `charybdis-Nano35` | `c820219` | 2026-08-11 | `3e2f9ee` |
| `charybdis-MINI36-RGB-EC11` | `8a66e81` | 2026-08-05 | `3e2f9ee` |
| `test` | `e0939aa` | 2026-08-02 | `87a8fe3` |
| `main-RL` | `459d590` | 2026-05-23 | `0e2df46` |
| `charybdis-RL-Mini36-MOD` | `5b26d79` | 2026-04-20 | `3e2f9ee` |
| `Z-fold` | `bd8d049` | 2026-03-31 | `270e1df` |
| `GC9A01` | `70fc3f7` | 2026-03-27 | `011c166` |
| `Charybdis-RGB-20250226` | `b3ddc14` | 2025-12-15 | `3e2f9ee` |
| `SCYLLA` | `c7e4d0b` | 2025-07-16 | `270e1df` |
| `HG-DactylGG-RGB` | `e34b5a0` | 2025-07-15 | `270e1df` |
| `SCYLLA-RGB` | `d484499` | 2025-07-02 | `270e1df` |
| `Dactyl-57GG-RGB` | `2b7c006` | 2025-06-22 | `270e1df` |
| `Hatsu-20250226` | `037ac76` | 2025-05-29 | `caa2db2` |
| `Charybdis-RGB-FPC-20250226` | `07a5c7b` | 2025-04-10 | `1a2cd37` |
| `Hatsu` | `436d407` | 2025-01-03 | `caa2db2` |
| `Charybdis-RGB` | `f6376c8` | 2025-01-03 | `caa2db2` |
| `main` | `44f88f7` | 2024-12-29 | `011c166` |
| `Dactyl-57-RGB` | `ffa20e9` | 2024-12-11 | `270e1df` |

## 결정

### 채택

| 원본 변경 | 적용 | 비고 |
| --- | --- | --- |
| 디바운스 7 ms 설정 삭제, 기본값 5 ms (`main-20250226` `4bbfafc`) | `7b476e1` | 제작자가 5 → 7 → 기본값 순으로 바꿨다 |
| kscan `wakeup-source`와 `CONFIG_ZMK_SLEEP` (`main-wake`) | `3185faf` | 1분 대신 5분. 동글은 제외하고 두 half에만 |

### 기각

| 원본 변경 | 이유 |
| --- | --- |
| 엔코더 `steps`, `triggers-per-rotation`, `pulses-per-detent`, 엔코더 behavior `tap-ms`, 오른쪽 엔코더 추가 | 엔코더를 쓰지 않는다. 노드가 모두 disabled다 |
| `ZMK_POINTING_DEFAULT_SCRL_VAL`, `ZMK_POINTING_DEFAULT_MOVE_VAL`, `&msc`/`&mmv`의 가속 설정, `&msc_input_listener`/`&mmv_input_listener` scaler | 마우스키 스크롤·이동 behavior(`&msc`, `&mmv`) 설정이다. 키맵에서 쓰지 않는다. 트랙볼 스크롤은 동글 listener의 processor chain이 맡는다 |
| badjeff 드라이버 `zmk-0.3` branch, `spi1`, `pixart,pmw3610` (`main-badjeff`) | 이미 더 새 ZMK line에서 같은 저자의 `pixart,pmw3610-alt` 드라이버를 쓴다 |
| 키맵과 기종별 배열 (`scylla-20260904`, `FK`, 각 branch의 keymap 변경) | 다른 기종이거나 개인 키맵이다 |
| RGB idle auto-off (`test`) | Underglow를 쓰지 않는다 |
