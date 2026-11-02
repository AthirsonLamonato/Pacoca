"""Offline Windows speech. Output is an in-memory WAV, never speaker playback."""
from functools import lru_cache
import io
import math
import os
import wave


@lru_cache(maxsize=1)
def female_voices():
    if os.name != 'nt':
        return ()
    import pythoncom
    from win32com.client.dynamic import Dispatch
    pythoncom.CoInitialize()
    voice = tokens = None
    try:
        voice = Dispatch('SAPI.SpVoice')
        tokens = voice.GetVoices('Language=416;Gender=Female')
        return tuple((tokens.Item(i).Id, tokens.Item(i).GetDescription()) for i in range(tokens.Count))
    except Exception:
        return ()
    finally:
        tokens = voice = None
        pythoncom.CoUninitialize()


def synthesize_female(text, speed):
    available = female_voices()
    if not available:
        raise RuntimeError('Não encontrei uma voz feminina de português brasileiro instalada no Windows. Escolha a voz masculina ou adicione a voz de português nas configurações de fala do Windows.')
    import pythoncom
    from win32com.client.dynamic import Dispatch
    pythoncom.CoInitialize()
    voice = tokens = token = stream = None
    try:
        voice = Dispatch('SAPI.SpVoice')
        tokens = voice.GetVoices('Language=416;Gender=Female')
        token = next((tokens.Item(i) for i in range(tokens.Count) if tokens.Item(i).Id == available[0][0]), None)
        if token is None:
            raise RuntimeError('A voz feminina do Windows não está mais disponível.')
        voice.Voice = token
        voice.Rate = max(-5, min(5, round(math.log2(max(.7, min(1.4, speed))) * 10)))
        stream = Dispatch('SAPI.SpMemoryStream')
        stream.Format.Type = 18  # SAFT16kHz16BitMono
        voice.AudioOutputStream = stream
        voice.Speak(text, 16)  # SVSFIsNotXML: arbitrary user text stays plain text.
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(bytes(stream.GetData()))
        return output.getvalue()
    finally:
        voice = token = tokens = stream = None
        pythoncom.CoUninitialize()
