"""LIVE check of your LLM + embedding keys. Usage: python -m scripts.check_llm"""
from app.llm.client import LLMClient
from app.llm.schemas import QueryList

llm = LLMClient()
out = llm.complete_json("You write search queries.", "Give 3 queries about student assignment planners.", QueryList)
print("LLM OK:", out.queries)
vecs = llm.embed(["assignment planner", "homework organiser"])
print(f"Embeddings OK: {len(vecs)} vectors of length {len(vecs[0])}")
print("usage:", llm.usage)
