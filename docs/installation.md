# Codex와 Claude Code 설치

이 저장소는 [billion-context](https://github.com/ranxianglei/billion-context)와 [acp-kernel](https://github.com/ranxianglei/acp-kernel)을 사용하며 원본 [LICENSE](../LICENSE)를 포함한다. 개선판은 source에서 빌드하거나 이 저장소가 제공한 빌드 패키지로 설치한다. npm의 공개 `billion-context`를 설치하면 이 저장소의 수정본을 받는 것이 아니다.

## 준비

- Git, npm, Node.js를 준비한다. package 요구사항은 Node ≥20이며, 이 작업의 검증 환경은 Node 22/24다.
- 사용할 Codex CLI 또는 Claude Code를 먼저 설치하고 로그인한다. [Codex CLI 공식 문서](https://developers.openai.com/codex/cli/), [Claude Code 공식 문서](https://code.claude.com/docs/en/quickstart)를 따른다.
- 실제 비교에 사용한 Codex 버전은 `0.163.0`이다. 다른 버전의 호환성, 성능을 같은 결과로 간주하지 않는다.
- 개선판 저장소는 `https://github.com/tot0rokr/billion-context-enhanced`다.

```bash
node --version
npm --version
codex --version
claude --version
```

둘 중 사용할 클라이언트만 있으면 된다. billion-context가 클라이언트 구독이나 모델 사용권을 제공하지는 않는다.

## 소스에서 설치

```bash
git clone https://github.com/tot0rokr/billion-context-enhanced.git
cd billion-context-enhanced
npm ci --ignore-scripts --no-fund --no-audit
npm run build
npm install -g . --install-links --prefix "$HOME/.local/opt/billion-context-enhanced"
```

`npm run build`는 kernel, pi-subagents, root bundle을 순서대로 빌드한다. `dist/`는 Git에 포함되지 않는다. `prepare`는 빌드 결과 유무를 검사하므로 Git URL을 바로 `npm install`에 넘기는 방식으로 대체하지 않는다.

`--install-links`는 설치본을 source worktree에 대한 symlink로 남기지 않기 위한 옵션이다. 사용자 전용 prefix를 사용하므로 `sudo`는 필요하지 않다. npm package 이름과 CLI 이름은 각각 `billion-context`, `bili`로 유지된다. 저장소 이름이 `billion-context-enhanced`라고 해서 npm에 같은 이름의 패키지가 게시됐다는 뜻은 아니다.

빌드 결과를 배포용 파일로 보관하려면 다음 명령을 사용한다.

```bash
mkdir -p "$HOME/.local/share/billion-context-enhanced/packages"
npm pack --pack-destination "$HOME/.local/share/billion-context-enhanced/packages"
```

출력된 `.tgz`를 설치할 때는 위의 source 디렉터리 대신 그 파일 경로를 `npm install -g --prefix ...`에 전달한다. GitHub Release에 패키지가 제공되면 해당 Release의 정확한 파일과 checksum을 사용한다. Source archive와 빌드된 npm tarball은 다르다. package 버전이 원본과 같을 수 있으므로 commit/tag와 checksum도 기록한다.

## Codex 실행

작업할 프로젝트 디렉터리에서 실행한다.

```bash
ACP_AUTO_UPDATE=0 \
BILI_ADVISORY_CHECK=0 \
BILI_AUTO_MODE_FORGE=0 \
"$HOME/.local/opt/billion-context-enhanced/bin/bili" codex
```

Codex launcher는 모델 요청에 proxy와 CA 환경을 적용하고 native MCP 도구를 연결한다. 지원하는 Codex에는 `--no-daemon`을 추가해 세션 proxy보다 오래 살아 있는 shared daemon을 통한 우회를 막는다. Codex 로그인 정보를 사용하며, 이 프로젝트의 A/B/C 비교는 실제 구독 인증으로 수행했다.

`bili plugin install codex`만 실행하면 MCP 도구 등록과 모델 트래픽 라우팅을 혼동하게 된다. MCP 등록만으로 부모 Codex의 모델 요청이 proxy를 통과하지 않는다. 위 launcher 방식을 사용한다. `BILI_LAUNCHER_DIRECT=1`은 Codex 모델 압축 경로를 우회하므로 이 안내에서는 사용하지 않는다.

## Claude Code 실행

```bash
ACP_AUTO_UPDATE=0 \
BILI_ADVISORY_CHECK=0 \
BILI_AUTO_MODE_FORGE=0 \
"$HOME/.local/opt/billion-context-enhanced/bin/bili" claude
```

현재 Claude launcher는 `ANTHROPIC_BASE_URL`을 로컬 proxy의 `/bili/` URL로 연결한다. 사용자 지정 upstream도 발견한 경로에 따라 연결하며, Vertex 설정은 별도 base URL을 처리한다. 일부 원본 문서의 “Claude 기본 MITM” 설명보다 [현재 라우팅 코드](../src/launcher.ts)를 기준으로 판단한다.

`BILI_AUTO_MODE_FORGE=0`은 원본의 auto-mode 안전 분류 호출을 로컬 allow 응답으로 대체하는 기능을 끈다. 실제 분류 요청을 upstream에 전달하는 동작을 사용한다. 이 값은 자동 업데이트 설정과 별개다.

Claude 설치 안내는 소스와 로컬 protocol, launcher 테스트에 근거한다. 이 저장소의 성능, 비용 비교는 Codex만 대상으로 했으며, 실제 Claude 구독 인증의 E2E와 Claude A/B/C 성능은 확인하지 않았다. Claude Desktop의 Code 탭은 터미널 CLI와 같은 경로라고 가정하지 않는다.

## 업데이트와 실행 데이터

두 launcher 예시의 환경변수는 실행할 때마다 붙여야 한다. 자주 사용한다면 같은 변수를 설정하는 별도 wrapper를 만든다.

- `ACP_AUTO_UPDATE=0`: 일반 자동 업데이트 확인을 끈다.
- `BILI_ADVISORY_CHECK=0`: 일반 업데이트와 독립적으로 동작하는 결함 공지 기반 강제 설치를 끈다.
- `BILI_RELEASE_NOTES_CHECK=0`: 선택적으로 release notes 확인을 끈다. 이 설정만으로 모든 공지 네트워크 기능이 꺼지는 것은 아니다.

수정본의 업데이트는 이 저장소의 검토한 tag/commit을 받아 다시 빌드, 설치하는 방식으로 관리한다. 원본 패키지를 설치할 수 있는 `bili update`를 수정본 업데이트 명령으로 사용하지 않는다. 자동 업데이트를 끄면 upstream의 수정, 보안 업데이트 반영도 직접 관리해야 한다.

실행하면 기본적으로 다음 위치에 데이터가 생성된다. `XDG_*`, `BILI_CONFIG_FILE`, `BILI_SESSIONS_DIR`를 설정한 환경에서는 위치가 달라질 수 있다.

| 데이터          | 기본 위치                                        |
| --------------- | ------------------------------------------------ |
| 설정            | `~/.config/billion-context/billion-context.json` |
| 압축 원본, 세션 | `~/.local/share/billion-context/sessions/`       |
| 상태, 로그      | `~/.local/state/billion-context/`                |
| cache           | `~/.cache/billion-context/`                      |
| 로컬 CA         | `~/.local/share/billion-context/ca/`             |

Codex는 실행용 overlay를 만들고 지원 버전에서 실제 HOME의 SQLite 상태를 공유한다. 별도 npm prefix는 프로그램 설치 위치를 분리할 뿐 로그인, 세션까지 완전히 분리하지 않는다. 압축 원문 보관소는 복원에 사용되므로 단순 cache로 취급해 지우지 않는다.

## 설치 결과 확인

```bash
"$HOME/.local/opt/billion-context-enhanced/bin/bili" --version
```

version 출력만으로 압축이 실제 발생했다는 결론을 내리지 않는다. launcher 시작 시 proxy 연결과 도구 주입 상태를 확인하고, 모델 요청이 전달되는지와 `acp_status`가 해당 세션을 보는지를 구분해 확인한다. 짧은 대화에서 압축이 발생하지 않는 것은 정상일 수 있다.

제품 개발용 source에는 다음 무과금 검증 경로가 있다. 실행자의 기존 설정에 테스트 데이터가 섞이지 않도록 repository의 test preload를 유지한다.

```bash
npm run check:dist-thin
```

이 검사는 scratch에 현재 tarball만 설치해 CLI와 agent bundle을 확인한다. 실제 모델의 정확도나 구독 연결을 검사하지 않는다. 실제 Codex와 로컬 fake upstream 검증, 과거 A/B/C 재실행은 [벤치마크 재현 문서](../benchmarks/REPRODUCE.md)에서 별도로 다룬다.
