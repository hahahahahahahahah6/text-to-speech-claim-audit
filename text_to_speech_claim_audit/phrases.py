"""Exact normalized documentation templates."""
import re

TTS = ('text to speech', 'converts text to speech', 'convert text to speech', 'converts text into speech', 'convert text into speech', 'does text to speech', 'text to speech conversion', 'text to speech synthesis', 'text to speech support', 'supports text to speech', 'support text to speech', 'speech synthesis', 'synthesizes speech', 'synthesize speech', 'synthesizes voice', 'voice synthesis', 'generates speech', 'generate speech', 'generates spoken audio', 'speaks text aloud', 'speaks aloud', 'speaks text', 'reads text aloud', 'reads aloud', 'reads out loud', 'reads text out loud', 'text to voice', 'converts text to voice', 'spoken output', 'speech output', 'voice output', 'narrates text', 'text narration', 'tts', 'tts support', 'supports tts', 'tts engine', 'tts capabilities')
NOTTS = ('no text to speech', 'does not convert text to speech', 'does not do text to speech', 'without text to speech', 'no tts', 'no tts support', 'without tts', 'does not speak', 'does not read aloud', 'does not read text aloud', 'cannot speak', 'never speaks', 'no voice output', 'no spoken output', 'no speech output', 'no speech synthesis', 'without speech synthesis', 'does not synthesize speech', 'does not generate speech', 'text only')

def normalize(text):
    return ' '.join(text.lower().replace("n't", ' not').replace('-', ' ').split())

def _remove(text, phrases):
    found = False
    for phrase in sorted(phrases, key=lambda p: (-len(p), p)):
        text, count = re.subn(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', ' ', text)
        found = found or bool(count)
    return text, found

def claims(text):
    text, negative = _remove(normalize(text), NOTTS)
    _, positive = _remove(text, TTS)
    return ({'NOTTS'} if negative else set()) | ({'TTS'} if positive else set())
