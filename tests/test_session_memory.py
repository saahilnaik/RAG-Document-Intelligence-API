from uuid import uuid4

from services.session_memory import session_memory


def test_add_and_get_turns():
    sid = uuid4()
    session_memory.add_turn(sid, "What is RAG?", "RAG is retrieval-augmented generation.")
    turns = session_memory.get_turns(sid)
    assert len(turns) == 1
    assert turns[0]["question"] == "What is RAG?"
    assert turns[0]["answer"] == "RAG is retrieval-augmented generation."


def test_eviction_at_max_turns():
    sid = uuid4()
    for i in range(7):
        session_memory.add_turn(sid, f"Q{i}", f"A{i}")
    turns = session_memory.get_turns(sid)
    assert len(turns) == 5          # default MAX_CONVERSATION_TURNS=5
    assert turns[0]["question"] == "Q2"   # Q0, Q1 evicted
    assert turns[-1]["question"] == "Q6"


def test_per_session_isolation():
    sid_a, sid_b = uuid4(), uuid4()
    session_memory.add_turn(sid_a, "Q-A", "Ans-A")
    session_memory.add_turn(sid_b, "Q-B", "Ans-B")
    assert session_memory.get_turns(sid_a)[0]["question"] == "Q-A"
    assert session_memory.get_turns(sid_b)[0]["question"] == "Q-B"
    assert len(session_memory.get_turns(sid_a)) == 1


def test_empty_session_returns_empty_list():
    assert session_memory.get_turns(uuid4()) == []


def test_clear_removes_session():
    sid = uuid4()
    session_memory.add_turn(sid, "Q", "A")
    session_memory.clear(sid)
    assert session_memory.get_turns(sid) == []
