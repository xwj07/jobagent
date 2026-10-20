from jobagent.normalize import canonical


def test_alias_mapping():
    assert canonical("K8s") == "kubernetes"
    assert canonical("Postgres") == "postgresql"
    assert canonical("大模型") == "大语言模型"


def test_whitespace_and_case():
    assert canonical("  FastAPI  ") == "fastapi"
    assert canonical("Spring   Boot") == "spring boot"


def test_trailing_punctuation():
    assert canonical("Python.") == "python"
    assert canonical("RAG，") == "rag"


def test_unknown_passes_through():
    assert canonical("Rust") == "rust"
