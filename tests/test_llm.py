from backend.dcif.llm import LLMSettings


def test_responses_url_accepts_base_endpoint() -> None:
    settings = LLMSettings(
        azure_endpoint="https://example.openai.azure.com",
        azure_model="deployment",
    )

    assert settings.responses_url == "https://example.openai.azure.com/openai/v1/responses"


def test_responses_url_accepts_full_responses_endpoint() -> None:
    settings = LLMSettings(
        azure_endpoint="https://example.openai.azure.com/openai/v1/responses",
        azure_model="deployment",
    )

    assert settings.responses_url == "https://example.openai.azure.com/openai/v1/responses"
