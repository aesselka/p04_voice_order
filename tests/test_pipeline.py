from voice_cart_nlu.menu import Menu
from voice_cart_nlu.pipeline import VoiceCommandPipeline
from voice_cart_nlu.stt import STTResult


class FakeLLM:
    def __init__(self, reply): self.reply, self.calls = reply, 0
    def complete(self, system, user):
        self.calls += 1
        return self.reply


class FakeSTT:
    def transcribe(self, audio, **kw):
        return STTResult("Хочу два комбо", "ru", "fake", 12.0)


MENU = Menu.load()


def test_rules_confident_no_llm_call():
    llm = FakeLLM("{}")
    r = VoiceCommandPipeline(MENU, llm=llm).parse_text("Два комбо")
    assert llm.calls == 0 and r.commands[0].source == "rules"


def test_llm_fallback_and_menu_validation():
    reply = '```json\n{"commands":[{"intent":"add","items":[{"menu_item_id":"pizza","quantity":1},{"menu_item_id":"fries","quantity":2}]}]}\n```'
    llm = FakeLLM(reply)
    r = VoiceCommandPipeline(MENU, llm=llm).parse_text("Хочу пиццу и две картошки по-деревенски")
    c = r.commands[0]
    assert llm.calls == 1 and c.source == "llm"
    assert [i.menu_item_id for i in c.items] == ["fries"]       # выдуманный id отфильтрован


def test_llm_garbage_keeps_rules_result():
    r = VoiceCommandPipeline(MENU, llm=FakeLLM("not json")).parse_text("Хочу пиццу")
    assert r.commands[0].intent.value == "unknown"


def test_audio_path():
    r = VoiceCommandPipeline(MENU, stt=FakeSTT()).parse_audio(b"\x00")
    assert r.stt_provider == "fake" and r.commands[0].items[0].menu_item_id == "combo"
    assert "stt" in r.timings_ms
