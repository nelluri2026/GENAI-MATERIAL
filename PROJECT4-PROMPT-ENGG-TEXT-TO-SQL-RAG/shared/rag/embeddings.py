from openai import OpenAI

from shared.rag.secrets import get_config_value


class OpenAIEmbeddingClient:
    def __init__(self) -> None:
        self.model = get_config_value("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.client = OpenAI(api_key=get_config_value("OPENAI_API_KEY"))

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]

