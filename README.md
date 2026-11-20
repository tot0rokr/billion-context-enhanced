# billion-context-enhanced

[English](README.md) | [한국어](README.ko.md)

The C implementation in this repository improves no-op compression handling and foldability reporting in billion-context. The table below shows one A/B/C run each using an authenticated Codex subscription. A and B ran on 2026-11-06; C ran on 2026-11-13. Different run dates and model implementation strategies prevent a causal claim about performance gains.

| Metric                             | A: Native Codex                                 | B: Upstream                                     | C: Enhanced                                     |
| ---------------------------------- | ----------------------------------------------- | ----------------------------------------------- | ----------------------------------------------- |
| Final implementation               | [A code](benchmarks/candidates/A)               | [B code](benchmarks/candidates/B)               | [C code](benchmarks/candidates/C)               |
| Generated analysis                 | [A JSON](benchmarks/candidates/A/analysis.json) | [B JSON](benchmarks/candidates/B/analysis.json) | [C JSON](benchmarks/candidates/C/analysis.json) |
| Hidden functional checks           | 13/13                                           | 13/13                                           | 13/13                                           |
| Recall without tools               | 48/48                                           | 48/48                                           | 48/48                                           |
| Corrected facts retained           | 8/8                                             | 8/8                                             | 8/8                                             |
| Total elapsed time                 | 33m 34s                                         | 40m 36s                                         | 24m 58s                                         |
| Input tokens, including cache      | 18,827,367                                      | 13,798,776                                      | 11,864,729                                      |
| Cached input tokens                | 18,147,328                                      | 12,943,488                                      | 10,893,952                                      |
| Uncached input tokens              | 680,039                                         | 855,288                                         | 970,777                                         |
| Output tokens, including reasoning | 123,555                                         | 118,764                                         | 92,889                                          |
| Standard API equivalent, USD       | 42.163399                                       | 27.434568                                       | 25.246172                                       |
| Successful compression calls       | Not applicable                                  | 5                                               | 3                                               |
| No-op compressions                 | Not applicable                                  | 7                                               | 4                                               |

These costs are **not actual subscription charges.** Public GPT-6 Astra Standard API rates checked on 2026-11-13 were applied to each request's reported usage. Cached input, cache writes, and reasoning were not counted twice. Requests exceeding 272,000 input tokens received 2× input/cache rates and 1.5× output rates for the entire request. Usage remains unknown for 12 canceled requests in B and 15 in C. See the [recorded comparison](benchmarks/results/comparison-ABC.json), [cost calculations](benchmarks/results/cost-estimate.json), and [formula and limitations (Korean)](docs/benchmark-results.md).

## Improvements

The baseline is [upstream commit be611a8](https://github.com/ranxianglei/billion-context/tree/be611a8566c22ee0a65fb5765365671d47e810d5). The source used for normal installation does not include benchmark instrumentation.

- Apply the existing foldability checks to per-message status reports, including protected regions, unresolved references, and turn splits.
- Skip rebuilding unchanged folded state when a compression result is exactly a no-op.
- Continue eligible streaming Responses rounds containing only no-op compressions with a client-visible receipt, allowing normal work to proceed.

The compression algorithm, default thresholds, and protection rules remain unchanged. The C run exercised the new no-op handling path four times but did not use the new per-message status view. These results do not establish the same effect for other protocols. See the [product changes](benchmarks/historical/product-c.patch).

## Installation

Use Node.js 22 or 24, npm, and Git. Install the Codex or Claude Code CLI first and sign in with your own account. See the [official Codex instructions](https://developers.openai.com/codex/cli/) and [official Claude Code instructions](https://code.claude.com/docs/en/quickstart).

Install this fork from source. Installing the public npm package `billion-context` gives you the upstream version.

```bash
git clone https://github.com/tot0rokr/billion-context-enhanced.git
cd billion-context-enhanced
npm ci --ignore-scripts --no-fund --no-audit
npm run build
npm install -g . --install-links --prefix "$HOME/.local/opt/billion-context-enhanced"
```

`--install-links` installs a copy instead of symlinking the source directory. The npm package name and displayed version remain `billion-context@0.1.212`, matching upstream, so identify an enhanced build by its repository URL and Git commit. The kernel version is `0.0.183`.

Run Codex from the project directory where you want to work:

```bash
ACP_AUTO_UPDATE=0 \
BILI_ADVISORY_CHECK=0 \
BILI_AUTO_MODE_FORGE=0 \
"$HOME/.local/opt/billion-context-enhanced/bin/bili" codex
```

Use the same installation's launcher for Claude Code:

```bash
ACP_AUTO_UPDATE=0 \
BILI_ADVISORY_CHECK=0 \
BILI_AUTO_MODE_FORGE=0 \
"$HOME/.local/opt/billion-context-enhanced/bin/bili" claude
```

- The two update variables disable automatic paths that could overwrite this fork with the upstream npm package. Review changes in this repository, rebuild, and reinstall instead of running `bili update`.
- `BILI_AUTO_MODE_FORGE=0` disables upstream's default behavior of replacing Claude safety-classifier responses with a locally generated allow verdict.
- The Codex launcher was tested with subscription authentication. Claude installation and routing instructions are based on source inspection and mock tests; Claude subscription OAuth end-to-end behavior and comparative performance were not measured.
- `bili plugin install codex` alone does not route model traffic through the proxy. Use the launcher shown above.
- Running the launcher creates stored session originals, summaries, logs, CA material, and Codex overlays. A separate npm installation path does not fully isolate authentication or conversation state.

See the [detailed installation guide (Korean)](docs/installation.md) for package archival, affected paths, and updates.

## Verification and reproduction

Verify published artifact hashes, token totals, costs, recall scores, and process metrics without API calls:

```bash
python3 benchmarks/recompute.py
```

Regrade the saved A/B/C implementations in Docker containers with networking disabled. These commands do not call a model:

```bash
docker pull python:3.12-slim
python3 benchmarks/recompute.py --grade-code
```

To run the same task in new Codex sessions, follow the [reproduction instructions (Korean)](benchmarks/REPRODUCE.md). `plan` and `preflight` do not call a model; `run` consumes your model usage. Each arm has a 60-minute limit, for up to 180 minutes across all three. Do not silently substitute another model or CLI version.

- [Methodology (Korean)](docs/benchmark-methodology.md): eight phases, Docker and model settings, instrumentation, external grading, and information-preservation checks.
- [Results and evaluation (Korean)](docs/benchmark-results.md): exact measurements, pricing formula, process metrics, and limitations.
- [Actual prompts](benchmarks/dataset-v2/prompts) and [input and answer manifest](benchmarks/dataset-v2/manifest.json).
- [Historical execution code](benchmarks/historical), [portable runner](benchmarks/reproduce.py), and [grader](benchmarks/grade.py).
- [Provenance and hashes](benchmarks/artifact-manifest.json), [per-request usage](benchmarks/results), and [product regression records](benchmarks/results/product-validation).

These are single runs of a published, fixed task. First-submission success rates, unique defect counts, and repair costs were not measured. The A/B/C implementations have different self-authored test suites, so their test counts are not a quality ranking. All 48 recall answers were correct before retrieval, preventing a measurement of the added benefit of search or recovery. Long-term compression across multiple tiers, preservation of arbitrary details, and Claude performance remain outside the validation scope.

## Upstream and attribution

This project uses [billion-context](https://github.com/ranxianglei/billion-context) and [acp-kernel](https://github.com/ranxianglei/acp-kernel), originally authored by ranxianglei. The [LICENSE](LICENSE), including its copyright notice and additional attribution terms, is preserved. See [README.upstream.md](README.upstream.md) for the original feature guide and [CONFIGURATION.md](CONFIGURATION.md) for configuration options. Installation, automatic update, and release instructions in upstream documentation refer to the upstream project.

Inherited GitHub Actions include npm publishing, scheduled jobs, and issue writes. Actions are disabled for the initial repository setup; review and adapt them for this fork before enabling them.
