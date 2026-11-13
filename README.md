# billion-context-enhanced

billion-context 원본에 무효 압축 처리와 압축 가능 여부 표시를 개선한 C 구현체다. 아래는 실제 Codex 구독으로 실행한 A/B/C 한 번씩의 관측 결과다. A/B는 2026-11-06, C는 2026-11-13에 실행했다. 실행 날짜와 모델의 작업 전략이 달라 인과적인 성능 개선으로 해석하지 않는다.

| 항목                      | A: 기본 Codex                                   | B: 원본                                         | C: 개선판                                       |
| ------------------------- | ----------------------------------------------- | ----------------------------------------------- | ----------------------------------------------- |
| 최종 구현체               | [A 코드](benchmarks/candidates/A)               | [B 코드](benchmarks/candidates/B)               | [C 코드](benchmarks/candidates/C)               |
| 생성한 분석 결과          | [A JSON](benchmarks/candidates/A/analysis.json) | [B JSON](benchmarks/candidates/B/analysis.json) | [C JSON](benchmarks/candidates/C/analysis.json) |
| 숨김 기능 검사            | 13/13                                           | 13/13                                           | 13/13                                           |
| 도구 없는 정보 회상       | 48/48                                           | 48/48                                           | 48/48                                           |
| 정정된 정보 반영          | 8/8                                             | 8/8                                             | 8/8                                             |
| 전체 경과시간             | 33분 34초                                       | 40분 36초                                       | 24분 58초                                       |
| 입력 토큰, cache 포함     | 18,827,367                                      | 13,798,776                                      | 11,864,729                                      |
| cached input              | 18,147,328                                      | 12,943,488                                      | 10,893,952                                      |
| uncached input            | 680,039                                         | 855,288                                         | 970,777                                         |
| 출력 토큰, reasoning 포함 | 123,555                                         | 118,764                                         | 92,889                                          |
| Standard API 환산 USD     | 42.163399                                       | 27.434568                                       | 25.246172                                       |
| 성공한 압축 호출          | 해당 없음                                       | 5                                               | 3                                               |
| 무효 압축                 | 해당 없음                                       | 7                                               | 4                                               |

비용은 **실제 구독 청구액이 아니다.** 2026-11-13에 확인한 GPT-6 Astra 공개 Standard API 요율을 요청별 usage에 적용했다. cached input, cache write, reasoning의 중복 합산을 피하고, 입력 272,000 토큰 초과 요청 전체에 input/cache 2배, output 1.5배를 적용했다. B의 취소 요청 12개와 C의 15개는 usage가 없어 미상이다. [원시 비교 수치](benchmarks/results/comparison-ABC.json), [비용 집계](benchmarks/results/cost-estimate.json), [계산식과 한계](docs/benchmark-results.md).

## 포함된 개선

기준은 [upstream 커밋 be611a8](https://github.com/ranxianglei/billion-context/tree/be611a8566c22ee0a65fb5765365671d47e810d5)이다. 일반 설치용 소스에는 벤치마크 계측을 넣지 않았다.

- 메시지별 상태 표시에도 기존 압축 가능 여부 검사를 적용한다. 보호 구간, 미해결 참조, 턴 분할 등의 이유를 표시한다.
- 압축 결과가 정확히 no-op이면 바뀌지 않은 압축 상태를 다시 생성하지 않는다.
- streaming Responses에서 조건에 맞는 no-op 전용 라운드는 클라이언트에 보이는 결과 알림으로 이어간다. 작업 자체를 강제로 중단하지 않는다.

압축 알고리즘, 기본 임계값, 보호 규칙을 교체한 버전은 아니다. C 실행에서는 새 no-op 처리 경로가 4회 사용됐고, 새 메시지별 상태 표시 경로는 사용되지 않았다. 다른 프로토콜에도 같은 효과가 있다고 주장하지 않는다. [실제 제품 변경 diff](benchmarks/historical/product-c.patch).

## 설치

Node.js 22 또는 24, npm, Git이 필요하다. Codex 또는 Claude Code CLI는 먼저 설치하고 본인 계정으로 로그인한다. [Codex 공식 안내](https://developers.openai.com/codex/cli/), [Claude Code 공식 안내](https://code.claude.com/docs/en/quickstart).

현재 배포 경로는 이 저장소의 소스 빌드다. npm 공개 패키지 `billion-context`를 설치하면 원본을 받는다.

```bash
git clone https://github.com/tot0rokr/billion-context-enhanced.git
cd billion-context-enhanced
npm ci --ignore-scripts --no-fund --no-audit
npm run build
npm install -g . --install-links --prefix "$HOME/.local/opt/billion-context-enhanced"
```

`--install-links`는 소스 디렉터리에 대한 symlink 대신 설치용 복사본을 만든다. npm package 이름, 표시 버전은 원본과 같은 `billion-context@0.1.212`를 유지하므로, 개선판은 저장소 URL과 Git 커밋으로 구별한다. kernel 버전은 `0.0.183`이다.

작업할 프로젝트 디렉터리에서 Codex를 실행한다.

```bash
ACP_AUTO_UPDATE=0 \
BILI_ADVISORY_CHECK=0 \
BILI_AUTO_MODE_FORGE=0 \
"$HOME/.local/opt/billion-context-enhanced/bin/bili" codex
```

Claude Code도 같은 설치본의 launcher를 사용한다.

```bash
ACP_AUTO_UPDATE=0 \
BILI_ADVISORY_CHECK=0 \
BILI_AUTO_MODE_FORGE=0 \
"$HOME/.local/opt/billion-context-enhanced/bin/bili" claude
```

- 두 업데이트 변수는 원본 npm 버전이 개선판을 덮어쓰는 자동 경로를 끈다. `bili update` 대신 이 저장소의 변경을 검토하고 다시 빌드, 설치한다.
- `BILI_AUTO_MODE_FORGE=0`은 Claude 안전 분류 응답을 로컬 allow로 대체하는 원본 기본 동작을 끈다.
- Codex launcher는 구독 인증을 사용한 실험에서 검증했다. Claude 설치, 라우팅 설명은 소스와 mock 테스트를 근거로 하며, Claude 구독 OAuth E2E와 성능 비교는 측정하지 않았다.
- `bili plugin install codex`만으로는 모델 트래픽이 프록시를 지나지 않는다. 위 launcher 방식을 사용한다.
- 실행하면 세션 원본, 요약, 로그, CA와 Codex overlay가 저장된다. 별도 npm 설치 경로가 로그인, 대화 상태까지 완전히 격리하는 것은 아니다.

패키지 보관, 실제 변경 경로와 업데이트 방식은 [설치 상세](docs/installation.md)에 있다.

## 결과 검증과 실험 재현

API 호출 없이 게시된 데이터의 해시, 토큰 합계, 비용, 기억 검사와 과정 지표를 다시 확인한다.

```bash
python3 benchmarks/recompute.py
```

저장된 A/B/C 구현체를 네트워크 없는 Docker에서 다시 채점한다. 이 명령은 모델을 호출하지 않는다.

```bash
docker pull python:3.12-slim
python3 benchmarks/recompute.py --grade-code
```

새 Codex 실행으로 동일 과제를 수행하려면 [재현 명령](benchmarks/REPRODUCE.md)을 따른다. `plan`과 `preflight`는 모델을 호출하지 않으며, `run`은 본인의 모델 사용량을 소비한다. 각 arm은 최대 60분이며 세 arm 전체는 최대 180분이다. 모델, CLI 버전을 임의로 대체하지 않는다.

- [방법론](docs/benchmark-methodology.md): 8단계, Docker, 모델 조건, 계측, 외부 채점과 정보 보존 검사.
- [결과와 평가](docs/benchmark-results.md): 정확한 수치, 가격 공식, 과정 지표와 평가 한계.
- [실제 프롬프트](benchmarks/dataset-v2/prompts), [입력, 정답 manifest](benchmarks/dataset-v2/manifest.json).
- [당시 실행 코드](benchmarks/historical), [재현용 runner](benchmarks/reproduce.py), [채점기](benchmarks/grade.py).
- [원본 대비 출처, 해시 기록](benchmarks/artifact-manifest.json), [요청별 usage](benchmarks/results), [제품 회귀 검사 기록](benchmarks/results/product-validation).

조건별 1회, 공개된 고정 과제의 결과다. 첫 제출 성공률, 고유 결함 수, 수정 비용은 측정하지 않았다. 자체 테스트 수는 A/B/C가 서로 다른 테스트를 작성한 결과라 품질 순위가 아니다. 48개 회상은 모두 정답이어서 검색, 복원 단계의 추가 효과를 구별하지 못했다. 장기간 다단계 재압축, 임의의 세부 정보 보존, Claude 성능은 검증 범위 밖이다.

## 원본과 출처

이 프로젝트는 [billion-context](https://github.com/ranxianglei/billion-context)와 [acp-kernel](https://github.com/ranxianglei/acp-kernel)을 사용한다. 원본 작성자는 ranxianglei이며, 저작권, 추가 출처 표시 조건을 포함한 [LICENSE](LICENSE)를 유지한다. 원본 기능 안내는 [README.upstream.md](README.upstream.md), 설정 목록은 [CONFIGURATION.md](CONFIGURATION.md)에 있다. 원본 문서의 npm 설치, 자동 업데이트, 배포 안내는 원본 프로젝트 기준이다.

상속된 GitHub Actions에는 npm 게시, 예약 실행, issue 쓰기가 포함돼 있다. 초기 저장소에서는 Actions를 비활성화하고, enhanced 전용 작업으로 검토, 조정한 뒤 활성화한다.
