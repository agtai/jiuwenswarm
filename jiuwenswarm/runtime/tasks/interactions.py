"""Validate observed information questions without granting approval authority."""

from copy import deepcopy


def information_question(payload):
    source = payload.get("source", "")
    questions = payload.get("questions")
    if (
        source not in {"", "ask_user", "ask_user_interrupt"}
        or payload.get("approval_schema")
        or payload.get("evolution_meta")
        or not isinstance(payload.get("request_id"), str)
        or not payload["request_id"]
        or not isinstance(questions, list)
        or not questions
        or any(
            not isinstance(q, dict)
            or not isinstance(q.get("question"), str)
            or not q["question"].strip()
            for q in questions
        )
    ):
        raise ValueError(
            "This interaction requires the existing non-voice interaction channel"
        )
    return dict(
        request_id=payload["request_id"],
        source=source,
        questions=deepcopy(questions),
        state="pending",
    )


def validate_answers(interaction, answers):
    """Bind ordered voice answers to Core's original observed questions."""
    information_question(interaction)
    if not isinstance(answers, list) or len(answers) != len(interaction["questions"]):
        raise ValueError("Answer every observed question exactly once")
    resolved = []
    for question, answer in zip(interaction["questions"], answers):
        if isinstance(answer, str):
            answer = {"question": question["question"], "answer": answer}
        if (
            not isinstance(answer, dict)
            or set(answer) - {"question", "answer", "selected_options"}
            or answer.get("question") != question["question"]
        ):
            raise ValueError("Answer does not match the observed question")
        text, options = answer.get("answer", ""), answer.get("selected_options", [])
        if (
            not isinstance(text, str)
            or len(text) > 4000
            or not isinstance(options, list)
            or len(options) > 32
            or any(
                not isinstance(v, str) or not v.strip() or len(v) > 1000
                for v in options
            )
            or not (text.strip() or options)
        ):
            raise ValueError("Invalid information answer")
        resolved.append(dict(answer))
    return resolved
