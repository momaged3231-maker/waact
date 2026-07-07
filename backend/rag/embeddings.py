import tiktoken
from config import config


def get_embedding_model():
    try:
        from openai import OpenAI
        api_key = config.OPENAI_API_KEY
        try:
            from ai.providers import ai_provider_manager
            if not ai_provider_manager.has_real_key(api_key):
                settings = ai_provider_manager.load_settings()
                api_key = settings.get("providers", {}).get("openai", {}).get("api_key", api_key)
        except Exception:
            pass
        client = OpenAI(api_key=api_key)
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to initialize OpenAI client: {e}")


def generate_embedding(text: str) -> list[float]:
    client = get_embedding_model()
    response = client.embeddings.create(
        model=config.EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    client = get_embedding_model()
    response = client.embeddings.create(
        model=config.EMBEDDING_MODEL,
        input=texts,
    )
    response.data.sort(key=lambda x: x.index)
    return [d.embedding for d in response.data]


def chunk_text(text: str, chunk_size: int = None, chunk_overlap: int = None) -> list[str]:
    if chunk_size is None:
        chunk_size = config.CHUNK_SIZE
    if chunk_overlap is None:
        chunk_overlap = config.CHUNK_OVERLAP

    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)

    chunks = []
    i = 0
    while i < len(tokens):
        chunk_tokens = tokens[i : i + chunk_size]
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append(chunk_text)
        i += chunk_size - chunk_overlap
        if i >= len(tokens):
            break

    return chunks


def count_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))
