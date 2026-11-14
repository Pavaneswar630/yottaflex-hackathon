"""Local lexical retrieval and provider-neutral LLM helpers."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


RULES = [
    {"id": "RULE-PRECEDENCE", "text": "An operation may start only after its predecessor operation has finished. Operation sequence is fixed by the effective product routing."},
    {"id": "RULE-MACHINE-CAPACITY", "text": "A machine processes at most one operation at a time. Setup and processing intervals both consume machine capacity."},
    {"id": "RULE-MACHINE-CALENDAR", "text": "Setup and processing must fit within one machine shift calendar interval. Machine downtime is unavailable capacity."},
    {"id": "RULE-MATERIAL-AVAILABLE", "text": "An order's inventory lots must be available before material consumption and before production starts. Consumption cannot exceed lot quantity."},
    {"id": "RULE-CHANGEOVER-REQUIRED", "text": "Setup duration depends on machine, previous product family, and next product family in the changeover matrix."},
    {"id": "RULE-TOOLING-CAPACITY", "text": "A shared tooling resource cannot be assigned to overlapping operations."},
    {"id": "RULE-ORDER-DUE-DATE", "text": "Order lateness is max(0, final operation end minus due minute); due dates are not hard constraints."},
    {"id": "RULE-INFEASIBILITY", "text": "An operation with no eligible machine slot in the planning horizon is marked infeasible with a reason; the generator does not fabricate a placement."},
]
ISSUE_RULE_IDS = {
    "machine_overlap": "RULE-MACHINE-CAPACITY",
    "precedence_violation": "RULE-PRECEDENCE",
    "material_before_availability": "RULE-MATERIAL-AVAILABLE",
    "outside_shift": "RULE-MACHINE-CALENDAR",
    "changeover_omitted": "RULE-CHANGEOVER-REQUIRED",
    "tooling_overlap": "RULE-TOOLING-CAPACITY",
}


class LLMClient:
    """OpenAI-chat-completions-compatible client; configure endpoint, model, and key via env."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None, timeout: int = 45):
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout = timeout

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not set; use an OpenAI-compatible provider and configure LLM_BASE_URL/LLM_MODEL as needed")
        payload = json.dumps({
            "model": self.model, "temperature": temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=payload, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"LLM provider returned HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Could not reach configured LLM provider: {error.reason}") from error
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("LLM provider returned an unsupported chat-completions response") from error


class Retriever:
    """Deterministic sparse-vector retrieval; no external embedding service required."""

    def __init__(self, documents: list[dict[str, Any]]):
        self.documents = documents

    @classmethod
    def from_dataset(cls, data: dict, validation: dict):
        docs = [
            {"id": row["id"], "rule_id": row["id"], "text": row["text"], "kind": "rule"}
            for row in RULES
        ]
        for entity, spec in data.items():
            if not spec:
                continue
            docs.append({
                "id": f"DATA-{entity.upper()}",
                "entity": entity,
                "kind": "data_dictionary",
                "text": f"{entity}: fields " + ", ".join(spec[0].keys()),
            })
        docs.append({
            "id": "VALIDATION-SUMMARY",
            "kind": "validation",
            "schedule_id": validation.get("schedule_id"),
            "text": f"Schedule validation is {'valid' if validation['valid'] else 'invalid'}. Metrics: {json.dumps(validation['metrics'], sort_keys=True)}",
        })
        for index, issue in enumerate(validation.get("issues", []), start=1):
            issue_type = issue["issue_type"]
            rule_id = ISSUE_RULE_IDS.get(issue_type)
            docs.append({
                "id": f"VALIDATION-{validation.get('schedule_id', 'UNKNOWN')}-{index:03d}",
                "kind": "validation_issue",
                "schedule_id": validation.get("schedule_id"),
                "issue_type": issue_type,
                "rule_id": rule_id,
                "text": f"{issue_type}: {issue['detail']}; affected IDs: {', '.join(issue['affected_entity_ids'])}",
            })
        # Ground truth is intentionally not an input and no scenario labels are indexed.
        return cls(docs)

    def search(self, query: str, limit: int = 4, filters: dict[str, str] | None = None) -> list[dict]:
        if limit < 1:
            raise ValueError("limit must be positive")
        terms = _tokens(query)
        if not terms:
            return []
        docs = [
            doc for doc in self.documents
            if all(doc.get(key) == value for key, value in (filters or {}).items())
        ]
        tokenized = [_tokens(doc["text"]) for doc in docs]
        document_frequency = Counter(term for words in tokenized for term in set(words))
        total_documents = max(1, len(docs))
        query_weights = _tfidf(terms, document_frequency, total_documents)
        scored = []
        for doc, words in zip(docs, tokenized):
            weights = _tfidf(words, document_frequency, total_documents)
            dot = sum(weight * query_weights.get(term, 0.0) for term, weight in weights.items())
            denominator = math.sqrt(sum(value * value for value in weights.values())) * math.sqrt(
                sum(value * value for value in query_weights.values())
            )
            score = dot / denominator if denominator else 0.0
            if score:
                scored.append((score, doc))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        return [dict(doc, score=score) for score, doc in scored[:limit]]


def _tfidf(tokens: list[str], document_frequency: Counter, document_count: int) -> dict[str, float]:
    term_frequency = Counter(tokens)
    return {
        term: (1 + math.log(count)) * (1 + math.log((document_count + 1) / (document_frequency[term] + 1)))
        for term, count in term_frequency.items()
    }


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def explain_violation(issue: dict, retriever: Retriever, client: LLMClient | None = None) -> dict:
    query = f"{issue['issue_type']} {issue['detail']}"
    rule_id = ISSUE_RULE_IDS.get(issue["issue_type"])
    evidence = retriever.search(query, limit=4, filters={"rule_id": rule_id}) if rule_id else []
    if not evidence:
        evidence = retriever.search(query, limit=4)
    if not evidence:
        raise ValueError("No matching rule or validation evidence was retrieved")
    client = client or LLMClient()
    answer = client.complete(
        "Explain production schedule exceptions using only supplied evidence. Return one JSON object with keys "
        "issue_type, cited_ids, explanation, suggested_fix. Do not invent IDs or facts.",
        json.dumps({"validator_evidence": issue, "retrieved_documents": evidence}, ensure_ascii=True),
    )
    try:
        result = json.loads(answer)
    except json.JSONDecodeError as error:
        raise RuntimeError("LLM explanation was not valid JSON") from error
    required = {"issue_type", "cited_ids", "explanation", "suggested_fix"}
    if not isinstance(result, dict) or set(result) != required or not isinstance(result["cited_ids"], list):
        raise RuntimeError("LLM explanation does not match the required response schema")
    evidence_ids = set(issue.get("affected_entity_ids", []))
    if any(not isinstance(value, str) or value not in evidence_ids for value in result["cited_ids"]):
        raise RuntimeError("LLM cited an entity ID not present in the validator evidence")
    return result


def query_read_only_sql(connection: sqlite3.Connection, query: str, max_rows: int = 100) -> list[dict]:
    """Execute exactly one read-only SELECT and cap returned rows."""
    statement = query.strip()
    if not re.match(r"(?is)^select\b", statement) or ";" in statement.rstrip(";"):
        raise ValueError("Only one SELECT statement is allowed")
    statement = statement.rstrip(";")
    connection.set_authorizer(_read_only_authorizer)
    try:
        cursor = connection.execute(statement)
        columns = [column[0] for column in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
        if len(rows) > max_rows:
            raise ValueError(f"Query exceeded the {max_rows}-row limit")
        return [dict(zip(columns, row)) for row in rows]
    except sqlite3.DatabaseError as error:
        raise ValueError(f"Read-only query rejected: {error}") from error
    finally:
        connection.set_authorizer(None)


def _read_only_authorizer(action, arg1, arg2, database, trigger):
    allowed = {
        sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def ask_sql(question: str, connection: sqlite3.Connection, client: LLMClient | None = None) -> dict:
    client = client or LLMClient()
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    schema = {}
    for (table,) in tables:
        schema[table] = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
    sql = client.complete(
        "Translate the question to one SQLite SELECT statement only. Never use ground truth, writes, multiple statements, "
        "or hidden assumptions. Return SQL only.",
        json.dumps({"question": question, "schema": schema}, ensure_ascii=True),
    ).strip().removeprefix("```sql").removesuffix("```").strip()
    return {"sql": sql, "rows": query_read_only_sql(connection, sql)}
