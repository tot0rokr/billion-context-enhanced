# 벤치마크 재현

`reproduce.py`는 게시된 8단계 과제를 새 A/B/C 실행에 적용한다. 역사적 실행 코드는 `historical/`에 보존한다. 이 파일은 경로 매개변수, 컨테이너 종료 제한, 인증정보 분리를 추가한 재현용 runner이며 당시 실행 파일과 동일한 파일이라고 주장하지 않는다. 아래 명령은 저장소 루트에서 실행한다.

## 준비 조건

- Linux, Python 3.11 이상, Docker Engine.
- Docker 안에서 실행할 수 있는 Codex CLI `0.163.0`의 Linux native executable. npm의 `bin/codex.js` 대신 플랫폼 패키지의 `vendor/<platform>/bin/codex`를 사용한다. `--codex-vendor`에는 `bin/codex`가 들어 있는 디렉터리를 지정한다.
- 본인 계정으로 로그인해 만든 Codex `auth.json`. 인증 파일을 저장소에 복사하거나 커밋하지 않는다.
- 기본 모델은 `gpt-6-astra`, reasoning은 `xhigh`다. 해당 모델 접근 권한은 실제 `run`에서 확인된다. 접근 불가 시 다른 모델로 자동 변경하지 않는다.
- B/C를 실행하려면 동일한 benchmark observer를 적용하고 빌드한 소스 디렉터리 두 개가 필요하다. 일반 설치용 C와 계측용 C는 구분한다.

원본 B의 기준 커밋은 `be611a8566c22ee0a65fb5765365671d47e810d5`다. [계측 설명](instrumentation/README.md)에 따라 B/C에 같은 observer를 적용한 새 디렉터리를 준비한다. `prepare_instrumented.py`는 입력 소스를 수정하지 않고 새 B/C 복사본을 생성하며, 기존 출력 디렉터리를 덮어쓰지 않는다.

```bash
git clone https://github.com/ranxianglei/billion-context.git "$HOME/bili-benchmark-original"
git -C "$HOME/bili-benchmark-original" switch --detach be611a8566c22ee0a65fb5765365671d47e810d5

python3 benchmarks/prepare_instrumented.py \
  --baseline-source "$HOME/bili-benchmark-original" \
  --enhanced-source "$PWD" \
  --output "$HOME/bili-instrumented"

npm --prefix "$HOME/bili-instrumented/B" ci --ignore-scripts --no-fund --no-audit
npm --prefix "$HOME/bili-instrumented/B" run build
npm --prefix "$HOME/bili-instrumented/C" ci --ignore-scripts --no-fund --no-audit
npm --prefix "$HOME/bili-instrumented/C" run build
```

runner는 두 소스의 계측 파일 SHA-256 일치와 빌드 결과의 `AUDIT_USAGE_LOG` 포함 여부를 검사한다. 일반 사용자 설치본에 이 계측을 적용할 필요는 없으며, 이 계측용 디렉터리를 일반 설치 대상으로 사용하지 않는다.

역사적 container image를 먼저 준비한다. 자동으로 최신 image로 바꾸지 않는다.

```bash
docker pull node@sha256:18a6d90fd60542269850c80ca03b29b1d9b14d6b221ac7ee8e35b0d33ef904bd
```

## 입력 검증

게시된 `dataset-v2/`는 당시 입력이다. 기본적으로 이를 그대로 사용하고 manifest에 있는 모든 파일의 해시를 검사한다. fixture를 다시 생성하려면 별도 새 디렉터리를 사용한다.

```bash
python3 benchmarks/fixture.py selftest
python3 benchmarks/fixture.py generate \
  --root /tmp/bili-fixture-recreated \
  --seed 20261106 \
  --batch-chars 175000
```

아래 예시의 `/path/to/...` 경로를 자신의 경로로 바꾼다. 모든 arm에 같은 CLI, 모델, image, 입력을 적용한다. `--output`은 아직 존재하지 않는 디렉터리여야 한다.

## 모델 호출 없는 확인

`plan`은 로컬 파일, 해시, 계측 일치 여부만 검사한다. `preflight`는 추가로 Docker와 image를 확인하고, 네트워크 없는 컨테이너에서 Codex, Python 버전만 조회한다. 두 모드 모두 모델 요청을 보내지 않고 실행 결과 디렉터리를 만들지 않는다.

```bash
python3 benchmarks/reproduce.py plan \
  --output "$HOME/bili-benchmark-runs/trial-01" \
  --codex-vendor /path/to/vendor/x86_64-unknown-linux-musl \
  --auth-file "$HOME/.codex/auth.json" \
  --baseline-source "$HOME/bili-instrumented/B" \
  --enhanced-source "$HOME/bili-instrumented/C" \
  --order A,B,C \
  --minutes 60
```

같은 명령의 `plan`을 `preflight`로 바꾸면 실행 환경까지 검사한다. `--codex-binary /path/to/native/codex`로 단일 native executable을 지정할 수도 있지만, 부속 실행 파일도 함께 제공하는 `--codex-vendor`를 우선 사용한다.

## 실제 실행

`run`만 실제 모델 요청을 보낸다. 본인의 구독 사용량이나 API 사용량이 소비된다. 60분은 arm별 상한이며 A/B/C 전체 상한은 최대 180분이다. 완료된 arm은 즉시 끝나고, 실패한 arm 뒤의 실행은 시작하지 않는다.

```bash
python3 benchmarks/reproduce.py run \
  --output "$HOME/bili-benchmark-runs/trial-01" \
  --codex-vendor /path/to/vendor/x86_64-unknown-linux-musl \
  --auth-file "$HOME/.codex/auth.json" \
  --baseline-source "$HOME/bili-instrumented/B" \
  --enhanced-source "$HOME/bili-instrumented/C" \
  --order A,B,C \
  --minutes 60
```

A만 실행할 때는 `--order A`로 지정하고 두 source 인자를 생략할 수 있다. C만 실행할 때는 `--order C`와 `--enhanced-source`를 지정한다. `--model`이나 `--expected-codex-version`, `--image`를 바꾸면 다른 조건의 실험이다. manifest에 실제 설정이 기록되므로 역사적 결과와 구별해서 보고한다.

실행 조건은 다음과 같다.

- arm별 새 컨테이너, CPU 4개, 메모리 8GB, PID 768 제한, non-root UID, capability 제거.
- 과제 디렉터리와 audit 출력만 해당 실행의 저장 위치에 연결한다. 소스와 Codex vendor는 읽기 전용이다.
- 인증정보와 CA를 포함하는 runtime HOME은 결과 디렉터리 밖의 전용 임시 디렉터리에 둔다. 실행이 종료되면 이 runner가 만든 임시 HOME만 제거한다. 사용자의 원래 인증 파일은 수정하지 않는다.
- 8개 프롬프트를 같은 thread에 순서대로 전달한다. 8단계 직전까지 `evidence/02.txt`, `03.txt`, `04.txt` 원문 파일을 공개하지 않는다. 숨김 정답인 `oracle/`는 작업 컨테이너에 연결하지 않는다.
- Codex `exec` 프로세스 밖의 watchdog이 실제 컨테이너 ID를 감시하고 기한에 컨테이너를 종료한다. 개별 phase timeout도 컨테이너를 종료한다.
- 원본과 동일하게 자동 업데이트, advisory, auto-mode forge를 끄고 context 설정을 고정한다. C 기능 자체를 더 수정하지 않는다.

## 결과 채점

완료 여부는 `trial-01/<arm>/result.json`의 `completed`, 시간 제한 결과는 `watchdog.json`에서 확인한다. 중단, 기한 초과 실행을 정상 완료 실행과 섞어 시간 순위를 만들지 않는다.

기능 검사는 모델을 호출하지 않는다. 기본 채점 image `python:3.12-slim`을 준비한 뒤 arm별로 실행한다.

```bash
docker pull python:3.12-slim

python3 benchmarks/grade.py \
  --root benchmarks/dataset-v2 \
  --candidate "$HOME/bili-benchmark-runs/trial-01/A/candidate" \
  --phase final \
  --output "$HOME/bili-benchmark-runs/trial-01/A/code-grade.json"

python3 benchmarks/grade.py \
  --root benchmarks/dataset-v2 \
  --phase memory \
  --answers "$HOME/bili-benchmark-runs/trial-01/A/audit/final-06.txt" \
  --output "$HOME/bili-benchmark-runs/trial-01/A/memory-grade.json"

python3 benchmarks/analyze.py \
  "$HOME/bili-benchmark-runs/trial-01/A" \
  --output "$HOME/bili-benchmark-runs/trial-01/A/metrics.json"
```

B/C는 경로의 arm 이름만 바꾼다. 7단계와 8단계는 `--phase retrieval`, 각각 `final-07.txt`와 `final-08.txt`를 사용해 `engine-recovery-grade.json`, `file-recovery-grade.json`으로 채점한다. 6단계의 도구 미사용 여부는 정답 채점만으로 입증되지 않으므로 `metrics.json`의 `phase6_tools`, `phase6_otel_tools`, `phase6_proxy_tools`가 모두 비어 있는지도 확인한다.

A는 `otel_totals`, B/C는 `provider_totals`가 주 토큰 집계다. 두 집계를 더하면 같은 요청을 중복 계산한다. B/C의 내부 압축 호출은 provider 집계에 이미 포함된다. 취소된 요청의 usage가 없으면 미상이며 0으로 취급하지 않는다. cached input과 reasoning output은 각각 전체 input과 output의 부분집합이다.

## 보관 범위와 한계

runtime HOME 중 `.codex/sessions/`, billion-context의 `sessions/`, `bili.log`만 분석을 위해 내보낸다. `auth.json`, CA key와 runtime 설정은 내보내지 않는다. OTLP에서 `user.account_id`와 `user.email`을 제거하며, 원본 로그 해시와 제외된 malformed 행 번호는 `audit/telemetry-redaction.json`에 기록한다.

이 자동 처리는 공개 게시를 위한 전체 개인정보 검사가 아니다. 실행 로그에는 모델 대화, 명령, 파일 경로가 남으므로 공개 전에 별도 검토한다. 모델의 행동, 서버 지연, cache 상태는 고정하지 못하므로 같은 입력으로 실행해도 시간, 토큰, 생성 코드는 달라진다. 최초 제출 성공률, 고유 결함 수, 수정 비용은 이 역사적 설계에서 측정하지 않았다.

## runner 검증

```bash
python3 -m unittest discover -s benchmarks -p test_reproduce.py -v
```

오프라인 테스트는 subprocess만 대체하여 명령 구성, 버전, 입력 불일치 거부, 컨테이너 기한 초과 종료, collector 실패 정리, 8단계 resume, 원문 공개 시점, 인증정보 제외를 검사한다. 이 테스트 통과는 새 유료 A/B/C 실행의 성공을 뜻하지 않는다.
