"""Fixed-corpus checks only. Never imported by the production semantic path.

These conservative lexical oracles can reject a valid paraphrase; they cannot
grant product authority and are not a general semantic classifier. Every failed
or unrecognized phrasing remains a failed/uncertain test, not an automatic pass.
"""

import re


def negative_action_pattern(action: str) -> str:
    # Permit coordinated prohibitions, but no arbitrary intervening prose such
    # as 'do not change the hotel, but allow booking'.
    verbs = r"(?:订票|购票|采购|购买|安装|执行|进行|办理|退款|发送|任何|消息|信息|实际|或者|[、，,或和及与\s])"
    return rf"(?:不要|不得|禁止|不可|不){verbs}{{0,24}}(?:{action})"


FLIGHT_CONSTRAINTS = {
    "arrival_goal": r"(?:会议|到达).{0,15}准时|准时.{0,15}(?:会议|到达)",
    "meeting_time": r"明(?:日|天|早).{0,20}(?:10[:：]00|10点|十点)",
    "new_cost_budget": r"新增交通.{0,12}接驳.{0,16}(?:不超|不得超|不超过|不得超过|上限为?)(?:1500|一千五)",
    "refund_separate": r"(?:退款|退票).{0,35}单独|单独.{0,15}(?:退款|退票)",
    "hotel_unchanged": r"酒店.{0,8}(?:保持不变|暂不调整|先不要动|不要动|不要改动|不(?:调整|改动|更换|改变)|不变)|不(?:调整|改动|更换|改变).{0,4}酒店",
    "no_booking": negative_action_pattern(r"订票|购票"),
    "no_refund_effect": negative_action_pattern(r"退款"),
    "no_message": negative_action_pattern(r"发送(?:任何)?(?:消息|信息)"),
}
EQUIPMENT_CONSTRAINTS = {
    "budget": r"(?:不超|不得超|不超过|不得超过|上限为?)(?:1500|一千五)",
    "backup_kept": r"(?:不停止|不中断|持续|保持).{0,3}备份",
    "continuous_service": r"(?:保证|保障|保持|维持).{0,4}连续服务|服务不中断",
    "no_purchase": negative_action_pattern(r"采购|购买"),
    "no_installation": negative_action_pattern(r"安装"),
    "no_message": negative_action_pattern(r"发送(?:任何)?(?:消息|信息)"),
}
CONTRARY_EFFECTS = {
    "booking": r"(?:允许|立即|马上|开始)(?:实际)?(?:订票|购票)",
    "purchase": r"(?:允许|立即|马上|开始)(?:实际)?(?:采购|购买)",
    "installation": r"(?:允许|立即|马上|开始)(?:实际)?安装",
    "refund": r"(?:允许|立即|马上|开始)(?:办理)?退款",
    "message": r"(?:允许|立即|马上|开始)发送(?:任何)?(?:消息|信息)",
    "backup": r"(?<!不)(?:停止|中断)备份",
    "hotel": r"(?:允许|立即|马上|开始)(?:调整|改动|更换|改变)酒店",
}


def assert_constraint_patterns(instruction, required, forbidden=CONTRARY_EFFECTS):
    compact = re.sub(r"\s+", "", instruction)
    failures = [
        name
        for name, pattern in required.items()
        if re.search(pattern, compact) is None
    ]
    contradictions = [
        name for name, pattern in forbidden.items() if re.search(pattern, compact)
    ]
    assert not failures and not contradictions, {
        "missing_constraints": failures,
        "contrary_effects": contradictions,
    }
    return list(required)
