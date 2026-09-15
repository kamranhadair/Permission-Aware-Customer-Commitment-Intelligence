from app.ingestion.parsers import calls as calls_parser
from app.ingestion.parsers import slack as slack_parser
from app.ingestion.parsers import support as support_parser
from app.ingestion.types import NormalizedAcl


def test_support_ticket_parses_into_normalized_document():
    raw = {
        "tickets": [
            {
                "id": "T-1",
                "account_slug": "acme-corp",
                "subject": "Subject",
                "description": "Body",
                "created_at": "2026-08-01T10:00:00Z",
                "sensitivity": "internal",
                "acl": {"users": ["alice@x.example"], "groups": []},
            }
        ]
    }
    documents, errors = support_parser.parse(raw)
    assert errors == []
    assert len(documents) == 1
    doc = documents[0]
    assert doc.external_id == "T-1"
    assert doc.source == "support"
    assert doc.account_slug == "acme-corp"
    assert doc.title == "Subject"
    assert doc.content == "Body"
    assert doc.sensitivity == "internal"
    assert doc.acl == NormalizedAcl(users=["alice@x.example"], groups=[])


def test_support_ticket_malformed_record_is_a_parse_error_not_an_exception():
    raw = {"tickets": [{"id": "T-2", "account_slug": "acme-corp"}]}  # missing subject/description/etc.
    documents, errors = support_parser.parse(raw)
    assert documents == []
    assert len(errors) == 1
    assert errors[0].external_id == "T-2"


def test_call_transcript_parses_into_normalized_document():
    raw = {
        "calls": [
            {
                "id": "C-1",
                "account_slug": "acme-corp",
                "title": "QBR",
                "transcript": "Transcript text",
                "occurred_at": "2026-08-01T10:00:00Z",
                "sensitivity": "customer_shared",
                "acl": {"users": [], "groups": ["account-management"]},
            }
        ]
    }
    documents, errors = calls_parser.parse(raw)
    assert errors == []
    assert len(documents) == 1
    doc = documents[0]
    assert doc.external_id == "C-1"
    assert doc.source == "call"
    assert doc.content == "Transcript text"
    assert doc.acl == NormalizedAcl(users=[], groups=["account-management"])


def test_call_transcript_malformed_record_is_a_parse_error():
    raw = {"calls": [{"id": "C-2", "account_slug": "acme-corp", "title": "No transcript"}]}
    documents, errors = calls_parser.parse(raw)
    assert documents == []
    assert len(errors) == 1


def _channel(channel_id="CH-1", account_slug="acme-corp", sensitivity="internal", acl=None):
    return {
        "id": channel_id,
        "name": "general",
        "account_slug": account_slug,
        "sensitivity": sensitivity,
        "acl": acl if acl is not None else {"users": [], "groups": ["product"]},
    }


def test_slack_thread_with_root_lacking_thread_ts_becomes_one_document():
    channels = {"channels": [_channel()]}
    messages = {
        "messages": [
            {"channel_id": "CH-1", "ts": "100.0", "user": "bob@x.example", "text": "root message"},
            {"channel_id": "CH-1", "ts": "101.0", "thread_ts": "100.0", "user": "carol@x.example", "text": "reply 1"},
            {"channel_id": "CH-1", "ts": "102.0", "thread_ts": "100.0", "user": "bob@x.example", "text": "reply 2"},
        ]
    }
    documents, errors = slack_parser.parse(channels, messages)
    assert errors == []
    assert len(documents) == 1
    doc = documents[0]
    assert doc.external_id == "CH-1:100.0"
    assert "root message" in doc.content
    assert "reply 1" in doc.content
    assert "reply 2" in doc.content
    assert doc.content.index("root message") < doc.content.index("reply 1") < doc.content.index("reply 2")


def test_slack_standalone_message_with_no_replies_becomes_one_document():
    channels = {"channels": [_channel()]}
    messages = {"messages": [{"channel_id": "CH-1", "ts": "200.0", "user": "bob@x.example", "text": "standalone"}]}
    documents, errors = slack_parser.parse(channels, messages)
    assert errors == []
    assert len(documents) == 1
    assert documents[0].external_id == "CH-1:200.0"
    assert "standalone" in documents[0].content


def test_slack_thread_and_standalone_documents_inherit_channel_acl():
    acl = {"users": ["alice@x.example"], "groups": ["exec"]}
    channels = {"channels": [_channel(acl=acl, sensitivity="confidential")]}
    messages = {
        "messages": [
            {"channel_id": "CH-1", "ts": "100.0", "user": "bob@x.example", "text": "root"},
            {"channel_id": "CH-1", "ts": "101.0", "thread_ts": "100.0", "user": "carol@x.example", "text": "reply"},
            {"channel_id": "CH-1", "ts": "200.0", "user": "bob@x.example", "text": "standalone"},
        ]
    }
    documents, errors = slack_parser.parse(channels, messages)
    assert errors == []
    assert len(documents) == 2
    for doc in documents:
        assert doc.acl == NormalizedAcl(users=["alice@x.example"], groups=["exec"])
        assert doc.sensitivity == "confidential"
        assert doc.account_slug == "acme-corp"


def test_slack_reply_referencing_nonexistent_root_is_a_parse_error():
    channels = {"channels": [_channel()]}
    messages = {
        "messages": [
            {"channel_id": "CH-1", "ts": "101.0", "thread_ts": "999.0", "user": "carol@x.example", "text": "orphan reply"}
        ]
    }
    documents, errors = slack_parser.parse(channels, messages)
    assert documents == []
    assert len(errors) == 1
    assert "999.0" in errors[0].reason
