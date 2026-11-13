# 요청별 사용량 계측

이 디렉터리는 B/C 실험에 동일하게 적용한 실제 계측 코드다. 일반 설치용 제품에는 적용하지 않는다.

- `audit-usage.ts`: 요청, 응답 usage, 도구 이름, 시간, 취소 여부를 JSONL에 기록한다. 인증 헤더나 요청, 응답 본문을 기록하지 않는다.
- `fetch-util.ts`: 원본에 observer를 연결한 전체 파일이다. B/C에서 바이트가 동일했다.
- `audit-meter.test.ts`: 응답 바이트 보존, usage 수집과 중복 처리 등을 검증한 테스트다.
- 실행 시 `AUDIT_USAGE_LOG`가 있어야 기록한다. 재현 runner가 컨테이너 안에서 지정한다.

`python3 benchmarks/prepare_instrumented.py --help`의 경로 옵션으로 원본과 개선판의 새 계측용 복사본을 만든다. 입력 checkout은 수정하지 않으며, 출력 경로가 이미 존재하면 거부한다. 출력은 두 입력 checkout 밖에 둔다. 생성된 각 복사본에서 의존성 설치와 빌드가 필요하다. 전체 명령은 [재현 절차](../REPRODUCE.md)에 있다.

입력은 개인 설정이나 인증 파일이 없는 새 clone을 사용한다. 이 스크립트는 Git 추적 여부로 파일을 선별하지 않으므로 untracked 파일도 복사할 수 있다. symlink는 대상을 읽지 않고 링크 자체로 복사한다. 계측 전 `fetch-util.ts`는 고정된 원본 SHA-256과 대조하며, 서로 다른 버전에 계측 파일을 덮어쓰지 않는다.

계측용 복사본을 일반 Codex/Claude 설치 대상으로 사용하지 않는다. 계측은 추가 관찰 비용이 있으며, A는 Codex OTLP, B/C는 provider 응답 observer로 집계했다는 측정 경계를 유지한다.
