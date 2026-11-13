# 벤치마크 방법과 재현

이 실험은 같은 구현 과제를 기본 Codex(A), 원본 billion-context(B), 개선판(C)으로 각각 한 번 수행한 기록이다. 실제 Codex 구독 인증과 모델 응답을 사용했다. A/B는 2026-11-06, C는 2026-11-13에 실행했다. 동일 시점의 무작위 반복 실험이 아니므로 실행 시간 차이를 패치의 인과 효과로 해석하지 않는다.

결과와 비용 해석은 [평가 결과](benchmark-results.md), 다른 환경에서 실행할 명령은 [재현 도구 사용법](../benchmarks/REPRODUCE.md), 일반 설치는 [설치 안내](installation.md)를 따른다.

## 기록과 재현 도구

| 위치                                              | 역할                                                                  |
| ------------------------------------------------- | --------------------------------------------------------------------- |
| [historical/ab](../benchmarks/historical/ab/)     | A/B를 실행, 비교, 검증한 당시 스크립트                                |
| [historical/c](../benchmarks/historical/c/)       | C 실행 당시 runner, 이후 보강한 runner, watchdog, 비교, 비용 스크립트 |
| [fixture.py](../benchmarks/fixture.py)            | 합성 과제, 프롬프트, 숨김 정답 생성                                   |
| [collector.py](../benchmarks/collector.py)        | Codex OTLP 수집                                                       |
| [analyze.py](../benchmarks/analyze.py)            | 요청별 usage와 실행 기록 집계                                         |
| [grade.py](../benchmarks/grade.py)                | 완성 코드와 기억 응답 외부 채점                                       |
| [dataset-v2](../benchmarks/dataset-v2/)           | 실제 사용한 프롬프트, 공개 입력, 숨김 입력, 정답, 해시                |
| [results](../benchmarks/results/)                 | 실제 실행에서 얻은 수치와 채점 결과                                   |
| [candidates](../benchmarks/candidates/)           | A/B/C가 각각 작성한 최종 구현과 테스트, 작업 메모                     |
| [instrumentation](../benchmarks/instrumentation/) | B/C의 모델 응답 usage를 관찰한 벤치마크 전용 코드                     |

역사 기록과 이식 가능한 재현 도구는 구분한다. 당시 스크립트에는 작성자의 절대 경로와 실행 날짜가 들어 있다. 이를 다른 컴퓨터에서 그대로 실행하는 대신 재현 도구에 자신의 경로를 지정한다. 경로, 인자, timeout 처리의 이식은 새로운 모델 측정 결과를 뜻하지 않는다.

C의 실제 실행본은 [run_benchmark.executed.py](../benchmarks/historical/c/run_benchmark.executed.py)다. [run_benchmark.hardened.py](../benchmarks/historical/c/run_benchmark.hardened.py)는 실행 이후의 timeout, 정리 보강본이다. 보강본을 당시 실행본으로 표기하지 않는다. 당시 터미널에 입력한 전체 셸 명령 문자열은 보존하지 않았으므로, 문서의 실행 명령은 저장된 코드와 manifest에서 재구성한 동등 명령이다.

원본 인증 파일, 계정 식별자, 전체 HOME, 개인 CLI 설정은 배포하지 않는다. 공개용 정규화 데이터는 필요한 측정 필드를 보존하며, 전체 원시 트래픽이나 구독 청구서의 대체물이 아니다. 계측 hook은 제품 코드에 설치하지 않고 벤치마크용 복사본에만 적용한다.

## 고정 조건

| 항목                            | 당시 값                                                                   |
| ------------------------------- | ------------------------------------------------------------------------- |
| 모델                            | `gpt-6-astra`                                                             |
| reasoning                       | `xhigh`                                                                   |
| Codex CLI                       | `0.163.0`                                                                 |
| 인증                            | 로그인된 Codex 구독의 파일 인증을 조건별 격리 HOME에 복사                 |
| 에이전트                        | 메인 1개, 서브에이전트 3개, 최대 깊이 1                                   |
| 설정한 context window           | `1000000`                                                                 |
| 설정한 native auto-compact 한도 | `900000`                                                                  |
| 실행 기록의 effective window    | `828400`                                                                  |
| Docker 메모리, CPU, PID 한도    | `8g`, `4`, `768`                                                          |
| Docker 보안 옵션                | 실행 사용자 UID/GID, `--cap-drop ALL`, `--security-opt no-new-privileges` |
| 작업 제한                       | 각 조건 전체 60분, 먼저 완료하면 종료                                     |
| 원본 billion-context commit     | `be611a8566c22ee0a65fb5765365671d47e810d5`                                |
| 원본 / C kernel 버전            | `0.0.182` / `0.0.183`                                                     |
| 데이터 seed                     | `20261106`                                                                |

Node 컨테이너 이미지는 `node@sha256:18a6d90fd60542269850c80ca03b29b1d9b14d6b221ac7ee8e35b0d33ef904bd`로 고정했다. A/B/C의 Codex 설정 해시와 이미지 digest가 일치한다. 각 조건의 manifest와 result가 실제 실행의 근거다.

클라이언트 내부 sandbox는 격리된 컨테이너 안에서 `danger-full-access`, 승인 정책은 `never`로 설정했다. 이는 호스트에서 같은 설정으로 실행하라는 안내가 아니다. 컨테이너에는 해당 조건의 작업 디렉터리, HOME, audit 디렉터리, 읽기 전용 Codex 바이너리와 billion-context 소스, collector만 연결했다. 모델에 접속해야 하므로 구현 컨테이너의 네트워크를 `none`으로 막지는 않았다. 외부 채점 컨테이너는 `--network none`이다.

앱, 플러그인, hook, web search, shell snapshot은 비활성화하고 multi-agent만 활성화했다. B/C는 자동 업데이트, advisory, release notes, auto-mode forge를 끄고 공지 URL을 로컬 비활성 주소로 지정했다. 압축 window는 `1000000`으로 설정했다. 일반 사용자의 기존 플러그인, 개인 지시문 전체를 복제한 환경은 아니다.

## 구현 과제

과제는 배포 이벤트에서 장치의 최종 상태와 오류를 재구성하는 Python CLI다. 실제 펌웨어를 빌드하거나 보드를 조작하지 않는다. Python 표준 라이브러리만 사용하고, 다음 인터페이스와 JSON 형식을 지켜야 한다.

```bash
python3 reconcile.py --input data/visible.jsonl --output analysis.json
```

출력은 `boards`, `incidents`, `totals`로 구성한다. 두 입력 schema를 정규화하고, 중복, 충돌 event ID를 처리하며, `BASELINE`, `STAGE`, `VERIFY`, `COMMIT`, `RESET`, `ROLLBACK`을 추적한다. 장치, epoch, sequence, 검증된 `(slot, digest)` 이력과 대기 중 transaction을 구분해야 한다. 입력 순서는 의도적으로 섞여 있고 wall-clock도 신뢰할 수 없게 만들었다.

초기 [README](../benchmarks/dataset-v2/visible/README.md)는 R1 규칙이다. 최종 규칙은 [final-contract.txt](../benchmarks/dataset-v2/oracle/final-contract.txt)에 있다. 후속 메시지가 R2/R3로 규칙을 바꾸므로 처음부터 최종 규칙을 에이전트에게 제공하면 같은 실험이 아니다.

| 입력           | 규모                    |
| -------------- | ----------------------- |
| 공개 사례      | 192개                   |
| 공개 이벤트    | 1,990개                 |
| 2단계 프롬프트 | 175,553자               |
| 3단계 프롬프트 | 176,374자               |
| 4단계 프롬프트 | 177,818자               |
| 세 묶음 합계   | 529,745자               |
| 숨김 종합 입력 | 72개 장치, 746개 이벤트 |
| 기억 문항      | 48개, 그중 8개 값 정정  |

문자 수를 토큰 수로 간주하지 않는다. manifest의 `rough_tokens_chars_div_4`는 입력 생성 당시의 추정치이고, 결과 표의 토큰은 모델이 보고한 실제 usage 합계다.

## 8단계 실행

| 단계 | 입력                                              | 수행과 평가 목적                                                                                                                                |
| ---- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | [01.txt](../benchmarks/dataset-v2/prompts/01.txt) | 초기 구현. 정확히 3개 서브에이전트에 ingest/schema, state-machine, report/audit 역할을 나누고 메인이 통합한다.                                  |
| 2    | [02.txt](../benchmarks/dataset-v2/prompts/02.txt) | 첫 로그 묶음과 운영 정보. 기존 구현을 분석, 보강한다.                                                                                           |
| 3    | [03.txt](../benchmarks/dataset-v2/prompts/03.txt) | 두 번째 묶음과 R2. timestamp 대신 sequence 순서를 사용하고 실패한 VERIFY가 이전 verified flag를 지우도록 수정한다.                              |
| 4    | [04.txt](../benchmarks/dataset-v2/prompts/04.txt) | 세 번째 묶음과 R3. epoch 변경 때 pending transaction을 지우고, rollback은 정확한 `(slot, digest)`로 판정한다. 앞서 준 운영 정보 8개도 정정한다. |
| 5    | [05.txt](../benchmarks/dataset-v2/prompts/05.txt) | 최종 통합, 테스트, `analysis.json` 생성. 이후 기억 검사에서 구현을 바꾸지 않는다.                                                               |
| 6    | [06.txt](../benchmarks/dataset-v2/prompts/06.txt) | 도구, 파일 읽기, 위임 없이 대화만 보고 48개 값을 JSON으로 답한다.                                                                               |
| 7    | [07.txt](../benchmarks/dataset-v2/prompts/07.txt) | 사용할 수 있는 컨텍스트 검색, 복원 도구와 이미 작성한 메모를 허용한다. 원문 배치 파일은 아직 제공하지 않는다.                                   |
| 8    | [08.txt](../benchmarks/dataset-v2/prompts/08.txt) | `evidence/02.txt`, `03.txt`, `04.txt`를 공개하고 같은 문항에 답한다.                                                                            |

각 단계는 같은 메인 thread를 `exec resume`으로 이어서 실행했다. 매 단계 새 대화로 시작하지 않는다. 서브에이전트도 같은 모델을 사용한다. 입력 로그 전체는 작업 파일에 있지만 운영 메모와 정정 지시는 단계별 프롬프트에 포함한다. 원문 프롬프트 파일 공개는 8단계 직전에만 수행한다.

운영 정보에는 ticket, 정확한 digest, settle window, 금지된 조작, escalation 범위, boot 상태, nonce, 보존 기간이 포함된다. 나중에 정확히 답할 값이라고 명시했다. 따라서 이 검사는 임의의 중요하지 않아 보이는 세부사항을 모두 기억하는지에 대한 blind recall 검사가 아니다.

## 외부 채점

[grade.py](../benchmarks/grade.py)는 에이전트가 작성한 구현을 별도 Docker에서 실행하고 저장된 oracle과 비교한다. 정답 파일은 구현 작업 컨테이너에 연결하지 않는다. 채점 컨테이너에는 후보 구현을 읽기 전용으로, 한 사례의 입력과 출력 디렉터리만 전달한다. 사례별 기본 timeout은 30초다.

- 숨김 종합 입력 1개와 개별 의미 규칙 사례 12개로 총 13개를 검사한다.
- JSON key 집합, 자료형, 배열 순서와 값까지 비교한다. “비슷한 결과”는 통과로 처리하지 않는다.
- 장치별 최종 상태, 오류의 false positive/false negative, 합계도 별도로 기록한다.
- 공개 전체 입력에 생성한 `analysis.json`도 oracle과 비교한다.
- 기억 답변은 48개 문자열을 정확히 비교하고, 누락, 추가 key, 예전 값, 정정값 반영 여부를 기록한다.
- 초기 미구현 stub은 숨김 검사 0/13으로 실패했다. 이는 채점기가 무조건 성공을 반환하지 않는다는 negative control이다.

단계 6의 도구 금지는 결과 JSON만으로 판단하지 않았다. 클라이언트 실행 기록, OTLP 도구 이벤트, B/C proxy 도구 이벤트를 함께 검사했다. 세 조건 모두 도구 없는 응답으로 확인됐다.

## 시간과 토큰 집계

시간은 구현 컨테이너와 collector를 준비한 뒤 첫 단계부터 마지막 단계가 완료될 때까지의 wall time이다. 서브에이전트 시간이 병렬로 겹쳐도 합산하지 않는다. 설치, 빌드, 외부 채점 시간은 포함하지 않는다. 단계별 시간은 각 arm의 result에 보존한다.

- A: 모든 thread의 Codex OTLP terminal usage 이벤트를 집계한다.
- B/C: proxy가 upstream에서 받은 응답의 usage를 집계한다. 내부 `compress`, `acp_status`, `decompress`, `search_context` 호출 과정의 모델 응답도 포함한다.
- B/C 계측은 동일한 응답 관찰 방식을 사용한다. 클라이언트에 보이는 usage만 집계하면 내부 컨텍스트 관리 요청이 빠진다.
- cached input은 input의 부분집합이고 reasoning output은 output의 부분집합이다. 두 값을 총량에 다시 더하지 않는다.
- 요청별 usage의 중복을 제거한다. 여러 단계의 누적 session usage를 그대로 합산하지 않는다.
- B의 12개, C의 15개 취소 요청은 `AbortError`로 종료돼 usage가 없다. 미상이며 0토큰으로 확정하지 않는다.

C에는 [외부 watchdog](../benchmarks/historical/c/watchdog.py)을 추가해 첫 단계 시작 시각 기준 60분을 감시했다. 실제로는 제한 전에 컨테이너가 종료돼 watchdog이 발동하지 않았다. 당시 runner와 watchdog, 이후 보강한 runner의 차이는 재현 도구 문서에 구분한다.

## 정보 보존 확인

B/C의 세 대량 프롬프트가 저장소에 원문 그대로 남았는지 문자열과 SHA-256으로 확인했다. 프롬프트 해시, 공개 입력 파일의 불변성, 5단계 후 Python 파일 수정 여부, 잘못된 JSONL 레코드도 검사했다. B는 T1 block 8개, C는 T1 block 5개가 남았다.

저장된 원문이 존재한다는 사실과 모델이 필요한 정보를 회수할 수 있다는 사실은 구분한다. 8단계는 외부에서 제공한 원문 파일을 읽는 검사이므로 billion-context 검색 품질의 증거로 사용하지 않는다. 단계 6부터 모든 문항이 정답이어서 단계 7의 복원 능력도 충분히 구별하지 못했다.

## 재현 순서와 변경 기록

1. [설치 안내](installation.md)의 의존성을 준비하고 원본 commit과 개선판 commit을 각각 고정한다.
2. [재현 도구 사용법](../benchmarks/REPRODUCE.md)에 따라 데이터 해시와 로그인, 바이너리 경로를 확인한다. 구독 모델 호출은 실행자의 사용 한도를 소비한다.
3. 먼저 로컬 fake upstream과 패키지 검사를 수행한다. 이 검사는 실제 모델 성능 측정과 구분한다.
4. 조건별 새 HOME, 작업 디렉터리, 컨테이너에서 동일한 8개 프롬프트를 실행한다. 채점기와 oracle은 작업 환경에 노출하지 않는다.
5. 후보 산출물과 기억 답변을 외부에서 채점하고 요청별 usage를 집계한다. 실패, timeout, usage 미보고를 그대로 기록한다.
6. 모델, CLI 버전, image digest, 입력, 소스 해시, 실행 순서와 날짜를 결과와 함께 보관한다. 모델 버전이나 사용 가능 기능이 달라졌다면 역사 실행의 동일 재현이 아니라 조건을 바꾼 새 실험으로 표시한다.

여러 과제로 반복할 때는 실행 순서를 교차하고 분산을 함께 보고한다. 첫 제출과 각 요구사항 단계의 소스 스냅샷을 남겨 같은 외부 테스트로 평가하면 첫 제출 통과율, 고유 결함, 회귀, 수정 비용을 추가로 측정할 수 있다. 이 지표들은 현재 역사 기록에서 측정한 값이 아니다.
