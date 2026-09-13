import pytest
from tests.support.live_voice.semantic_constraint_oracles import (
    EQUIPMENT_CONSTRAINTS,
    FLIGHT_CONSTRAINTS,
    assert_constraint_patterns,
)

FLIGHT = "明日10:00客户会议准时到达。新增交通及接驳支出不超过1500元，退款单独列明，酒店保持不变。禁止实际订票、办理退款或发送任何消息。保存出行方案.md。"
EQUIPMENT = "保证连续服务，不停止备份。支出不得超过1500元，不实际采购或安装，不发送消息。保存设备建议.md。"


@pytest.mark.parametrize(
    "text,required", [(FLIGHT, FLIGHT_CONSTRAINTS), (EQUIPMENT, EQUIPMENT_CONSTRAINTS)]
)
def test_complete_corpus_constraints_are_accepted(text, required):
    assert assert_constraint_patterns(text, required) == list(required)


@pytest.mark.parametrize(
    "old,new",
    [
        ("酒店保持不变", "立即修改酒店"),
        ("退款单独列明", "退款抵扣新费用"),
        (
            "禁止实际订票、办理退款或发送任何消息",
            "立即订票，立即办理退款，立即发送消息",
        ),
        ("会议准时到达", "会议可以迟到"),
        ("不超过1500", "可以超过1500"),
    ],
)
def test_money_and_filename_alone_never_pass_reversed_constraints(old, new):
    changed = FLIGHT.replace(old, new)
    assert "1500" in changed and "出行方案.md" in changed
    with pytest.raises(AssertionError):
        assert_constraint_patterns(changed, FLIGHT_CONSTRAINTS)


def test_backup_word_does_not_hide_opposite_operating_constraint():
    with pytest.raises(AssertionError):
        assert_constraint_patterns(
            EQUIPMENT.replace("不停止备份", "停止备份"), EQUIPMENT_CONSTRAINTS
        )


def test_clear_spoken_paraphrases_preserve_date_and_hotel_constraints():
    paraphrase = FLIGHT.replace(
        "明日10:00客户会议准时到达", "明早9:30到会场赶上10点客户会议，准时到达"
    ).replace("酒店保持不变", "酒店不要改动")
    assert_constraint_patterns(paraphrase, FLIGHT_CONSTRAINTS)
    with pytest.raises(AssertionError):
        assert_constraint_patterns(
            paraphrase.replace("酒店不要改动", "酒店允许改动"), FLIGHT_CONSTRAINTS
        )


def test_forbidden_effect_cannot_be_hidden_after_a_valid_prohibition():
    with pytest.raises(AssertionError):
        assert_constraint_patterns(FLIGHT + "但立即订票。", FLIGHT_CONSTRAINTS)


def test_spoken_coordinated_prohibition_keeps_message_constraint():
    spoken = FLIGHT.replace("禁止实际订票、办理退款或发送任何消息",
                            "不要订票,退款或者发送任何消息")
    assert_constraint_patterns(spoken, FLIGHT_CONSTRAINTS)
    with pytest.raises(AssertionError):
        assert_constraint_patterns(spoken + "但是允许发送任何消息。", FLIGHT_CONSTRAINTS)


@pytest.mark.parametrize("effect", ["立即购买设备", "立即安装", "立即购买设备并立即安装"])
def test_purchase_and_installation_cannot_override_equipment_prohibitions(effect):
    with pytest.raises(AssertionError):
        assert_constraint_patterns(EQUIPMENT + "但" + effect + "。", EQUIPMENT_CONSTRAINTS)
