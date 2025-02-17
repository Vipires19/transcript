from streamlit_webrtc import WebRtcMode, webrtc_streamer
from pathlib import Path
from datetime import datetime
import time
import queue

import streamlit as st
import openai
import pydub

PASTA_ARQUIVOS = Path(__file__).parent / 'arquivos'
PASTA_ARQUIVOS.mkdir(exist_ok=True)

PROMPT = '''Faça o resumo do texto delimitado por #### 
O texto é a trancrição de uma reunião.
O resumo deve contar com os principais assuntos abordados durante a reunião
O resumo deve ter no máximo 400 caracteres.
O resumo deve estar em texto corrido.
No final, deve ser apresentado todos acordos e combinados feitos durante a reunião no formato de bullet points.
Se ouver perguntas durante a reunião separe as perguntas e respostas com bullet points assim como no exemplo, se não haver perguntas na transcrição da reunião não retorne nada referente as perguntas.

O formato final que eu desejo é:
Resumo reunião:
- escrever aqui o resumo.

Perguntas:
- Pergunta 1\n Resposta 1
- Pergunta 2\n Resposta 2
- Pergunta n\n Resposta n

Acordos da Reunião:
- Acordo 1
- Acordo 2
- Acordo n

texto: ####{}####

'''

client = openai.OpenAI(api_key= st.secrets['OPENAI_API_KEY'])

def salva_arquivo(caminho_arquivo, conteudo):
    with open(caminho_arquivo, 'w') as f:
        f.write(conteudo)

def ler_arquivo(caminho_arquivo):
    if caminho_arquivo.exists():
        with open(caminho_arquivo) as f:
            return f.read()
    else:
        return ''

def listar_pacientes():
    lista_pacientes = PASTA_ARQUIVOS.glob('*')
    lista_pacientes = list(lista_pacientes)
    paciente_dict = {}
    for pasta_paciente in lista_pacientes:
        paciente_paste = pasta_paciente.stem
        paciente_dict[paciente_paste]  = paciente_paste
    return paciente_dict

def listar_reunioes(paciente):
    pasta_reunioes = PASTA_ARQUIVOS/paciente
    lista_reunioes = pasta_reunioes.glob('*')
    lista_reunioes = list(lista_reunioes)
    lista_reunioes.sort(reverse=True)
    reunioes_dict = {}
    for pasta_reuniao in lista_reunioes:
        data_reuniao = pasta_reuniao.stem
        ano, mes,dia,hora,minuto,segundo = data_reuniao.split('_')
        reunioes_dict[data_reuniao] = f'{dia}/{mes}/{ano} {hora}:{minuto}:{segundo}'
        titulo = ler_arquivo(pasta_reuniao / 'titulo.txt')
        if titulo != '':
            reunioes_dict[data_reuniao] += f' - {titulo}'
    return reunioes_dict

def transcreve_audio(caminho_audio, language = 'pt', response_format = 'text'):
    with open(caminho_audio, 'rb') as arquivo_audio:
        transcripit = client.audio.transcriptions.create(
            model= 'whisper-1',
            language=language,
            response_format= response_format,
            file= arquivo_audio
        )
    return transcripit

def chat_openai(mensagem, modelo = "gpt-4o-mini"):
    mensagens = [{'role' : 'user', 'content' : mensagem}]
    resposta = client.chat.completions.create(
        model=modelo,
        messages=mensagens,
    )
    return resposta.choices[0].message.content

def adiciona_audio_chunck(frames_audio,audio_chunck):
    for frame in frames_audio:
        sound = pydub.AudioSegment(
            data=frame.to_ndarray().tobytes(),
            sample_width = frame.format.bytes,
            frame_rate = frame.sample_rate,
            channels = len(frame.layout.channels)
        )
        audio_chunck += sound
    return audio_chunck

def gravar():

    paciente = st.text_input('Nome do Paciente')

    webrtx_ctx = webrtc_streamer(
        key = 'recebe_audio',
        mode = WebRtcMode.SENDONLY,
        audio_receiver_size = 1024,
        media_stream_constraints ={'video' : False, 'audio' :True},
    )

    if not webrtx_ctx.state.playing:
        st.markdown('Não está rodando')
        return
    
    container = st.empty()
    container.markdown('Comece a falar')

    pasta_paciente = PASTA_ARQUIVOS / paciente
    pasta_paciente.mkdir(exist_ok = True)

    pasta_reuniao = PASTA_ARQUIVOS / paciente /datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    pasta_reuniao.mkdir()

    ultima_transcricao = time.time()
    audio_completo = pydub.AudioSegment.empty()
    audio_chunck = pydub.AudioSegment.empty()
    transcricao = ''

    while True:
        if webrtx_ctx.audio_receiver:
            
            try:
                frames_audio = webrtx_ctx.audio_receiver.get_frames(timeout = 1)
            except queue.Empty:
                time.sleep(0.1)
                continue
            
            audio_completo = adiciona_audio_chunck(frames_audio,audio_completo)
            audio_chunck = adiciona_audio_chunck(frames_audio,audio_chunck)
            
            if len(audio_chunck) > 0:
                audio_completo.export(pasta_reuniao/'audio.mp3')
                agora = time.time()
                if agora - ultima_transcricao > 5:
                    ultima_transcricao = agora
                    audio_chunck.export(pasta_reuniao/'audio_temp.mp3')
                    transcricao_chunck = transcreve_audio(pasta_reuniao/'audio_temp.mp3')
                    transcricao += transcricao_chunck
                    salva_arquivo(pasta_reuniao/'transcricao.txt', transcricao)
                    container.markdown(transcricao)

                    audio_chunck = pydub.AudioSegment.empty()


        else:
            break

def salvar_tit(pasta_reuniao, titulo):
    salva_arquivo(pasta_reuniao / 'titulo.txt', titulo)

def selecao():
    st.markdown('Seleção de reuniões')
    paciente_dict = listar_pacientes()
    pacientes = st.selectbox('Paciente', list(paciente_dict.values()))
    reunioes_dict = listar_reunioes(pacientes)
    if len(reunioes_dict) > 0:
        reuniao_selecionada = st.selectbox('Selecione uma reunião', list(reunioes_dict.values()))
        st.divider()
        reuniao_data = [k for k, v in reunioes_dict.items() if v == reuniao_selecionada][0]
        pasta_reuniao = PASTA_ARQUIVOS / pacientes / reuniao_data
        if not (pasta_reuniao/ 'titulo.txt').exists():
            st.warning('Adicione um título')
            titulo_reuniao = st.text_input('Título da reunião')
            st.button('Salvar', on_click= salvar_tit, args=(pasta_reuniao,titulo_reuniao))


        else:
            titulo = ler_arquivo(pasta_reuniao / 'titulo.txt')
            transcript = ler_arquivo(pasta_reuniao / 'transcricao.txt')
            resumo = ler_arquivo(pasta_reuniao / 'resumo.txt')
            if resumo == '':
                gerar_resumo(pasta_reuniao)
                resumo = ler_arquivo(pasta_reuniao/'resumo.txt')
            st.markdown(f'## {titulo}')
            st.markdown(f'{resumo}')
            st.divider()
            st.markdown(f'## Transcrição completa')
            st.markdown(transcript)

def gerar_resumo(pasta_reuniao):
    transcript = ler_arquivo(pasta_reuniao/'transcricao.txt')
    resumo = chat_openai(mensagem= PROMPT.format(transcript))
    salva_arquivo(pasta_reuniao / 'resumo.txt', resumo)


def main():
    st.title('Camppo Transcript 🎤')
    tab_gravar, tab_selecao = st.tabs(['Gravar reunião', 'Ver Transcrições Salvas'])
    with tab_gravar:
        
        gravar()
    with tab_selecao:
        selecao()

if __name__ == '__main__':
    main()