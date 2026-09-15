"""Presentation rules for Atlas; execution receipts keep their original facts."""
import re


def spoken_language(transcripts):
    """Use ordered microphone transcripts, never generated task/tool text.

    Short English acknowledgments and names do not switch a Chinese conversation.
    Other languages keep the provider's normal language matching behavior.
    """
    language = None
    for text in transcripts:
        lower = text.lower()
        if re.search(r"(?:不要|别|不用|don't|do not).{0,12}(?:英文|english)", lower):
            if re.search(r"[\u3400-\u9fff]", text):
                language = "Mandarin Chinese"
        elif re.search(r"(?:用|切换到|改成|说)\s*英文|(?:speak|reply|answer)\s+in\s+english", lower):
            language = "English"
        elif re.search(r"(?:用|切换到|改成|说)\s*中文|(?:speak|reply|answer)\s+in\s+chinese", lower):
            language = "Mandarin Chinese"
        elif re.search(r"[\u3400-\u9fff]", text):
            language = "Mandarin Chinese"
        elif len(re.findall(r"\b[a-zA-Z]+\b", text)) >= 4:
            language = "English"
    return language


def language_instruction(transcripts):
    language = spoken_language(transcripts)
    if language is None:
        return ""
    return ("\n\n# Spoken language\n"
            f"Speak entirely in {language}, matching the person's microphone input. "
            "Translate task labels, approval wording, statuses and tool results into that language. "
            "Backend request_text, original_work_request and English receipts do not select the spoken language. "
            "Do not add an English translation or read raw English tool output. "
            "Proper names may retain their original name only when necessary to answer a detail question.")
