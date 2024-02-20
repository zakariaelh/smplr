from modal import Stub, Mount, Image, Volume, Secret, gpu, method, enter, asgi_app, Dict
import subprocess
import os
import time
import string
import random
from fastapi import FastAPI, staticfiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pathlib import Path
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

vol = Volume.persisted('samples')
vol2 = Volume.persisted("cache-pyannote")

image = Image.debian_slim().pip_install_from_requirements('requirements.txt').apt_install('ffmpeg')
image2 = Image.debian_slim().pip_install('torch', 'torchaudio', 'pydub', 'pyannote-audio').apt_install('ffmpeg')
image3 = Image.debian_slim().pip_install('pytube').apt_install('ffmpeg')
image_fe = Image.debian_slim().pip_install('pytube', 'pydub').apt_install('ffmpeg')

mounts=[
        Mount.from_local_dir(
                    local_path='uvr5_weights',
                    remote_path='/root/uvr5_weights/'),
        Mount.from_local_dir(
                    local_path='uvr5_pack',
                    remote_path='/root/uvr5_pack/')
            ]

stub = Stub(
    "smplr", 
    # volumes={'/root/audios': vol},
    volumes={'/root/audios': vol, '/root/.cache/torch/pyannote': vol2},
    # mounts=mounts,
    # image=image,
    secrets=[Secret.from_name("smplr-secrets")]
)

stub.progress = Dict.new()
stub.results = Dict.new()

assets_path = Path(__file__).parent / "front-end/build"
mounts_fe = [
        Mount.from_local_dir(assets_path, remote_path="/assets")
    ]

with image.imports():
    from separate import _audio_pre_
    from librosa.util.exceptions import ParameterError

with image2.imports():
    from torch import device, cuda
    from torchaudio import load
    from pyannote.audio import Pipeline
    from pyannote.audio.pipelines.utils.hook import ProgressHook
    from pydub import AudioSegment
     
with image_fe.imports():
    from pytube import YouTube, exceptions

def update_progress(run_id, text, perc=None, error=None, is_final = None, results = None):
    if run_id:
        stub.progress[run_id] = {
            "text": text,
            "perc": perc,
            "error": error,
            "is_final": is_final,
            "results": results
        }

def generate_random_id(length=10):
    """Generate a random ID of given length using letters and digits."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=length))


def secfloat_to_milli(sec_float):
        """Convert seconds (float) to milliseconds (int)."""
        return int(sec_float * 1000)

def concat_mp3_files(segment_files, format_type = 'wav'):
    t1 = time.time()
    # Sort the segment files by their numeric order inferred from filenames
    sorted_segment_files = sorted(
        segment_files, key=lambda x: int(os.path.basename(x).split('_')[-1].split('.')[0]))
    
    # Create a temporary file to list all the MP3 files to concatenate in sorted order
    with open("concat_list.txt", "w", encoding="utf-8") as list_file:
        for file_path in sorted_segment_files:
            list_file.write(f"file '{file_path}'\n")
    
    # FFmpeg command to concatenate all listed files
    output_file = "audios/" + os.path.basename(segment_files[0]).split('.')[0] + f'_concat_vocal.{format_type}'
    if format_type == 'mp3':
        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat_list.txt', 
            '-acodec', 'libmp3lame', '-q:a', '4', output_file
        ]
    elif format_type == 'wav':
        cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat_list.txt', '-c', 'copy', output_file]
    else:
        raise Exception('unknown format request for output file of concatenation')
    
    result = subprocess.run(cmd, capture_output=True)

    # Check for errors in FFmpeg command execution
    if result.returncode != 0:
        print(f"Error concatenating files: {result.stderr.decode()}")
        raise Exception('error when concatenating')
    # Clean up the temporary file
    os.remove("concat_list.txt")

    t2 = time.time()
    print('time to concat audio files', t2 - t1)
    return output_file

def convert_wav_to_mp3(input_file):
    """
    Convert an audio file to MP3 format using FFmpeg, letting FFmpeg choose the best
    audio settings based on the input file.

    Args:
    input_file (str): The path to the input audio file.
    output_file (str): The path where the output MP3 file should be saved.
    """
    output_file = input_file.replace('.wav', '.mp3')
    if output_file == input_file:
        return output_file
    
    try:
        command = [
            'ffmpeg',
            '-y',
            '-i', input_file,  # Input file
            '-vn',  # No video
            '-f', 'mp3',  # Output format
            '-q:a', '4',  # Quality scale (VBR), where a lower number is a higher quality. 2 is a good choice for high quality.
            output_file,  # Output file
        ]
        subprocess.run(command, check=True)
        print(f"Conversion successful. Output saved to {output_file}")
        return output_file
    except subprocess.CalledProcessError as e:
        print(f"Error during conversion: {e}")


@stub.function(image=image3, timeout=3600)
def youtube_to_mp3(url, segment_length, run_id = None):
    from pytube import YouTube
    
    update_progress(run_id, "Downloading")

    try: 

        t1 = time.time()
        # Download the video from YouTube
        yt = YouTube(url)
        
        # Select the audio stream
        video = yt.streams.filter(only_audio=True).first()
        
        # Download the audio stream
        out_file = video.download(output_path="audios")

        update_progress(run_id, "Video downloaded", perc=80)
        
        # Define the base filename for the MP3 segments
        base_filename = out_file.replace(".mp4", "")
        
        # Path for the segment files
        segment_path = f"{base_filename}_%03d.mp3"
        
        # FFmpeg command to convert to MP3 and split into segments
        cmd = [
            'ffmpeg', '-i', out_file, 
            '-f', 'segment', '-segment_time', str(segment_length), 
            '-c:a', 'libmp3lame', '-q:a', '4', 
            '-vn', segment_path
        ]

        subprocess.run(cmd)
        
        # Assuming the naming pattern holds, generate the list of segment files
        segment_files = [f for f in os.listdir("audios") if f.startswith(os.path.basename(base_filename)) and f.endswith(".mp3")]

        update_progress(run_id, "Video Converted")

        # Generate full paths
        segment_files_full_path = [os.path.join("audios", f) for f in segment_files]

        t2 = time.time()
        print('Time to download and segment:', t2 - t1)

        # Clean up the original downloaded file
        os.remove(out_file)

        vol.commit()

        return segment_files_full_path

    except Exception as e:
        update_progress(
            run_id,
            "Failed to download video",
            error=str(e)
        )
        raise e

@stub.cls(gpu="any",image=image,mounts=mounts, timeout=3600)
class VocalExtractor:
    # def __init__(self):
    #     pass 

    @enter()
    def load_model(self): 
        self.pre_fun = _audio_pre_(
            model_path='uvr5_weights/2_HP-UVR.pth',
            device='cuda',
            is_half=True
        )
        
    @method()
    def process(self, audio_path=None, init_only=False, run_id=None):
        if init_only: 
            time.sleep(1)
            return 'vocal init'
        else: 
            try:
                update_progress(run_id, "Starting the vocalization process")
                t1 = time.time()
                while True:
                    vol.reload() 
                    l = ['audios/' + i for i in os.listdir('audios/')]
                    # print(l)
                    time.sleep(0.5)
                    if audio_path in l:
                        print('HAHA')
                        break 

                save_path = 'audios'
                vocals_filename = self.pre_fun._path_audio_(
                        audio_path,
                        save_path,
                        save_path)
                
                update_progress(run_id, "Vocalization Done")

                vol.commit()
                print('vocals saved in ', vocals_filename)
                t2 = time.time()
                print('time to process the vocals (without init)', t2-t1)
                return vocals_filename
            except ParameterError as pe:
                print(f"ParameterError in {audio_path}")
                return None
            except Exception as e:
                update_progress(
                    run_id,
                    "Failed to do the vocalization",
                    error=str(e)
                )
                raise e 

@stub.cls(gpu=gpu.T4(count=2),image=image2, timeout=3600, container_idle_timeout=400)
class Diarizer:
    @enter()
    def start_pipeline(self):
        t1 = time.time()
        if cuda.is_available():
            for _ in range(10):
                print('CUDA')
        else:
            print('NOT AVAILABLE')
        
        self.pipeline = Pipeline.from_pretrained(
                checkpoint_path="pyannote/speaker-diarization-3.1",
                use_auth_token=os.environ['HF_TOKEN'],
                # cache_dir='.'
            ).to(device("cuda" if cuda.is_available() else "cpu"))
    
        vol2.commit()
        t2 = time.time()
        print('time to init pipeline ', t2 - t1)

    def split_audio_by_speaker(self, buffer):
        """Split the given audio into segments per speaker."""
        t1 = time.time()
        print('starting prediction')
        while True:
             vol.reload() 
             l = ['audios/' + i for i in os.listdir('audios/')]
             print(l)
             time.sleep(0.5)
             if buffer in l:
                  print('HAHA')
                  break 
        waveform, sample_rate = load(buffer)
        print('file path loaded by torchaudio')
        audio_in_memory = {"waveform": waveform, "sample_rate": sample_rate}
        with ProgressHook() as hook:
            diarization = self.pipeline(audio_in_memory, hook=hook)
        
        t2 = time.time()
        print('time to predict and diarize', t2 - t1)
        return diarization

    @method()
    def process(self, buffer=None, warm_start=False, run_id=None):
        vol.reload()
        if warm_start:
            return None
        
        try:
            update_progress(run_id, "Starting the diarization")

            if isinstance(buffer, list):
                # read all the audios files 
                vocal_concatenated_file = concat_mp3_files(segment_files=buffer)
                print(vocal_concatenated_file)
            else:
                vocal_concatenated_file = buffer
            
            update_progress(run_id, "Processing the Diarization")

            """Process the given audio file for speaker diarization."""
            # Split the audio by speaker
            diarization = self.split_audio_by_speaker(vocal_concatenated_file)
            # audio = AudioSegment.from_file(concat_file)
            update_progress(run_id, "Diarization Done")
            # return diarization  
            audio = AudioSegment.from_file(vocal_concatenated_file)
            audio_speaker = dict()
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segment = audio[secfloat_to_milli(turn.start):secfloat_to_milli(turn.end)]
                if speaker not in audio_speaker:
                    audio_speaker[speaker] = segment
                else:
                    audio_speaker[speaker] += segment
            
            # now save all of those segments 
            l_samples = []
            for audio in audio_speaker.values():
                audio_id = generate_random_id()
                file_name = f'{audio_id}.wav'
                audio.export(f'audios/{file_name}', format='wav')
                print('audio saved in ', file_name)
                l_samples.append(file_name)

            vol.commit()
            
            return l_samples
        except Exception as e:
            update_progress(
                run_id,
                "Failed to Diarize the video",
                error=str(e)
            )
            raise e 

# @stub.local_entrypoint()
@stub.function(image=image_fe, timeout=7200)
def orchestrator(url, segment_length, run_id=None):
    update_progress(run_id, "Starting the process")
    # spawn three containers 
    t1 = time.time()
    for i in range(3):
        _ = VocalExtractor().process.spawn(init_only=True)
    
    audio_files = youtube_to_mp3.remote(url, segment_length, run_id)
    print('list of mp3s from youtube: ', audio_files)
    t11 = time.time()
    # warming up diarizer container 
    Diarizer().process.remote(warm_start=True)

    l_vocals = []
    l_false = [False] * len(audio_files)
    l_run_id = [run_id] * len(audio_files)
    l_vocals = list(VocalExtractor().process.map(audio_files, l_false, l_run_id))
    # raise error if they're all None 
    if all([x is None for x in l_vocals]):
        update_progress(
                run_id,
                "Failed to Extract Vocals from the video",
                error="All segments returned None"
            )
        raise Exception("Vocalization failed as all segments return None")
    else: 
        l_vocals = [i for i in l_vocals if i is not None]
    print('list of vocals split and processed', l_vocals)
    t2 = time.time()
    # diarizer
    diarization_results = Diarizer().process.remote(l_vocals, run_id=run_id)
    t3 = time.time()
    update_progress(run_id, "Done", is_final=True, results=diarization_results)
    print('time to download (incl container build', t11 - t1)
    print('time taken to do vocalization (incl container build)', t2 - t11)
    print('time taken to do diarization (incl container build)', t3 - t2)
    print('time taken to do everything', t3 - t1)

    stub.results[run_id] = diarization_results
    return diarization_results


class Item(BaseModel):
    url: str
    segment_length: int

def sendAudioInChunks(file_path):  
    with open(file_path, mode="rb") as file_like:  
        yield from file_like  


@app.get('/url-details')
def validate_url(url):
    error = "Video cannot be downloaded"
    try:
        yt = YouTube(url)
        yt.streams.filter(only_audio=True).first()
        title = yt.title 
        length = yt.length
        return {
            "title": title,
            "length": length
        }
    except exceptions.AgeRestrictedError as age_error:
        return {
            "error": error,
            "reason": "Video is age-restricted",
            "stack": str(age_error),
        }
    except Exception as e:
        return {
            "error": error,
            "trace": str(e)
        }

@app.get('/retrieve-sample')
def retrieve_audio(audio_id, mp3_format=True):
    while True:
        vol.reload() 
        l = os.listdir('audios/')
        # print(l)
        time.sleep(0.5)
        if audio_id in l:
            print('HAHA')
            break 
    file_path = f'audios/{audio_id}'
    if mp3_format:
        file_path = convert_wav_to_mp3(file_path)
        media_type = 'audio/mp3'
    else:
        media_type = 'audio/wav'

    return StreamingResponse(sendAudioInChunks(file_path), media_type=media_type)

@app.get('/progress')
def get_progress(run_id):
    try:
        prog = stub.progress[run_id]
        return prog
    except KeyError:
        return "This run can't be found"

@app.get('/results')
def get_diarization_results(run_id):
    try:
        results = stub.results[run_id]
    except KeyError:
        return "no results yet"
    
    return results

@app.post('/sample')
def local_entry(item: Item):
    url = item.url
    segment_length = item.segment_length
    
    run_id = generate_random_id()
    orchestrator.spawn(url, segment_length, run_id)
    resp = {
        "run_id": run_id
    }
    return resp

@stub.function(image=image_fe, mounts=mounts_fe, container_idle_timeout=120)
@asgi_app()
def main():
    app.mount(
        "/", staticfiles.StaticFiles(directory="/assets", html=True)
    )
    return app