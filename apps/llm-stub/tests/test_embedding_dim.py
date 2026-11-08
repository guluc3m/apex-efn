from __future__ import annotations

from pathlib import Path

from helpers import mount_stub


async def test_configured_embedding_dimension(tmp_path: Path) -> None:
    (tmp_path / "default.yaml").write_text(
        "name: default\nembedding_dim: 16\nresponse:\n  kind: text\n  content: a\n"
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post("/v1/embeddings", json={"model": "e", "input": "x"})
        assert len(r.json()["data"][0]["embedding"]) == 16
    finally:
        await client.aclose()
