Sample provider responses used by `tests/test_llm_providers.py`.

They follow the documented response shapes of each API (chat completions for OpenAI-compatible servers, Messages for Anthropic) with synthetic content:
they are **samples, not live captures**. Add a file here when a provider returns something unexpected, then a test that feeds it to the adapter.
