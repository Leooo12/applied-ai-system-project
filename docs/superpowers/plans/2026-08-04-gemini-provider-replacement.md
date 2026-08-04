# Gemini Provider Replacement 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 VibeMatch 的 live AI provider 从 Anthropic-only 替换为 Gemini-only，同时保留现有的 AIClient 接口、确定性排名、guardrails、verifier、repair/fallback 和离线测试。

**架构：** `GeminiAIClient` 实现现有 `AIClient.generate(system_prompt, user_prompt)` 协议。`main.py` 只负责创建 provider；parser、orchestrator、explanation generator、verifier 和 FakeAIClient 的调用契约不变。密钥只从进程环境变量 `GEMINI_API_KEY` 读取。

**技术栈：** Python 3.10、Google `google-genai` SDK、pytest、现有 `AIClient` Protocol 和异常类型。

---

## 文件结构和职责

- 修改 `src/ai_client.py`：移除 Anthropic client，添加 Gemini client；保留错误类型、Protocol、FakeAIClient。
- 修改 `src/main.py`：构造 Gemini client，更新缺少密钥的提示。
- 修改 `requirements.txt`、`.env.example`：切换依赖和变量文档。
- 修改 `tests/test_ai_client.py`、`tests/test_main_interactive.py`：覆盖 Gemini 配置和 CLI setup path，全部离线。
- 修改 `README.md`：更新 provider、安装和环境变量说明。
- 已创建并提交设计规格：`docs/superpowers/specs/2026-08-04-gemini-provider-replacement-design.md`。

## 任务 1：TDD 红灯——Gemini client contract

**文件：** `tests/test_ai_client.py`

- [ ] **步骤 1：编写失败测试。** 将 Anthropic-specific tests 替换为以下行为：

```python
def test_gemini_client_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError):
        GeminiAIClient()


def test_gemini_client_returns_sdk_text():
    client = GeminiAIClient(api_key="test-key", model="test-model")
    client._client = fake_sdk_client_with_text("OK")
    assert client.generate("system", "user") == "OK"


def test_gemini_client_maps_transient_sdk_error():
    client = GeminiAIClient(api_key="test-key", model="test-model")
    client._client = fake_sdk_client_that_times_out()
    with pytest.raises(TemporaryAIServiceError):
        client.generate("system", "user")
```

Use deterministic local SDK doubles; do not call the network or include a real key.

- [ ] **步骤 2：验证红灯：** `python -m pytest tests/test_ai_client.py -v`。
  Expected: the new Gemini tests fail because `GeminiAIClient` does not exist.
- [ ] **步骤 3：Commit：** `git add tests/test_ai_client.py && git commit -m "Test Gemini client contract"`。

## 任务 2：实现 Gemini provider boundary

**文件：** `src/ai_client.py`, `tests/test_ai_client.py`

- [ ] **步骤 1：** 保留 `AIClientError`、`MissingAPIKeyError`、
  `InvalidAIResponseError`、`TemporaryAIServiceError`、`AIClient` 和
  `FakeAIClient`；删除 `AnthropicAIClient`、`ANTHROPIC_API_KEY` 和 Anthropic imports。
- [ ] **步骤 2：** 添加以下配置和 client shape，使用 SDK 的具体异常类型完成最后的错误分类：

```python
GEMINI_API_KEY_ENV_VAR = "GEMINI_API_KEY"
GEMINI_MODEL_ENV_VAR = "GEMINI_MODEL"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

class GeminiAIClient:
    def __init__(self, api_key=None, model=None, max_tokens=None):
        api_key = api_key or os.environ.get(GEMINI_API_KEY_ENV_VAR)
        if not api_key:
            raise MissingAPIKeyError("Set GEMINI_API_KEY before interactive mode.")
        self._model = model or os.environ.get(
            GEMINI_MODEL_ENV_VAR, DEFAULT_GEMINI_MODEL
        )
        self._max_tokens = max_tokens or int(
            os.environ.get(MAX_TOKENS_ENV_VAR, DEFAULT_MAX_TOKENS)
        )
        from google import genai
        self._client = genai.Client(api_key=api_key)

    def generate(self, system_prompt, user_prompt):
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config={"system_instruction": system_prompt,
                    "max_output_tokens": self._max_tokens},
        )
        text = getattr(response, "text", "") or ""
        if not text.strip():
            raise InvalidAIResponseError("The Gemini model returned no text.")
        return text
```

Import `from google.genai import errors` and map the documented `errors.APIError`
as follows: code `429` or codes `500` and above become
`TemporaryAIServiceError`; other API errors become `InvalidAIResponseError`.
Catch SDK connection/timeout errors as `TemporaryAIServiceError`, sanitize the
message with `safe_error_message`, and do not add a new retry loop.

- [ ] **步骤 3：验证绿灯：** `python -m pytest tests/test_ai_client.py -v`。
- [ ] **步骤 4：Commit：** `git add src/ai_client.py tests/test_ai_client.py && git commit -m "Replace Anthropic client with Gemini client"`。

## 任务 3：Wire CLI and configuration

**文件：** `src/main.py`, `requirements.txt`, `.env.example`,
`tests/test_main_interactive.py`

- [ ] **步骤 1：** Replace lazy `AnthropicAIClient` construction with
  `GeminiAIClient`; missing-key output must mention `GEMINI_API_KEY` and never
  print its value.
- [ ] **步骤 2：** Replace `anthropic` with `google-genai` in requirements;
  preserve `pytest` and `tabulate`.
- [ ] **步骤 3：** Make `.env.example` contain only placeholders for:

```text
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-2.5-flash
VIBEMATCH_MAX_TOKENS=1024
VIBEMATCH_LOG_LEVEL=INFO
```

- [ ] **步骤 4：** Update missing-key assertions and run
  `python -m pytest tests/test_ai_client.py tests/test_main_interactive.py -v`.
- [ ] **步骤 5：** Commit with
  `git add src/main.py requirements.txt .env.example tests/test_main_interactive.py && git commit -m "Wire interactive mode to Gemini"`。

## 任务 4：Update documentation

**文件：** `README.md`

- [ ] **步骤 1：** Document `GEMINI_API_KEY`, `GEMINI_MODEL`,
  `google-genai`, process-local setup, and the fact that no key belongs in Git.
- [ ] **步骤 2：** Preserve existing architecture, reliability, guardrail, and
  limitation sections; do not claim a live Gemini result without a real local run.
- [ ] **步骤 3：** Verify stale provider references with:
  `rg -n "Anthropic|ANTHROPIC_API_KEY|anthropic" src tests README.md .env.example requirements.txt`.
  Expected: no active references.
- [ ] **步骤 4：** Commit with
  `git add README.md && git commit -m "Document Gemini setup for VibeMatch"`。

## 任务 5：Full verification and optional live smoke test

**文件：** no source changes unless a concrete failure identifies one.

- [ ] **步骤 1：** Run `python -m pytest -v`; expected: all tests pass without a key or network.
- [ ] **步骤 2：** Run `python -m src.evaluator`; expected: 12/12 cases pass using FakeAIClient.
- [ ] **步骤 3：** Run `python -m src.main`; expected: 36-song deterministic output without a key.
- [ ] **步骤 4：** Only if the user chooses a live test, they run locally:

```bash
export GEMINI_API_KEY="your-key"
python -m src.main --interactive
```

Never record the key or commit live secrets.

- [ ] **步骤 5：** Run `git diff --check`, `git status --short --branch`,
  `git rev-list --left-right --count origin/main...main`, then
  `git push origin main`; expected final sync is `0 0`.
