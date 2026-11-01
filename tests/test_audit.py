import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from text_to_speech_claim_audit.audit import audit, evidence, main
from text_to_speech_claim_audit.phrases import TTS, NOTTS, claims, normalize

ROUTES = [
    'import pyttsx3\ne=pyttsx3.init()\ne.say("hello")',
    'from pyttsx3 import init as start\ne=start()\ne.save_to_file("hi", "a")',
    'import pyttsx3 as p\np.init().say("hi")',
    'from gtts import gTTS\ng=gTTS("hi")\ng.save("a")',
    'import gtts as g\nx=g.gTTS("hi")\nx.write_to_fp(fp)',
    'from gtts import gTTS as G\nG("hi").save("a")',
    'import edge_tts\ne=edge_tts.Communicate("hi")\ne.save("a")',
    'from edge_tts import Communicate as C\ne=C("hi")\ne.stream()',
    'import TTS.api\nt=TTS.api.TTS()\nt.tts("hi")',
    'from TTS import api\nt=api.TTS()\nt.tts_to_file("hi")',
    'from TTS.api import TTS as Voice\nVoice().tts_to_file("hi")',
    'from bark import generate_audio\ngenerate_audio("hi")',
    'import bark.api as b\nb.generate_audio("hi")',
    'from kokoro import KPipeline as K\np=K()\np("hi")',
    'import kokoro\np=kokoro.KPipeline()\np("hi")',
    'from transformers import pipeline as p\np("text-to-speech")',
    'import transformers as t\nt.pipeline(task="text-to-speech")',
    'client.audio.speech.create(input="hi")',
    'import win32com.client\nv=win32com.client.Dispatch("SAPI.SpVoice")\nv.Speak("hi")',
    'from win32com.client import Dispatch as D\nD("SAPI.SpVoice").Speak("hi")',
    'import edge_tts\nedge_tts.Communicate("hi").stream()',
    'from kokoro import KPipeline\nKPipeline(lang_code="a")("hello")',
]
NON = [
    'import pyttsx3', 'import pyttsx3\npyttsx3.init()',
    'import pyttsx3\ne=pyttsx3.init()\ne.runAndWait()',
    'from gtts import gTTS\ngTTS("hi")',
    'from edge_tts import Communicate\nCommunicate("hi")',
    'from TTS.api import TTS\nTTS()',
    'from kokoro import KPipeline\nKPipeline()',
    'from win32com.client import Dispatch\nDispatch("SAPI.SpVoice")',
    'import sounddevice\nsounddevice.play(data)',
    'from playsound import playsound\nplaysound("a.wav")',
    'import pygame\npygame.mixer.music.play()',
    'import simpleaudio\nsimpleaudio.play_buffer(data)',
    'import winsound\nwinsound.PlaySound("a", 0)',
    'import os\nos.startfile("a.wav")',
    'import librosa\nlibrosa.load("a")',
    'import soundfile\nsoundfile.read("a")',
    'import wave\nwave.open("a", "rb")',
    'import torchaudio\ntorchaudio.load("a")',
    'import whisper\nmodel=whisper.load_model("base")\nmodel.transcribe("a")',
    'import speech_recognition as sr\nsr.Recognizer().recognize_google(data)',
    'from transformers import pipeline\npipeline("automatic-speech-recognition")',
    'from diffusers import AudioLDMPipeline\nAudioLDMPipeline()()',
    'from audiocraft.models import MusicGen\nMusicGen.get_pretrained("x").generate(["hi"])',
    'import subprocess\nsubprocess.run(["espeak", "hi"])',
    '"client.audio.speech.create()"',
    'from bark import generate_audio\ndef generate_audio(x): pass\ngenerate_audio("hi")',
    'from gtts import gTTS\nclass gTTS: pass\ngTTS().save("a")',
    'from transformers import pipeline\ndef pipeline(x): pass\npipeline("text-to-speech")',
    'from pyttsx3 import init\ninit=lambda: None\ninit().say("hi")',
    'from kokoro import KPipeline\ndef f(KPipeline):\n p=KPipeline()\n p("hi")',
    'engine.say("hi")', 'voice.Speak("hi")', 'x.save("a")', 'x.tts("hi")',
    'from bark import generate_audio\ngenerate_audio', 'this is syntax invalid !!',
]


class AuditTests(unittest.TestCase):
    def project(self, files):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        return root

    def cli(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main(args)
            except SystemExit as error:
                code = error.code
        return code, output.getvalue()

    def test_phrase_order_and_paragraphs(self):
        self.assertEqual(claims('no tts support; supports tts; speech synthesis'), {'TTS', 'NOTTS'})
        root = self.project({'README.md': 'speaks\n\naloud'})
        self.assertEqual(audit(root)['claims'], [])
        root = self.project({'README.md': 'speaks aloud; reads aloud; speaks aloud'})
        self.assertEqual(len(audit(root)['findings']), 1)

    def test_io_error(self):
        root = self.project({})
        (root / 'README.md').write_bytes(b'\xff')
        self.assertEqual(self.cli([str(root)])[0], 1)

    def test_module_isolation(self):
        root = self.project({'README.md': 'speaks aloud',
                             'one.py': 'import pyttsx3\ne=pyttsx3.init()',
                             'two.py': 'e.say("hi")'})
        self.assertFalse(audit(root)['production_evidence'])

    def test_all_constructor_shadows(self):
        for module, symbol, operation in [
            ('pyttsx3', 'init', 'say("hi")'),
            ('gtts', 'gTTS', 'save("a")'),
            ('edge_tts', 'Communicate', 'stream()'),
            ('TTS.api', 'TTS', 'tts("hi")'),
            ('win32com.client', 'Dispatch', 'Speak("hi")'),
        ]:
            source = 'from %s import %s\ndef %s(*args): pass\nv=%s("SAPI.SpVoice")\nv.%s' % (module, symbol, symbol, symbol, operation)
            with self.subTest(symbol=symbol):
                self.assertFalse(evidence(source))

    def test_phrase_counts(self):
        self.assertEqual(len(TTS), 38)
        self.assertEqual(len(NOTTS), 20)
        self.assertEqual(len(set(TTS + NOTTS)), 58)

    def test_normalization(self):
        self.assertEqual(normalize("Doesn't\nconvert text-to-speech"), 'does not convert text to speech')
        self.assertEqual(claims("Doesn't convert text-to-speech"), {'NOTTS'})
        self.assertEqual(claims('xtts ttsx'), set())

    def test_docs_scope(self):
        root = self.project({'docs/nested/guide.md': '`reads aloud`', 'other.md': 'no tts'})
        self.assertEqual(audit(root)['claims'], ['TTS'])

    def test_fences(self):
        root = self.project({'README.md': '   ```python\nspeaks aloud\n   ```\n\n~~~\nno tts\n~~~\n'})
        self.assertEqual(audit(root)['claims'], [])

    def test_test_only(self):
        for name in ['tests/a.py', 'test_a.py', 'a_test.py']:
            with self.subTest(name=name):
                root = self.project({'README.md': 'speaks aloud', name: ROUTES[0]})
                self.assertEqual(audit(root)['findings'][0]['severity'], 'MEDIUM')
                self.assertEqual(self.cli([str(root)])[0], 0)
                self.assertEqual(self.cli([str(root), '--fail-on', 'MEDIUM'])[0], 2)

    def test_excluded_sources(self):
        for name in ['fixtures/a.py', 'docs/a.py', 'examples/a.py']:
            with self.subTest(name=name):
                root = self.project({'README.md': 'speaks aloud', name: ROUTES[0]})
                self.assertEqual(audit(root)['findings'][0]['severity'], 'HIGH')

    def test_no_source_asymmetry(self):
        self.assertEqual(len(audit(self.project({'README.md': 'tts'}))['findings']), 1)
        self.assertEqual(audit(self.project({'README.md': 'no tts'}))['findings'], [])

    def test_ignore(self):
        root = self.project({'README.md': 'speaks aloud', 'src/a.py': ROUTES[0]})
        self.assertEqual(audit(root)['findings'], [])
        self.assertEqual(len(audit(root, ['src'])['findings']), 1)
        self.assertEqual(self.cli([str(root), '--ignore', 'README.md'])[0], 0)

    def test_symlinks(self):
        root = self.project({'README.md': 'speaks aloud', 'fixtures/real.py': ROUTES[0]})
        (root / 'link.py').symlink_to(root / 'fixtures/real.py')
        (root / 'linked').symlink_to(root / 'fixtures', target_is_directory=True)
        self.assertFalse(audit(root)['production_evidence'])

    def test_cli(self):
        root = self.project({'README.md': 'speaks aloud'})
        code, output = self.cli([str(root), '--json'])
        self.assertEqual(code, 2)
        data = json.loads(output)
        self.assertEqual(set(data), {'status', 'findings', 'claims', 'production_evidence', 'test_evidence'})
        self.assertEqual(data['status'], 'FAIL')
        self.assertEqual(self.cli([str(root), '--verbose'])[0], 2)
        self.assertEqual(self.cli([str(root / 'missing')])[0], 1)
        self.assertEqual(self.cli(['--unknown'])[0], 1)
        self.assertEqual(self.cli(['--fail-on', 'INVALID'])[0], 1)
        self.assertEqual(self.cli(['--version']), (0, '0.1.0\n'))
        self.assertEqual(self.cli([str(self.project({}))])[0], 0)


def phrase_test(phrase, family):
    def test(self):
        self.assertEqual(normalize(phrase), phrase)
        self.assertEqual(claims(phrase), {family})
        files = {'docs/guide.md': phrase}
        if family == 'NOTTS':
            files['app.py'] = ROUTES[0]
        result = audit(self.project(files))
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertEqual(result['findings'][0]['rule'], 'documented-no-tts-claim-false' if family == 'NOTTS' else 'documented-tts-claim-false')
    return test


for family, phrases in [('TTS', TTS), ('NOTTS', NOTTS)]:
    for index, phrase in enumerate(phrases):
        setattr(AuditTests, 'test_phrase_%s_%02d' % (family, index), phrase_test(phrase, family))
for index, source in enumerate(ROUTES):
    def test(self, source=source):
        self.assertTrue(evidence(source), source)
    setattr(AuditTests, 'test_route_%02d' % index, test)
for index, source in enumerate(NON):
    def test(self, source=source):
        self.assertFalse(evidence(source), source)
    setattr(AuditTests, 'test_non_evidence_%02d' % index, test)

if __name__ == '__main__':
    unittest.main()
