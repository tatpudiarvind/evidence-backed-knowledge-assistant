"""Calls made to a hosted language model each UTC day (Phase 9).

The count is kept in PostgreSQL, so every API process shares one limit and a restart doesn't
reset it.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

# A single statement: the first call of a day inserts its row, and later calls add one only
# while the day's count is below the limit, so two requests can't both take the last call.
_RESERVE = text(
    """
    INSERT INTO llm_usage (day, calls)
    VALUES ((now() AT TIME ZONE 'utc')::date, 1)
    ON CONFLICT (day) DO UPDATE SET calls = llm_usage.calls + 1
    WHERE llm_usage.calls < :limit
    RETURNING calls
    """
)
_ADD_TOKENS = text(
    """
    INSERT INTO llm_usage (day, calls, prompt_tokens, completion_tokens)
    VALUES ((now() AT TIME ZONE 'utc')::date, 0, :prompt, :completion)
    ON CONFLICT (day) DO UPDATE SET
        prompt_tokens = llm_usage.prompt_tokens + :prompt,
        completion_tokens = llm_usage.completion_tokens + :completion
    """
)


def reserve_call(session: Session, limit: int) -> bool:
    """Count one call against today's limit and commit it; False once the limit is reached."""
    reserved = session.execute(_RESERVE, {"limit": limit}).first() is not None
    session.commit()
    return reserved


def add_tokens(session: Session, prompt_tokens: int, completion_tokens: int) -> None:
    """Add the tokens a provider reported for a call to today's totals, and commit."""
    session.execute(_ADD_TOKENS, {"prompt": prompt_tokens, "completion": completion_tokens})
    session.commit()
