"""Per-tenant API keys, for systems that push readings without a person.

Until now the only credential was a user's JWT, obtained by someone typing a
password into a browser. That makes an unattended connector impossible: a
nightly job pulling from an accounting system has no session to borrow. This
is the credential such a job uses.

Three deliberate properties:

  - Only a hash is stored. The key is displayed once, at creation, and is
    unrecoverable afterwards, so a database disclosure yields no working
    credentials.
  - Keys are ingest-scoped. A leaked key can submit readings; it cannot
    approve a decision, read an audit trail or see a diagnosis. A credential
    that lives in someone else's cron job should carry only that job's
    authority.
  - Keys carry a recognisable prefix, so a scanner sweeping a public
    repository can spot one and a person can tell theirs apart.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text

from aether.core.db import session as plain_session
from aether.core.db import tenant_session
from aether.core.models import ApiKey

KEY_PREFIX = "aek_live_"
_SECRET_BYTES = 32  # 256 bits


def generate_key() -> str:
    """A new secret. 256 bits of entropy from the OS CSPRNG."""
    return f"{KEY_PREFIX}{secrets.token_urlsafe(_SECRET_BYTES)}"


def hash_key(raw: str) -> str:
    """Hash for storage and lookup.

    SHA-256 rather than bcrypt, and that is deliberate rather than an
    oversight. Slow hashing exists to make guessing *low-entropy* secrets
    expensive — passwords. These keys carry 256 bits from a CSPRNG, so there
    is nothing to guess, and a slow hash would instead add its cost to every
    single ingest request. The trade only makes sense for passwords.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def display_prefix(raw: str) -> str:
    """The identifiable, non-secret head of a key, e.g. aek_live_9f3b."""
    return raw[: len(KEY_PREFIX) + 4]


@dataclass(frozen=True)
class IssuedKey:
    id: uuid.UUID
    name: str
    secret: str  # shown once, never stored
    prefix: str


def create_key(tenant_id: uuid.UUID, name: str, created_by: str) -> IssuedKey:
    raw = generate_key()
    with tenant_session(tenant_id) as db:
        record = ApiKey(
            tenant_id=tenant_id,
            name=name,
            key_hash=hash_key(raw),
            key_prefix=display_prefix(raw),
            created_by=created_by,
        )
        db.add(record)
        db.flush()
        return IssuedKey(id=record.id, name=name, secret=raw, prefix=record.key_prefix)


@dataclass(frozen=True)
class KeyIdentity:
    key_id: uuid.UUID
    tenant_id: uuid.UUID
    name: str


def resolve_key(raw: str) -> KeyIdentity | None:
    """Identify the tenant a key belongs to, or None if it is not usable.

    This runs *before* a tenant context exists — establishing the tenant is
    the whole point — so it cannot use tenant_session. It instead opens a
    transaction-local flag that a dedicated RLS policy accepts for this one
    lookup. Nothing leaks: the caller must already hold the secret whose hash
    is being matched, and only that row can be found.
    """
    if not raw or not raw.startswith(KEY_PREFIX):
        return None

    digest = hash_key(raw)
    with plain_session() as db:
        db.execute(text("SELECT set_config('app.apikey_lookup', 'on', true)"))
        record = db.scalar(select(ApiKey).where(ApiKey.key_hash == digest))
        if record is None or record.revoked_at is not None:
            return None
        return KeyIdentity(key_id=record.id, tenant_id=record.tenant_id, name=record.name)


def touch_key(tenant_id: uuid.UUID, key_id: uuid.UUID) -> None:
    """Record that a key was used, so a stale one is visible to its owner."""
    with tenant_session(tenant_id) as db:
        record = db.get(ApiKey, key_id)
        if record is not None:
            record.last_used_at = datetime.datetime.now(datetime.UTC)


def revoke_key(tenant_id: uuid.UUID, key_id: uuid.UUID) -> bool:
    with tenant_session(tenant_id) as db:
        record = db.get(ApiKey, key_id)
        if record is None or record.revoked_at is not None:
            return False
        record.revoked_at = datetime.datetime.now(datetime.UTC)
        return True


def list_keys(tenant_id: uuid.UUID) -> list[dict]:
    with tenant_session(tenant_id) as db:
        rows = db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "prefix": r.key_prefix,
                "created_at": r.created_at.isoformat(),
                "created_by": r.created_by,
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                "revoked": r.revoked_at is not None,
            }
            for r in rows
        ]
