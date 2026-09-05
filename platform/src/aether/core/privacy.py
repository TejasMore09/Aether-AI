"""Getting a person's data out, and getting a person out.

D31 chose India, the US and Europe, which makes GDPR an obligation rather than
a nicety: a right of access (Art. 15), portability (Art. 20) and erasure
(Art. 17). This is that, and it is written as an obligation — the interesting
work is not the endpoints, it is making sure they stay true.

**Erasing a user is not deleting a row, and the schema says so.** Email
addresses are stored in six places, not one: `users`, and then
`audit_logs.triggered_by`, `pending_approvals.resolved_by`,
`api_keys.created_by`, `notifications.recipient` and
`login_throttle.identifier`. Every one is personal data. A `DELETE FROM users`
would look like compliance and leave five copies behind, which is the version
of this feature most products ship.

**The registry below names every table in the schema**, and a test fails when
one appears that nobody has classified. That is the part worth having. An
export that was complete when it was written stops being complete the first
time a migration adds a table, and nothing about it will look broken — the
file still downloads, the endpoint still returns 200. Making the schema and
this file disagree loudly is the only way it stays honest (D68).

**Decisions are pseudonymised, not deleted.** A customer's audit trail is a
record of what their agent did and what a person decided; erasing the entries
would destroy the account of the business's own operations, which they rely on
and may be required to keep. Art. 17(3) allows retention where processing is
necessary for legal claims. So the *person* goes and the *decision* stays: the
email is replaced by a pseudonym that is random, stable across their rows, and
not reversible to the address it replaced.

**What this cannot do, said plainly.** Backups made before an erasure still
contain the data until they rotate out — fourteen by default, so about two
weeks. That is a normal and defensible position, and it is only defensible if
it is written down where a person asking can be told.
"""

from __future__ import annotations

import datetime
import json
import logging
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import text as sql

from aether.core.db import session as plain_session
from aether.core.db import tenant_session

logger = logging.getLogger(__name__)

# What happens to a table's rows when a person exercises their right to erasure.
DELETE = "delete"  # the rows are only about them
ANONYMISE = "anonymise"  # the record matters, the person does not
NOT_PERSONAL = "not personal"  # nothing about a natural person in it
STAFF = "staff"  # about platform employees, not customers


@dataclass(frozen=True)
class Holding:
    """What one table holds, and what erasure does to it."""

    holds: str
    on_erasure: str
    # The column carrying a user's email, where the table names a person by
    # address rather than by id. These are the ones a naive delete misses.
    email_column: str | None = None
    # The column carrying a user id.
    user_column: str | None = None
    # Whether a tenant's export includes it.
    tenant_scoped: bool = False


# Every table in the schema. A test asserts this covers the database exactly,
# so a migration that adds a table fails the build until somebody has decided
# what it holds. See the module docstring for why that matters more than the
# endpoints do.
REGISTRY: dict[str, Holding] = {
    # ── The person ────────────────────────────────────────────────────────
    "users": Holding(
        "email, name and password hash",
        ANONYMISE,  # rows elsewhere point at this id; it becomes a tombstone
        email_column="email",
    ),
    "memberships": Holding("which organisations they belong to", DELETE, user_column="user_id"),
    "sessions": Holding(
        "signed-in sessions, with the address each began from", DELETE, user_column="user_id"
    ),
    "mfa_enrolments": Holding("a sealed second-factor secret", DELETE, user_column="subject_id"),
    "mfa_recovery_codes": Holding("hashed recovery codes", DELETE, user_column="subject_id"),
    "password_resets": Holding(
        "reset requests, with the address each came from", DELETE, user_column="user_id"
    ),
    "login_throttle": Holding(
        "failed sign-in counts, keyed on the address typed", DELETE, email_column="identifier"
    ),
    # ── The record of what happened, which outlives the person ────────────
    "audit_logs": Holding(
        "every decision an agent made, and who triggered it",
        ANONYMISE,
        email_column="triggered_by",
        tenant_scoped=True,
    ),
    "pending_approvals": Holding(
        "decisions awaiting a human, and who resolved them",
        ANONYMISE,
        email_column="resolved_by",
        tenant_scoped=True,
    ),
    "notifications": Holding(
        "alerts sent, and the address each went to",
        ANONYMISE,
        email_column="recipient",
        tenant_scoped=True,
    ),
    "api_keys": Holding(
        "ingest credentials and who created them",
        ANONYMISE,
        email_column="created_by",
        tenant_scoped=True,
    ),
    # ── The business's data, which is not personal data ───────────────────
    "tenants": Holding("the organisation's name and settings", NOT_PERSONAL, tenant_scoped=True),
    "observations": Holding("readings the business reported", NOT_PERSONAL, tenant_scoped=True),
    "policy_configs": Holding("the agent's tuning", NOT_PERSONAL, tenant_scoped=True),
    "agent_instances": Holding("the agents themselves", NOT_PERSONAL, tenant_scoped=True),
    "alert_rules": Holding("when to notify", NOT_PERSONAL, tenant_scoped=True),
    "knowledge_chunks": Holding("what the agent remembers", NOT_PERSONAL, tenant_scoped=True),
    "llm_usage": Holding("diagnosis spend", NOT_PERSONAL, tenant_scoped=True),
    # ── Platform machinery ────────────────────────────────────────────────
    "alembic_version": Holding("the schema revision", NOT_PERSONAL),
    "backup_runs": Holding("backup attempts and their checks", NOT_PERSONAL),
    "error_events": Holding("scrubbed faults (D57)", NOT_PERSONAL),
    "erasure_log": Holding("that an erasure happened, never who it was", NOT_PERSONAL),
    # ── Platform staff, not customers ─────────────────────────────────────
    "platform_admins": Holding("staff accounts", STAFF),
    "staff_sessions": Holding("staff sessions", STAFF),
    "staff_audit_logs": Holding(
        "what staff did, append-only by trigger. Erasing a member of staff is "
        "an employment matter and would fight that trigger; a customer's "
        "erasure never touches it",
        STAFF,
    ),
    "break_glass_grants": Holding("staff access to one tenant, with a reason", STAFF),
}


class PrivacyError(Exception):
    """The request cannot be carried out as asked."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def known_tables() -> set[str]:
    """Every table actually in the database right now."""
    with plain_session() as db:
        rows = db.execute(
            sql("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        return set(rows)


def unclassified() -> set[str]:
    """Tables the registry has not decided about. Should always be empty."""
    return known_tables() - set(REGISTRY)


def stale_entries() -> set[str]:
    """Registry entries for tables that no longer exist."""
    return set(REGISTRY) - known_tables()


# ── Access and portability ────────────────────────────────────────────────────


def _rows(db, statement: str, params: dict) -> list[dict]:
    out = []
    for row in db.execute(sql(statement), params).mappings():
        item = {}
        for key, value in row.items():
            if isinstance(value, datetime.datetime):
                item[key] = value.isoformat()
            elif isinstance(value, uuid.UUID):
                item[key] = str(value)
            else:
                item[key] = value
        out.append(item)
    return out


def export_user(user_id: uuid.UUID) -> dict:
    """Everything the platform holds about one person.

    JSON, because Art. 20 asks for a structured, commonly used and
    machine-readable format and this is all three. Nothing here is a summary:
    a portability export that has been helpfully condensed is not the data.
    """
    with plain_session() as db:
        profile = _rows(
            db,
            "SELECT id, email, display_name, created_at, is_active FROM users WHERE id = :id",
            {"id": user_id},
        )
        if not profile:
            raise PrivacyError("no such person")
        email = profile[0]["email"]

        return {
            "exported_at": _now().isoformat(),
            "about": "Everything Aether holds about you as a person. Your organisation's "
            "business data is a separate export, available to its owner.",
            "profile": profile[0],
            "organisations": _rows(
                db,
                "SELECT t.name, t.slug, m.role, m.created_at AS joined_at "
                "FROM memberships m JOIN tenants t ON t.id = m.tenant_id "
                "WHERE m.user_id = :id",
                {"id": user_id},
            ),
            "sessions": _rows(
                db,
                "SELECT created_at, last_seen_at, expires_at, revoked_at, revoked_reason, "
                "created_from FROM sessions WHERE user_id = :id ORDER BY created_at",
                {"id": user_id},
            ),
            "second_factor": _rows(
                db,
                "SELECT created_at, confirmed_at FROM mfa_enrolments "
                "WHERE subject_kind = 'user' AND subject_id = :id",
                {"id": user_id},
            ),
            "password_resets": _rows(
                db,
                "SELECT created_at, expires_at, used_at, requested_from FROM password_resets "
                "WHERE user_id = :id ORDER BY created_at",
                {"id": user_id},
            ),
            "sign_in_throttling": _rows(
                db,
                "SELECT scope, failures, window_started_at, locked_until FROM login_throttle "
                "WHERE identifier = :email",
                {"email": email},
            ),
            # The four tables below are row-level-security scoped, so they are
            # read one organisation at a time rather than in this transaction.
            **_across_organisations(user_id, email),
            "not_included": [
                "Your password, which is stored only as a bcrypt hash and cannot be read back.",
                "Your second-factor secret, which is stored encrypted and would let anyone "
                "holding this file generate your codes.",
                "Recovery codes, stored only as hashes.",
            ],
        }


def organisations_of(user_id: uuid.UUID) -> list[uuid.UUID]:
    """Every organisation this person currently belongs to."""
    with plain_session() as db:
        return list(
            db.execute(
                sql("SELECT tenant_id FROM memberships WHERE user_id = :id"), {"id": user_id}
            ).scalars()
        )


# The four tables that name a person by email *and* are row-level-security
# scoped. They cannot be read or written from a plain session, which is the
# isolation model working as designed — so they are visited one organisation at
# a time, inside that organisation's own transaction.
#
# **The bound this puts on erasure, stated because it is real.** Rows in an
# organisation the person has since *left* are not reachable this way: there is
# no membership to find them through, and giving this module a connection that
# bypasses row-level security to go looking would trade the platform's central
# security property for a rare operation. The right fix is to pseudonymise a
# person's trace in an organisation at the moment they leave it, which is where
# the context still exists. Nothing removes a membership today, so the gap is
# currently theoretical — and it is written here so that whoever builds
# "remove a member" knows it is theirs to close.
_TENANT_SCOPED_EMAIL_COLUMNS = (
    (
        "audit_logs",
        "triggered_by",
        "actions_you_triggered",
        "SELECT created_at, domain, action, risk_level, status FROM audit_logs "
        "WHERE triggered_by = :email ORDER BY created_at",
    ),
    (
        "pending_approvals",
        "resolved_by",
        "decisions_you_resolved",
        "SELECT created_at, domain, action, status, resolved_at FROM pending_approvals "
        "WHERE resolved_by = :email ORDER BY created_at",
    ),
    (
        "notifications",
        "recipient",
        "emails_sent_to_you",
        "SELECT created_at, kind, channel, subject, status FROM notifications "
        "WHERE recipient = :email ORDER BY created_at",
    ),
    (
        "api_keys",
        "created_by",
        "api_keys_you_created",
        "SELECT created_at, name, key_prefix, last_used_at, revoked_at FROM api_keys "
        "WHERE created_by = :email ORDER BY created_at",
    ),
)


def _across_organisations(user_id: uuid.UUID, email: str) -> dict:
    """Read this person's rows from each organisation they belong to."""
    gathered: dict[str, list] = {key: [] for _, _, key, _ in _TENANT_SCOPED_EMAIL_COLUMNS}
    for tenant_id in organisations_of(user_id):
        with tenant_session(tenant_id) as db:
            for _, _, key, statement in _TENANT_SCOPED_EMAIL_COLUMNS:
                for row in _rows(db, statement, {"email": email}):
                    gathered[key].append({"organisation": str(tenant_id), **row})
    return gathered


def export_tenant(tenant_id: uuid.UUID) -> dict:
    """Everything the platform holds for one organisation.

    Run inside the tenant's own transaction, so row-level security is what
    scopes it rather than a WHERE clause somebody could forget — the same
    property the whole platform rests on.
    """
    with tenant_session(tenant_id) as db:
        organisation = _rows(
            db,
            "SELECT id, name, slug, created_at, currency, sector, is_active "
            "FROM tenants WHERE id = :id",
            {"id": tenant_id},
        )
        if not organisation:
            raise PrivacyError("no such organisation")

        return {
            "exported_at": _now().isoformat(),
            "organisation": organisation[0],
            # `memberships` and `users` carry no row-level-security policy —
            # they are what *establishes* a tenant rather than being scoped by
            # one. Inside a tenant transaction an unfiltered join over them
            # would return every organisation's people, so the WHERE clause
            # here is load-bearing rather than tidy.
            "people": _rows(
                db,
                "SELECT u.email, u.display_name, m.role, m.created_at AS joined_at "
                "FROM memberships m JOIN users u ON u.id = m.user_id "
                "WHERE m.tenant_id = :tenant_id",
                {"tenant_id": tenant_id},
            ),
            "readings": _rows(
                db,
                "SELECT observed_at, domain, metrics, drift_fraction, performance, source, "
                "status, issues, details FROM observations ORDER BY observed_at",
                {},
            ),
            "decisions": _rows(
                db,
                "SELECT created_at, domain, action, risk_level, status, triggered_by, details "
                "FROM audit_logs ORDER BY created_at",
                {},
            ),
            "approvals": _rows(
                db,
                "SELECT created_at, domain, action, reason, risk_level, expected_loss, "
                "currency, status, resolved_by, resolved_at, diagnosis FROM pending_approvals "
                "ORDER BY created_at",
                {},
            ),
            "policies": _rows(db, "SELECT domain, params, updated_at FROM policy_configs", {}),
            "agents": _rows(
                db, "SELECT name, kind, created_at, is_active FROM agent_instances", {}
            ),
            "what_the_agent_remembers": _rows(
                db,
                "SELECT created_at, occurred_at, kind, domain, source_id, body, meta "
                "FROM knowledge_chunks ORDER BY created_at",
                {},
            ),
            "diagnosis_spend": _rows(
                db,
                "SELECT created_at, purpose, model, prompt_tokens, completion_tokens, cost_usd "
                "FROM llm_usage ORDER BY created_at",
                {},
            ),
        }


# ── Erasure ───────────────────────────────────────────────────────────────────


def _pseudonym() -> str:
    """A stand-in for an address, stable across one person's rows.

    Random rather than derived: a hash of the email would be reversible by
    anyone who can guess an address, which for an email is everyone.
    """
    return f"erased-{secrets.token_hex(6)}"


def erase_user(user_id: uuid.UUID) -> dict:
    """Remove a person, keeping the record of what their organisation did.

    Refuses if they are the only owner of an active organisation. Erasing them
    would leave a business nobody can administer, and the right answer is for
    somebody else to be made an owner first — or for the organisation itself to
    be deleted, which is a different and much larger decision.
    """
    with plain_session() as db:
        row = db.execute(sql("SELECT email FROM users WHERE id = :id"), {"id": user_id}).first()
        if row is None:
            raise PrivacyError("no such person")
        email = row.email

        stranded = (
            db.execute(
                sql("""
                SELECT t.slug
                FROM memberships m
                JOIN tenants t ON t.id = m.tenant_id
                WHERE m.user_id = :id AND m.role = 'owner' AND t.is_active
                  AND NOT EXISTS (
                      SELECT 1 FROM memberships other
                      WHERE other.tenant_id = m.tenant_id
                        AND other.user_id <> m.user_id
                        AND other.role = 'owner'
                  )
                """),
                {"id": user_id},
            )
            .scalars()
            .all()
        )
        if stranded:
            raise PrivacyError(
                "you are the only owner of "
                + ", ".join(stranded)
                + ". Make somebody else an owner first, or delete the organisation."
            )

    alias = _pseudonym()
    counts: dict[str, int] = {}

    # Rows whose *record* matters and whose *person* does not, visited one
    # organisation at a time because row-level security scopes them. This is
    # the part a delete-the-row implementation leaves behind entirely.
    for table, *_ in _TENANT_SCOPED_EMAIL_COLUMNS:
        counts[table] = 0
    for tenant_id in organisations_of(user_id):
        with tenant_session(tenant_id) as db:
            for table, column, _, _ in _TENANT_SCOPED_EMAIL_COLUMNS:
                rewritten = db.execute(
                    sql(
                        f"UPDATE {table} SET {column} = :alias WHERE {column} = :email RETURNING 1"
                    ),
                    {"alias": alias, "email": email},
                ).all()
                counts[table] += len(rewritten)

    with plain_session() as db:
        # Rows that are only about them.
        for table, column, value in (
            ("memberships", "user_id", user_id),
            ("sessions", "user_id", user_id),
            ("password_resets", "user_id", user_id),
            ("login_throttle", "identifier", email),
        ):
            result = db.execute(
                sql(f"DELETE FROM {table} WHERE {column} = :value RETURNING 1"), {"value": value}
            ).all()
            counts[table] = len(result)

        for table in ("mfa_enrolments", "mfa_recovery_codes"):
            result = db.execute(
                sql(
                    f"DELETE FROM {table} WHERE subject_kind = 'user' AND subject_id = :id "
                    "RETURNING 1"
                ),
                {"id": user_id},
            ).all()
            counts[table] = len(result)

        # The account itself becomes a tombstone rather than disappearing:
        # nothing may point at a missing id, and `.invalid` is reserved by
        # RFC 2606 precisely so it can never be delivered to.
        db.execute(
            sql("""
                UPDATE users
                SET email = :alias, display_name = '', password_hash = :dead, is_active = false
                WHERE id = :id
                """),
            {"alias": f"{alias}@aether.invalid", "dead": "erased", "id": user_id},
        )
        counts["users"] = 1

        db.execute(
            sql("""
                INSERT INTO erasure_log (id, subject_kind, pseudonym, completed_at, counts)
                VALUES (:id, 'user', :alias, :now, CAST(:counts AS jsonb))
                """),
            {"id": uuid.uuid4(), "alias": alias, "now": _now(), "counts": json.dumps(counts)},
        )

    logger.info("erased a user; %s rows touched", sum(counts.values()))
    return {"pseudonym": alias, "rows": counts}


def erase_tenant(tenant_id: uuid.UUID) -> dict:
    """Delete an organisation and everything scoped to it.

    Not pseudonymisation: when the organisation goes there is no record left
    that anyone has a claim to keep, and the tenant's own data is the thing
    being removed rather than a person inside it.

    The members' *accounts* survive, because a person may belong to more than
    one organisation and their identity is not this organisation's to delete.
    """
    counts: dict[str, int] = {}

    with tenant_session(tenant_id) as db:
        for table in (
            "knowledge_chunks",
            "llm_usage",
            "notifications",
            "api_keys",
            "alert_rules",
            "pending_approvals",
            "audit_logs",
            "observations",
            "policy_configs",
            "agent_instances",
        ):
            result = db.execute(sql(f"DELETE FROM {table} RETURNING 1")).all()
            counts[table] = len(result)

    with plain_session() as db:
        counts["memberships"] = len(
            db.execute(
                sql("DELETE FROM memberships WHERE tenant_id = :id RETURNING 1"), {"id": tenant_id}
            ).all()
        )
        counts["sessions"] = len(
            db.execute(
                sql("DELETE FROM sessions WHERE tenant_id = :id RETURNING 1"), {"id": tenant_id}
            ).all()
        )
        counts["break_glass_grants"] = len(
            db.execute(
                sql("DELETE FROM break_glass_grants WHERE tenant_id = :id RETURNING 1"),
                {"id": tenant_id},
            ).all()
        )
        counts["tenants"] = len(
            db.execute(
                sql("DELETE FROM tenants WHERE id = :id RETURNING 1"), {"id": tenant_id}
            ).all()
        )

        alias = _pseudonym()
        db.execute(
            sql("""
                INSERT INTO erasure_log (id, subject_kind, pseudonym, completed_at, counts)
                VALUES (:id, 'tenant', :alias, :now, CAST(:counts AS jsonb))
                """),
            {"id": uuid.uuid4(), "alias": alias, "now": _now(), "counts": json.dumps(counts)},
        )

    logger.info("erased a tenant; %s rows removed", sum(counts.values()))
    return {"pseudonym": alias, "rows": counts}


# How long a backup keeps what an erasure removed. Not a setting: it is
# `backup_keep` × the interval, and saying it out loud is the point.
def backup_retention_note() -> str:
    from aether.core.config import get_settings

    settings = get_settings()
    days = settings.backup_keep * settings.backup_interval_hours / 24
    return (
        f"Backups taken before this request still contain the data for about "
        f"{days:.0f} days, until they rotate out. They are not searched or "
        f"restored except to recover from a failure."
    )
