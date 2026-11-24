Placeholders de áudio originais, sintetizados localmente para A Vigília das Cinzas.
21 SFX e cinco loops estéreo PCM 16-bit a 44100 Hz (aproximadamente 13 MB).
Gerador determinístico: tools/synthesize_audio.py (numpy, seed 46).
Nenhuma amostra externa foi utilizada.

Regenerar: .venv/Scripts/python.exe tools/synthesize_audio.py
Mapeamento, volume por evento e prioridade: data/audio/map.toml

O jogo não gera arquivos ao iniciar. Sem WAVs, ou sem dispositivo de áudio,
continua silencioso. Cada arquivo ausente/corrompido é ignorado isoladamente.
Esses loops curtos ficam em memória para permitir crossfade por dois canais.
Uma trilha final longa precisará de um backend de streaming adequado.
